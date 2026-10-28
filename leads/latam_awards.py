"""Latin American contract awards for the Supplier Universe:
  Brazil  - PNCP contracts (company suppliers, CNPJ), current days + back-fill
  Colombia - SECOP II contracts (company suppliers, NIT) above ~USD 120k, last 12 months
Award rows go to data/leads/awards/<source>/; supplier IDs go to the private contacts cache."""
import datetime as dt
import time

from .common import PRIVATE, award_days, clean, log, polite, save_awards, session, today
from .sectors import classify

PNCP = "https://pncp.gov.br/api/consulta/v1/contratos"
SECOP = "https://www.datos.gov.co/resource/jbjy-vk9h.json"
CAT = {"Compras": "goods", "Obras": "works", "Serviços": "services"}


def _brazil(s, day, budget_end):
    rows, page = [], 1
    d = day.strftime("%Y%m%d")
    while page <= 400 and time.time() < budget_end:
        r = s.get(PNCP, params={"dataInicial": d, "dataFinal": d, "pagina": page, "tamanhoPagina": 50}, timeout=90)
        if r.status_code == 429:
            polite(20); continue
        if r.status_code != 200:
            break
        j = r.json()
        for c in j.get("data") or []:
            if c.get("tipoPessoa") != "PJ":
                continue
            v = c.get("valorGlobal") or c.get("valorInicial") or 0
            if v < 150_000:
                continue
            org = c.get("orgaoEntidade") or {}
            text = clean(c.get("objetoContrato"), 300)
            sec, _ = classify(text)
            name = clean(c.get("nomeRazaoSocialFornecedor"), 120)
            rows.append({
                "id": f"BRC-{c.get('numeroControlePNCP')}", "source": "Brazil PNCP", "group": "", "sector": sec,
                "title": text[:200], "buyer": clean(org.get("razaoSocial"), 120), "country": "BRA", "cpv": "",
                "published": (c.get("dataAssinatura") or c.get("dataPublicacaoPncp") or str(day))[:10],
                "winners": [name], "winner_country": "BRA", "winner_size": "", "value": float(v), "currency": "BRL",
                "bids": "", "email": "", "link": "",
                "contacts": [{"name": name, "country": "BRA", "legal_id": f"CNPJ:{c.get('niFornecedor')}", "email": "",
                              "phone": "", "website": "", "address": ""}],
            })
        if j.get("paginasRestantes", 0) <= 0:
            break
        page += 1
        polite(0.6)
    return rows


def _colombia(s, since):
    rows, offset = [], 0
    where = (f"valor_del_contrato > 500000000 AND tipodocproveedor='NIT' AND fecha_de_firma >= '{since}T00:00:00'")
    while offset < 60000:
        r = s.get(SECOP, params={"$where": where, "$limit": 5000, "$offset": offset, "$order": "fecha_de_firma DESC",
                                 "$select": "id_contrato,nombre_entidad,descripcion_del_proceso,objeto_del_contrato,"
                                            "tipo_de_contrato,documento_proveedor,proveedor_adjudicado,valor_del_contrato,"
                                            "fecha_de_firma,codigo_de_categoria_principal,urlproceso"}, timeout=180)
        if r.status_code != 200:
            log.warning("SECOP contracts %s %s", r.status_code, r.text[:200]); break
        batch = r.json()
        for c in batch:
            text = clean(c.get("objeto_del_contrato") or c.get("descripcion_del_proceso"), 300)
            cat = (c.get("codigo_de_categoria_principal") or "").replace("V1.", "")
            sec, _ = classify(text, unspsc=cat)
            name = clean(c.get("proveedor_adjudicado"), 120)
            rows.append({
                "id": f"COC-{c.get('id_contrato')}", "source": "Colombia SECOP", "group": "", "sector": sec,
                "title": text[:200], "buyer": clean(c.get("nombre_entidad"), 120), "country": "COL", "cpv": "",
                "published": (c.get("fecha_de_firma") or "")[:10], "winners": [name], "winner_country": "COL",
                "winner_size": "", "value": float(c.get("valor_del_contrato") or 0), "currency": "COP", "bids": "",
                "email": "", "link": ((c.get("urlproceso") or {}).get("url") if isinstance(c.get("urlproceso"), dict) else ""),
                "contacts": [{"name": name, "country": "COL", "legal_id": f"NIT:{c.get('documento_proveedor')}",
                              "email": "", "phone": "", "website": "", "address": ""}],
            })
        if len(batch) < 5000:
            break
        offset += 5000
    return rows


def fetch():
    s, t = session(), today()
    t_end = time.time() + 900
    # Brazil: yesterday + back-fill 3 older days per run (12 months)
    have = award_days("brazil")
    days = [t - dt.timedelta(days=1)] + [t - dt.timedelta(days=k) for k in range(2, 366)
                                         if str(t - dt.timedelta(days=k)) not in have][:3]
    br = 0
    for d in days:
        rows = _brazil(s, d, t_end)
        save_awards("brazil", rows or [{"id": f"empty-{d}", "published": str(d), "empty": True}]); br += len(rows)
    # Colombia: 12 months on the first run, then the last 10 days
    first = not award_days("colombia")
    co = _colombia(s, str(t - dt.timedelta(days=365 if first else 10)))
    save_awards("colombia", co)
    log.info("LatAm awards: Brazil %d (%d days), Colombia %d", br, len(days), len(co))
    return [], {"brazil": br, "colombia": len(co)}
