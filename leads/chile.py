"""Chile - Mercado Publico (ChileCompra) open public tenders, official API (api.mercadopublico.cl).
Needs a ticket (free, request at api.mercadopublico.cl); set the CHILE_TICKET secret. Without it the public demo ticket is
used, which is rate limited, so only the list is read. Keeps the larger tender types (LE, LP, LQ, LR) that a foreign
supplier can bid on; small L1 purchases are skipped. Rolling store."""
import datetime as dt
import os
import re

from .common import clean, log, polite, rolling, session, today
from .sectors import classify

API = "https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json"
DEMO = "F8537A18-6766-4DEF-9E59-426B4FEE2844"
KEEP = re.compile(r"-(LE|LP|LQ|LR)\d{2}$")
DETAIL_PER_RUN = 120


def _get(s, params, tries=6):
    for i in range(tries):
        r = s.get(API, params=params, timeout=90)
        if r.status_code == 200:
            j = r.json()
            if isinstance(j, dict) and j.get("Codigo") and "Listado" not in j:  # API-level error such as "simultaneous requests"
                log.info("Chile API said: %s", str(j.get("Mensaje"))[:120]); polite(8 * (i + 1)); continue
            return j
        if r.status_code == 429 or "peticiones simult" in r.text:
            polite(5 * (i + 1)); continue
        r.raise_for_status()
    return None


def fetch():
    ticket = os.environ.get("CHILE_TICKET") or DEMO
    s, t = session(), today()
    lst = _get(s, {"estado": "activas", "ticket": ticket})
    items = [x for x in (lst or {}).get("Listado", []) if KEEP.search(str(x.get("CodigoExterno", "")))]
    log.info("Chile: %d active, %d of kept types", (lst or {}).get("Cantidad", 0), len(items))
    new, n_det = [], 0
    for x in items:
        code = x["CodigoExterno"]
        dl = (x.get("FechaCierre") or "")[:10]
        if dl and dl < str(t):
            continue
        buyer, value, cur, pub = "Chile public buyer", "", "", str(t)
        if n_det < DETAIL_PER_RUN and ticket != DEMO or n_det < 25:
            try:
                d = _get(s, {"codigo": code, "ticket": ticket})
                it = ((d or {}).get("Listado") or [{}])[0]
                comp = it.get("Comprador") or {}
                buyer = clean(comp.get("NombreOrganismo") or buyer)
                if it.get("MontoEstimado"):
                    value, cur = str(it["MontoEstimado"]), it.get("Moneda") or "CLP"
                pub = (it.get("Fechas") or {}).get("FechaPublicacion", "")[:10] or pub
                n_det += 1; polite(1.2)
            except Exception as e:  # noqa: BLE001
                log.warning("Chile detail %s: %s", code, str(e)[:100])
        title = clean(x.get("Nombre") or "")
        sector, method = classify(title)
        new.append({
            "id": "CL-" + code, "source": "ChileCompra", "group": "", "sector": sector, "nature": "", "cpv": "", "classification": method,
            "country": "CHL", "buyer": buyer, "title": title[:300], "notice_type": "Licitacion publica", "stage": "tender",
            "access": "Open (Chile Mercado Publico; foreign suppliers register at ChileProveedores)", "published": pub, "deadline": dl,
            "value": value, "currency": cur, "link": f"https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={code}",
            "contact": "", "lang": "es",
        })
    rows, _ = rolling("chile", new)
    log.info("Chile new %d, open %d, details %d", len(new), len(rows), n_det)
    return rows, {"new": len(new)}
