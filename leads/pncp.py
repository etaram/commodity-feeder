"""Brazil: PNCP (Portal Nacional de Contratações Públicas) open API - every purchase notice still taking proposals,
all sizes and modalities (owner, 13 Nov 2026: every segment, target 1M open opportunities; the value stays on the row
and the panel filters by it). Portuguese text, sector by keyword. A first run (or a small cache) reads the last 30
days, later runs the last 2; a time budget keeps the step inside its timeout and the rest comes next run."""
import datetime as dt
import time

from .common import CACHE, cache_empty, clean, log, polite, rolling, session, today
from .sectors import classify

URL = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
MODES = {6: "Pregão eletrônico", 4: "Concorrência eletrônica", 8: "Dispensa", 7: "Pregão presencial",
         5: "Concorrência presencial", 1: "Leilão eletrônico", 2: "Diálogo competitivo", 3: "Concurso", 12: "Credenciamento"}
BUDGET_S = 900


def fetch():
    s, t = session(), today()
    small = cache_empty("pncp") or (CACHE / "pncp.jsonl").stat().st_size < 20_000_000
    days = 30 if small else 2
    d0, d1 = (t - dt.timedelta(days=days)).strftime("%Y%m%d"), t.strftime("%Y%m%d")
    new, t0, pages = [], time.time(), 0
    for mode in MODES:
        page = 1
        while page <= 1000 and time.time() - t0 < BUDGET_S:
            r = s.get(URL, params={"dataInicial": d0, "dataFinal": d1, "codigoModalidadeContratacao": mode,
                                   "pagina": page, "tamanhoPagina": 50}, timeout=90)
            if r.status_code == 429:
                polite(15)
                r = s.get(URL, params={"dataInicial": d0, "dataFinal": d1, "codigoModalidadeContratacao": mode,
                                       "pagina": page, "tamanhoPagina": 50}, timeout=90)
            if r.status_code == 204:
                break
            if r.status_code != 200:
                log.warning("PNCP %s mode %s p%s", r.status_code, mode, page); break
            j = r.json()
            for n in j.get("data") or []:
                v = n.get("valorTotalEstimado") or 0
                dl = (n.get("dataEncerramentoProposta") or "")[:10]
                if dl and dl < str(t):
                    continue
                org = n.get("orgaoEntidade") or {}; un = n.get("unidadeOrgao") or {}
                text = clean(f"{n.get('objetoCompra', '')} {n.get('informacaoComplementar', '') or ''}")
                sector, method = classify(text)
                cnpj, ano, seq = org.get("cnpj", ""), n.get("anoCompra"), n.get("sequencialCompra")
                new.append({
                    "id": f"PNCP-{n.get('numeroControlePNCP')}", "source": "PNCP (Brazil)", "group": "",
                    "sector": sector, "nature": "", "cpv": "", "classification": method, "country": "BRA",
                    "buyer": clean(f"{org.get('razaoSocial', '')} ({un.get('ufSigla', '')})", 120), "title": text[:300],
                    "notice_type": MODES.get(mode, ""), "stage": "tender", "access": "National (foreign firms via local rep)",
                    "published": (n.get("dataPublicacaoPncp") or "")[:10], "deadline": dl,
                    "value": round(v) if v else "", "currency": "BRL" if v else "",
                    "link": f"https://pncp.gov.br/app/editais/{cnpj}/{ano}/{seq}", "contact": "", "lang": "pt",
                })
            if j.get("paginasRestantes", 0) <= 0:
                break
            page += 1; pages += 1
            polite(0.6)
    rows, _ = rolling("pncp", new, max_age_days=120)
    log.info("PNCP window %d days, pages %d, new %d, open %d, budget used %ds", days, pages, len(new), len(rows), time.time() - t0)
    return rows, {"new": len(new), "pages": pages}
