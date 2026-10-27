"""US federal opportunities (SAM.gov public search, no key): active solicitations matched by commodity keywords."""
import re

from .common import clean, log, polite, session, today
from .taxonomy import GROUPS, group_of_text

URL = "https://sam.gov/api/prod/sgs/v1/search/"
TYPES = {"o": "Solicitation", "k": "Combined Synopsis/Solicitation", "p": "Presolicitation", "r": "Sources Sought"}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def fetch():
    s = session(); s.headers["Accept"] = "application/hal+json"
    t = str(today()); rows, seen = [], set()
    for g in GROUPS:
        for kw in g["kw"]:
            try:
                r = s.get(URL, params={"index": "opp", "page": 0, "size": 100, "sort": "-modifiedDate",
                                       "mode": "search", "is_active": "true", "q": f'"{kw}"'}, timeout=60)
                res = r.json().get("_embedded", {}).get("results", [])
            except Exception as e:  # noqa: BLE001
                log.warning("SAM %s: %s", kw, e); continue
            for o in res:
                if o.get("_id") in seen or (o.get("type") or {}).get("code") not in TYPES:
                    continue
                title = clean(o.get("title"))
                if group_of_text(title) != g["id"]:
                    continue
                dl = (o.get("responseDate") or "")[:10]
                if dl and dl < t:
                    continue
                seen.add(o["_id"])
                org = o.get("organizationHierarchy") or []
                desc = " ".join(d.get("content", "") for d in o.get("descriptions") or [])
                em = EMAIL.search(desc)
                rows.append({
                    "id": f"SAM-{o['_id']}", "source": "SAM.gov (USA)", "group": g["id"], "country": "USA",
                    "buyer": clean(" / ".join(x.get("name", "") for x in (org[:1] + org[-1:])), 120),
                    "title": title[:300], "classification": f"keyword: {kw}",
                    "notice_type": TYPES[o["type"]["code"]], "published": (o.get("publishDate") or "")[:10],
                    "deadline": dl, "value": "", "currency": "",
                    "link": f"https://sam.gov/opp/{o['_id']}/view", "contact": em.group(0) if em else "", "match": "",
                })
            polite(0.7)
    log.info("SAM rows %d", len(rows))
    return rows, {}
