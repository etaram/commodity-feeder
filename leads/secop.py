"""Colombia: SECOP II processes (datos.gov.co Socrata open data): every process still open, all sizes (owner,
13 Nov 2026: every segment; the value stays on the row and the panel filters by it). UNSPSC category gives the
sector. Paged with $offset; a small cache reads the last 60 days, later runs the last 3."""
import datetime as dt

from .common import CACHE, cache_empty, clean, log, rolling, session, today
from .sectors import classify

URL = "https://www.datos.gov.co/resource/p6dx-8zbt.json"
PAGE = 5000
MAX_PAGES = 40


def fetch():
    s, t = session(), today()
    small = cache_empty("secop") or (CACHE / "secop.jsonl").stat().st_size < 5_000_000
    days = 60 if small else 3
    since = (t - dt.timedelta(days=days)).isoformat()
    where = (f"fecha_de_publicacion_del >= '{since}T00:00:00' "
             f"AND estado_de_apertura_del_proceso = 'Abierto'")
    got = []
    for page in range(MAX_PAGES):
        r = s.get(URL, params={"$where": where, "$limit": PAGE, "$offset": page * PAGE,
                               "$order": "fecha_de_publicacion_del DESC, id_del_proceso"}, timeout=120)
        if r.status_code != 200:
            log.warning("SECOP %s %s", r.status_code, r.text[:200]); break
        batch = r.json()
        got += batch
        if len(batch) < PAGE:
            break
    new = []
    for n in got:
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
    rows, _ = rolling("secop", new, max_age_days=120)
    log.info("SECOP window %d days, read %d, new %d, open %d", days, len(got), len(new), len(rows))
    return rows, {"new": len(new)}
