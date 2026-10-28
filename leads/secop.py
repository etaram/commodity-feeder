"""Colombia: SECOP II processes (datos.gov.co Socrata open data), open processes above MIN_COP published recently.
UNSPSC category gives the sector."""
import datetime as dt

from .common import cache_empty, clean, log, rolling, session, today
from .sectors import classify

URL = "https://www.datos.gov.co/resource/p6dx-8zbt.json"
MIN_COP = 2_000_000_000  # ~ USD 0.5M


def fetch():
    s, t = session(), today()
    days = 21 if cache_empty("secop") else 3
    since = (t - dt.timedelta(days=days)).isoformat()
    where = (f"fecha_de_publicacion_del >= '{since}T00:00:00' AND precio_base > {MIN_COP} "
             f"AND estado_de_apertura_del_proceso = 'Abierto'")
    r = s.get(URL, params={"$where": where, "$limit": 5000, "$order": "fecha_de_publicacion_del DESC"}, timeout=120)
    if r.status_code != 200:
        log.warning("SECOP %s %s", r.status_code, r.text[:200]); return [], {}
    new = []
    for n in r.json():
        if (n.get("estado_del_procedimiento") or "") in ("Cancelado", "Adjudicado", "Desierto", "Cerrado"):
            continue
        dl = (n.get("fecha_de_recepcion_de") or n.get("fecha_de_apertura_de_respuesta") or "")[:10]
        if dl and dl < str(t):
            continue
        text = clean(f"{n.get('nombre_del_procedimiento', '')} - {n.get('descripci_n_del_procedimiento', '')}")
        cat = (n.get("codigo_principal_de_categoria") or "").replace("V1.", "")
        sector, method = classify(text, unspsc=cat)
        url = (n.get("urlproceso") or {}).get("url", "")
        new.append({
            "id": f"SECOP-{n.get('id_del_proceso')}", "source": "SECOP II (Colombia)", "group": "", "sector": sector,
            "nature": "", "cpv": "", "classification": f"UNSPSC {cat}" if cat else method, "country": "COL",
            "buyer": clean(n.get("entidad"), 120), "title": text[:300], "notice_type": clean(n.get("modalidad_de_contratacion")),
            "stage": "tender", "access": "National (foreign firms may bid)", "published": (n.get("fecha_de_publicacion_del") or "")[:10],
            "deadline": dl, "value": round(float(n.get("precio_base") or 0)) or "", "currency": "COP",
            "link": url, "contact": "", "lang": "es",
        })
    rows, _ = rolling("secop", new, max_age_days=90)
    log.info("SECOP new %d, open %d", len(new), len(rows))
    return rows, {"new": len(new)}
