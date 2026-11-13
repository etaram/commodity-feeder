"""Brazil: PNCP (Portal Nacional de Contratações Públicas) open API - every purchase notice still taking proposals,
all sizes and modalities (owner, 13 Nov 2026: every segment, target 1M open opportunities; the value stays on the row
and the panel filters by it). Portuguese text, sector by keyword. A first run (or a small cache) reads the last 30
days. Two lanes per run: a freshness lane (the last 2 days, every modality, first) and a backfill lane over a 30-day window
that resumes where the last run stopped (modality and page saved in cache/pncp_progress.json only after a page was
read; a failed page is read again next run). Notices whose proposal deadline has passed are dropped; a notice without
a deadline is kept as published and is not counted as confirmed open by the panel."""
import datetime as dt
import json
import os
import time

from .common import CACHE, clean, log, polite, rolling, session, today
from .sectors import classify

URL = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
MODES = {6: "Pregão eletrônico", 4: "Concorrência eletrônica", 8: "Dispensa", 7: "Pregão presencial",
         5: "Concorrência presencial", 1: "Leilão eletrônico", 2: "Diálogo competitivo", 3: "Concurso", 12: "Credenciamento"}
BUDGET_S = 900


FRESH_S = 240          # the freshness lane (last 2 days, every modality) always runs first
PROGRESS = CACHE / "pncp_progress.json"


def _page(s, d0, d1, mode, page):
    """(rows on that page, pages remaining) or None on a failure (the page is not checkpointed and is read again)."""
    params = {"dataInicial": d0, "dataFinal": d1, "codigoModalidadeContratacao": mode, "pagina": page, "tamanhoPagina": 50}
    for wait in (0, 15, 45):
        if wait:
            polite(wait)
        try:
            r = s.get(URL, params=params, timeout=90)
        except Exception as e:  # noqa: BLE001
            log.warning("PNCP mode %s p%s: %s", mode, page, str(e)[:100]); continue
        if r.status_code == 204:
            return [], 0
        if r.status_code == 200:
            try:
                j = r.json()
            except ValueError:
                continue
            return j.get("data") or [], int(j.get("paginasRestantes") or 0)
        if r.status_code not in (429, 500, 502, 503, 504):
            log.warning("PNCP %s mode %s p%s", r.status_code, mode, page); return None
    return None


def _rows(data, mode, t):
    out = []
    for n in data:
        v = n.get("valorTotalEstimado") or 0
        dl = (n.get("dataEncerramentoProposta") or "")[:10]
        if dl and dl < str(t):
            continue
        org = n.get("orgaoEntidade") or {}; un = n.get("unidadeOrgao") or {}
        text = clean(f"{n.get('objetoCompra', '')} {n.get('informacaoComplementar', '') or ''}")
        sector, method = classify(text)
        cnpj, ano, seq = org.get("cnpj", ""), n.get("anoCompra"), n.get("sequencialCompra")
        out.append({
            "id": f"PNCP-{n.get('numeroControlePNCP')}", "source": "PNCP (Brazil)", "group": "",
            "sector": sector, "nature": "", "cpv": "", "classification": method, "country": "BRA",
            "buyer": clean(f"{org.get('razaoSocial', '')} ({un.get('ufSigla', '')})", 120), "title": text[:300],
            "notice_type": MODES.get(mode, ""), "stage": "tender", "access": "National (foreign firms via local rep)",
            "published": (n.get("dataPublicacaoPncp") or "")[:10], "deadline": dl,
            "value": round(v) if v else "", "currency": "BRL" if v else "",
            "link": f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}", "contact": "", "lang": "pt",
        })
    return out


def _lane(s, d0, d1, t, budget, start=(0, 1)):
    """Reads modalities in order from start=(modality index, page). Returns (rows, pages read, next position or None
    when every modality was read to its end, failed pages)."""
    keys = list(MODES)
    t0, rows, pages, failed = time.time(), [], 0, 0
    mi, page = start
    while mi < len(keys):
        if time.time() - t0 > budget:
            return rows, pages, (mi, page), failed
        got = _page(s, d0, d1, keys[mi], page)
        if got is None:              # not checkpointed: the next run starts again at this page
            failed += 1
            return rows, pages, (mi, page), failed
        data, remaining = got
        rows += _rows(data, keys[mi], t); pages += 1
        if remaining <= 0 or page >= 2000:
            mi, page = mi + 1, 1
        else:
            page += 1
        polite(0.6)
    return rows, pages, None, failed


def fetch():
    s, t = session(), today()
    t0 = time.time()
    # 1. freshness lane: the last 2 days in full, every run, so a long backfill never starves new notices
    f0, f1 = (t - dt.timedelta(days=2)).strftime("%Y%m%d"), t.strftime("%Y%m%d")
    fresh, fpages, fpos, ffail = _lane(s, f0, f1, t, FRESH_S)
    # 2. backfill lane: a 30-day window read across runs, resumed from the saved position (modality, page)
    prog = {}
    if PROGRESS.exists():
        try:
            prog = json.loads(PROGRESS.read_text())
        except ValueError:
            prog = {}
    if not prog or prog.get("done_on") and prog.get("done_on") < str(t - dt.timedelta(days=7)):
        prog = {"d0": (t - dt.timedelta(days=30)).strftime("%Y%m%d"), "d1": f1, "mi": 0, "page": 1, "started": str(t)}
    back, bpages, bpos, bfail = [], 0, None, 0
    if not prog.get("done_on"):
        back, bpages, bpos, bfail = _lane(s, prog["d0"], prog["d1"], t, max(60, BUDGET_S - (time.time() - t0)),
                                          (int(prog.get("mi", 0)), int(prog.get("page", 1))))
        if bpos is None:
            prog.update({"done_on": str(t), "mi": len(MODES), "page": 1})
        else:
            prog.update({"mi": bpos[0], "page": bpos[1]})
        tmp = PROGRESS.with_name(PROGRESS.name + ".tmp"); tmp.write_text(json.dumps(prog)); os.replace(tmp, PROGRESS)
    rows, _ = rolling("pncp", fresh + back, max_age_days=120)
    left = "complete" if prog.get("done_on") else f"next modality {list(MODES)[prog['mi']] if prog['mi'] < len(MODES) else '-'} page {prog['page']}"
    log.info("PNCP fresh lane %d pages (%s), backfill %s..%s %d pages (%s), failed pages %d, new %d, open %d, %ds",
             fpages, "complete" if fpos is None else "cut by budget", prog.get("d0"), prog.get("d1"), bpages, left,
             ffail + bfail, len(fresh) + len(back), len(rows), time.time() - t0)
    return rows, {"new": len(fresh) + len(back), "pages": fpages + bpages, "backfill": left, "failed_pages": ffail + bfail}
