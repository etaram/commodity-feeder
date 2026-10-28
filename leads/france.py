"""France: BOAMP (Bulletin officiel des annonces des marchés publics) open data API - all contract notices,
national and EU-threshold, with buyer, deadline, market type and descriptor."""
import datetime as dt

from .common import cache_empty, clean, log, polite, rolling, session, today
from .sectors import classify

URL = "https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/records"
NATURE = {"TRAVAUX": "works", "FOURNITURES": "goods", "SERVICES": "services"}


def _first(v):
    s = str(v or "").strip("[]'\" ")
    return s.split("', '")[0]


def fetch():
    s, t = session(), today()
    days = 21 if cache_empty("france") else 3
    since = (t - dt.timedelta(days=days)).isoformat()
    where = f"dateparution >= date'{since}' AND nature = 'APPEL_OFFRE' AND datelimitereponse >= date'{t}'"
    new, offset = [], 0
    while offset < 9900:
        r = s.get(URL, params={"where": where, "limit": 100, "offset": offset, "order_by": "dateparution desc",
                               "select": "idweb,objet,dateparution,datelimitereponse,nomacheteur,type_marche,"
                                         "descripteur_libelle,procedure_libelle,famille_libelle,code_departement,url_avis"},
                  timeout=90)
        if r.status_code != 200:
            log.warning("BOAMP %s %s", r.status_code, r.text[:200]); break
        res = r.json().get("results") or []
        if not res:
            break
        for x in res:
            desc = clean(" ".join(x.get("descripteur_libelle") or []) if isinstance(x.get("descripteur_libelle"), list) else _first(x.get("descripteur_libelle")))
            tm = x.get("type_marche"); tm = tm[0] if isinstance(tm, list) and tm else _first(tm)
            title = clean(x.get("objet"))
            sector, method = classify(f"{title} {desc}")
            new.append({
                "id": f"FR-{x.get('idweb')}", "source": "BOAMP (France)", "group": "", "sector": sector,
                "nature": NATURE.get(tm, ""), "cpv": "", "classification": desc[:60] or method, "country": "FRA",
                "buyer": clean(x.get("nomacheteur"), 120), "title": title[:300],
                "notice_type": clean(f"{x.get('procedure_libelle') or ''} ({x.get('famille_libelle') or ''})", 60),
                "stage": "tender", "access": "GPA/EU open" if "europ" in (x.get("famille_libelle") or "").lower() else "National (EU firms; others case by case)",
                "published": x.get("dateparution") or "", "deadline": (x.get("datelimitereponse") or "")[:10],
                "value": "", "currency": "", "link": x.get("url_avis") or "", "contact": "", "lang": "fr",
            })
        offset += 100
        polite(0.3)
    rows, _ = rolling("france", new)
    log.info("BOAMP new %d, open %d", len(new), len(rows))
    return rows, {"new": len(new)}
