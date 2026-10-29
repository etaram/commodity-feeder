"""US federal opportunities (SAM.gov public search, no key): every active solicitation, newest changes first, with
a rolling cache. Sector from the Federal Supply Class / service code that prefixes many titles (e.g. '61--CABLE'),
else by keyword."""
import datetime as dt
import json
import re

from .common import CACHE, cache_empty, clean, log, polite, rolling, session, today
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


SET_ASIDES = ["SBA", "SBP", "8A", "8AN", "HZC", "HZS", "SDVOSBC", "SDVOSBS", "WOSB", "WOSBSS", "EDWOSB", "EDWOSBSS",
              "LAS", "IEE", "ISBEE", "BICiv", "VSA", "VSS"]
STATE = CACHE / "sam_state.json"


def _tz_country():
    """IANA time zone -> ISO3 country, from the system zone table (the response time zone tells where an overseas
    US contracting office buys: Europe/Berlin, Asia/Jerusalem ...)."""
    out = {}
    for f in ("/usr/share/zoneinfo/zone1970.tab", "/usr/share/zoneinfo/zone.tab"):
        try:
            for line in open(f, encoding="utf-8"):
                if line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 3:
                    cc = parts[0].split(",")[0]
                    out.setdefault(parts[2].strip(), cc)
        except OSError:
            continue
    try:
        import pycountry
        return {tz: (pycountry.countries.get(alpha_2=cc).alpha_3 if pycountry.countries.get(alpha_2=cc) else "")
                for tz, cc in out.items()}
    except Exception:  # noqa: BLE001
        return {}


def _pages(s, params, max_pages=100):
    for page in range(max_pages):
        try:
            r = s.get(URL, params={"index": "opp", "page": page, "size": 100, "mode": "search", "is_active": "true",
                                   **params}, timeout=60)
            j = r.json()
        except Exception as e:  # noqa: BLE001
            log.warning("SAM %s page %d: %s", params, page, e); return
        res = j.get("_embedded", {}).get("results", [])
        if not res:
            return
        yield res
        tot = (j.get("page") or {}).get("totalPages", 0)
        if page + 1 >= min(tot, 100):
            return
        polite(0.4)


def _row(o, t, aside, tzc):
    if (o.get("type") or {}).get("code") not in TYPES or o.get("isCanceled"):
        return None
    dl = (o.get("responseDate") or "")[:10]
    if dl and dl < str(t):
        return None
    title = clean(o.get("title"))
    org = o.get("organizationHierarchy") or []
    desc = " ".join(d.get("content") or "" for d in o.get("descriptions") or [])
    em = EMAIL.search(desc)
    sector, method = _sector(title)
    orgs = " ".join(x.get("name") or "" for x in org).upper()
    if not sector and re.search(r"DEFENSE|ARMY|NAVY|AIR FORCE|MARINE CORPS|SPACE FORCE", orgs):
        sector, method = "DEFENCE", "military buyer"
    tz = o.get("responseTimeZone") or ""
    pop = tzc.get(tz, "") if tz and not tz.startswith(("America/", "Pacific/", "US/")) else ""
    code = aside.get(o["_id"])
    if code:
        access = f"US set-aside ({code}): US small businesses only"
    elif pop and pop != "USA":
        access = "International: US agency buying abroad, open to local and international firms"
    else:
        access = "US full and open competition, open to foreign firms (TAA/GPA: Israeli products eligible)"
    return {
        "id": f"SAM-{o['_id']}", "source": "SAM.gov (USA)", "group": group_of_text(title) or "",
        "sector": sector, "nature": "", "cpv": "", "country": pop if pop and pop != "USA" else "USA",
        "buyer": clean(" / ".join(dict.fromkeys(x.get("name") or "" for x in (org[:1] + org[-1:]))), 120),
        "title": title[:300], "classification": method, "notice_type": TYPES[o["type"]["code"]] + (f" | set-aside {code}" if code else ""),
        "stage": "planned" if o["type"]["code"] in ("p", "r") else "tender", "access": access,
        "published": (o.get("publishDate") or "")[:10], "deadline": dl, "value": "", "currency": "",
        "link": f"https://sam.gov/opp/{o['_id']}/view", "contact": em.group(0) if em else "", "lang": "",
    }


def fetch():
    """Daily full sweep of every active solicitation (all four notice types, combined synopses split by response-date
    week to stay under the 10,000-result cap) plus small-business set-aside tagging; incremental runs in between."""
    s = session(); s.headers["Accept"] = "application/hal+json"
    t = today()
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    full = cache_empty("sam") or st.get("full_sweep") != str(t)
    aside = st.get("set_aside", {}) if not full else {}
    tzc = _tz_country()
    if full:
        for code in SET_ASIDES:
            for res in _pages(s, {"set_aside": code}):
                for o in res:
                    aside[o["_id"]] = code
        log.info("SAM set-aside notices: %d", len(aside))
    new = []
    if full:
        for typ in ("o", "p", "r"):
            for res in _pages(s, {"notice_type": typ, "sort": "-modifiedDate"}):
                new += [x for x in (_row(o, t, aside, tzc) for o in res) if x]
        for w in range(0, 420, 7):
            a, b = t + dt.timedelta(days=w - 1), t + dt.timedelta(days=w + 6)
            for res in _pages(s, {"notice_type": "k", "response_date.from": f"{a}-05:00", "response_date.to": f"{b}-05:00"}):
                new += [x for x in (_row(o, t, aside, tzc) for o in res) if x]
        (CACHE / "sam.jsonl").unlink(missing_ok=True)  # rebuild: drops cancelled and withdrawn notices
    else:
        cut = str(t - dt.timedelta(days=2))
        for res in _pages(s, {"sort": "-modifiedDate"}, max_pages=40):
            new += [x for x in (_row(o, t, aside, tzc) for o in res) if x]
            if (res[-1].get("modifiedDate") or "")[:10] < cut:
                break
    rows, _ = rolling("sam", new)
    if full:
        STATE.write_text(json.dumps({"full_sweep": str(t), "set_aside": aside}))
    open_ = sum(1 for r in rows if "set-aside" not in r["access"])
    log.info("SAM %s: fetched %d, open %d (%d open to foreign firms)", "full sweep" if full else "incremental",
             len(new), len(rows), open_)
    return rows, {"fetched": len(new), "set_aside": len(aside), "open_to_foreign": open_, "full": int(full)}
