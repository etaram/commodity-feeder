"""Brazil: PNCP (Portal Nacional de Contratações Públicas) open API - electronic tenders (pregão and concorrência)
published in the last days, estimated value above MIN_BRL. Portuguese text, sector by keyword."""
import datetime as dt

from .common import cache_empty, clean, log, polite, rolling, session, today
from .sectors import classify

URL = "https://pncp.gov.br/api/consulta/v1/contratacoes/publicacao"
MODES = {4: "Concorrência eletrônica", 6: "Pregão eletrônico", 8: "Dispensa"}
MIN_BRL = 1_000_000


def fetch():
    s, t = session(), today()
    days = 10 if cache_empty("pncp") else 2
    d0, d1 = (t - dt.timedelta(days=days)).strftime("%Y%m%d"), t.strftime("%Y%m%d")
    new = []
    for mode in (4, 6):
        page = 1
        while page <= 120:
            r = s.get(URL, params={"dataInicial": d0, "dataFinal": d1, "codigoModalidadeContratacao": mode,
                                   "pagina": page, "tamanhoPagina": 50}, timeout=90)
            if r.status_code == 204:
                break
            if r.status_code != 200:
                log.warning("PNCP %s mode %s p%s", r.status_code, mode, page); break
            j = r.json()
            for n in j.get("data") or []:
                v = n.get("valorTotalEstimado") or 0
                if v and v < MIN_BRL:
                    continue
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
            page += 1
            polite(0.3)
    rows, _ = rolling("pncp", new, max_age_days=90)
    log.info("PNCP new %d, open %d", len(new), len(rows))
    return rows, {"new": len(new)}
