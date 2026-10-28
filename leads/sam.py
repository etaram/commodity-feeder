"""US federal opportunities (SAM.gov public search, no key): every active solicitation, newest changes first, with
a rolling cache. Sector from the Federal Supply Class / service code that prefixes many titles (e.g. '61--CABLE'),
else by keyword."""
import datetime as dt
import re

from .common import cache_empty, clean, log, polite, rolling, session, today
from .sectors import classify
from .taxonomy import group_of_text

URL = "https://sam.gov/api/prod/sgs/v1/search/"
TYPES = {"o": "Solicitation", "k": "Combined Synopsis/Solicitation", "p": "Presolicitation", "r": "Sources Sought"}
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
FSC = {"10": "DEFENCE", "11": "DEFENCE", "12": "DEFENCE", "13": "DEFENCE", "14": "DEFENCE", "15": "TRANSPORT_EQ",
       "16": "TRANSPORT_EQ", "17": "TRANSPORT_EQ", "19": "TRANSPORT_EQ", "20": "TRANSPORT_EQ", "22": "TRANSPORT_EQ",
       "23": "TRANSPORT_EQ", "24": "MACHINERY", "25": "TRANSPORT_EQ", "26": "TRANSPORT_EQ", "28": "MACHINERY",
       "29": "TRANSPORT_EQ", "30": "MACHINERY", "31": "MACHINERY", "32": "MACHINERY", "34": "MACHINERY",
       "35": "MACHINERY", "36": "MACHINERY", "37": "MACHINERY", "38": "MACHINERY", "39": "MACHINERY",
       "40": "MACHINERY", "41": "MACHINERY", "42": "DEFENCE", "43": "MACHINERY", "44": "MACHINERY",
       "45": "CONSTR_MAT", "46": "WATER", "47": "CONSTR_MAT", "48": "CONSTR_MAT", "49": "MAINT", "51": "MACHINERY",
       "52": "LAB", "53": "MACHINERY", "54": "CONSTR_MAT", "55": "CONSTR_MAT", "56": "CONSTR_MAT", "58": "ICT",
       "59": "POWER", "60": "ICT", "61": "POWER", "62": "POWER", "63": "DEFENCE", "65": "HEALTH", "66": "LAB",
       "67": "ICT", "68": "CHEMICALS", "69": "SOCIAL", "70": "ICT", "71": "CONSUMER", "72": "CONSUMER",
       "73": "CONSUMER", "74": "CONSUMER", "75": "CONSUMER", "76": "CONSUMER", "77": "CONSUMER", "78": "CONSUMER",
       "79": "ENV_WASTE", "80": "CHEMICALS", "81": "CONSUMER", "83": "TEXTILES", "84": "TEXTILES", "85": "CONSUMER",
       "87": "AGRI_FOOD", "88": "AGRI_FOOD", "89": "AGRI_FOOD", "91": "ENERGY", "93": "CHEMICALS", "94": "MINING_METALS",
       "95": "MINING_METALS", "96": "MINING_METALS", "99": "CONSUMER",
       "A": "CONSULTING", "B": "CONSULTING", "C": "ENGINEERING", "D": "ICT", "E": "BUILDING", "F": "ENV_WASTE",
       "G": "SOCIAL", "H": "LAB", "J": "MAINT", "K": "MAINT", "L": "CONSULTING", "M": "MAINT", "N": "MAINT",
       "P": "ENV_WASTE", "Q": "HEALTH", "R": "CONSULTING", "S": "ENV_WASTE", "T": "CONSULTING", "U": "SOCIAL",
       "V": "LOGISTICS", "W": "MACHINERY", "X": "BUILDING", "Y": "BUILDING", "Z": "MAINT"}
CODE = re.compile(r"^\s*([0-9]{2}|[A-Z][0-9A-Z]{0,3})\s*-{1,2}")


def _sector(title):
    m = CODE.match(title)
    if m:
        c = m.group(1)
        s = FSC.get(c[:2]) if c[:2].isdigit() else FSC.get(c[0])
        if s:
            return s, f"FSC {c}"
    return classify(title)


def fetch():
    s = session(); s.headers["Accept"] = "application/hal+json"
    t = today()
    cut = str(t - dt.timedelta(days=21 if cache_empty("sam") else 3))
    new, page = [], 0
    while page < 100:
        try:
            r = s.get(URL, params={"index": "opp", "page": page, "size": 100, "sort": "-modifiedDate",
                                   "mode": "search", "is_active": "true"}, timeout=60)
            res = r.json().get("_embedded", {}).get("results", [])
        except Exception as e:  # noqa: BLE001
            log.warning("SAM page %d: %s", page, e); break
        if not res:
            break
        for o in res:
            if (o.get("type") or {}).get("code") not in TYPES:
                continue
            dl = (o.get("responseDate") or "")[:10]
            if dl and dl < str(t):
                continue
            title = clean(o.get("title"))
            org = o.get("organizationHierarchy") or []
            desc = " ".join(d.get("content", "") for d in o.get("descriptions") or [])
            em = EMAIL.search(desc)
            sector, method = _sector(title)
            new.append({
                "id": f"SAM-{o['_id']}", "source": "SAM.gov (USA)", "group": group_of_text(title) or "",
                "sector": sector, "nature": "", "cpv": "", "country": "USA",
                "buyer": clean(" / ".join(dict.fromkeys(x.get("name") or "" for x in (org[:1] + org[-1:]))), 120),
                "title": title[:300], "classification": method, "notice_type": TYPES[o["type"]["code"]],
                "stage": "planned" if o["type"]["code"] in ("p", "r") else "tender",
                "access": "US (Buy American / TAA; GPA for covered agencies)",
                "published": (o.get("publishDate") or "")[:10], "deadline": dl, "value": "", "currency": "",
                "link": f"https://sam.gov/opp/{o['_id']}/view", "contact": em.group(0) if em else "", "lang": "",
            })
        if (res[-1].get("modifiedDate") or "")[:10] < cut:
            break
        page += 1
        polite(0.5)
    rows, _ = rolling("sam", new)
    log.info("SAM new %d, open %d (pages %d)", len(new), len(rows), page + 1)
    return rows, {"new": len(new)}
