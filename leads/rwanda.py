"""Rwanda: Umucyo e-procurement, advertised tenders (all procuring entities). ICB = international competitive bidding,
open to foreign suppliers; NCB = national. Each listed tender carries its reference, name, deadline, method and type."""
import datetime as dt
import html
import re

from .common import clean, log, polite, rolling, today
from .sectors import classify

URL = "https://www.umucyo.gov.rw/eb/bav/selectListAdvertisingListForGU.do"
TYPE = {"G": "goods", "W": "works", "NC": "services", "C": "services"}
RADIO = re.compile(r'name="tenderNo"\s+class="radio"\s+value="([^"]+)"')
SHOWN = re.compile(r"fn_moveclari\('([^']+)','[^']*','([^']+)'\)")


def _date(s):
    try:
        return dt.datetime.strptime(s.strip()[:10], "%d/%m/%Y").date().isoformat()
    except ValueError:
        return ""


def fetch():
    from curl_cffi import requests as cr
    s = cr.Session(impersonate="chrome")
    for i in range(3):  # the portal's DNS answers slowly from some networks
        try:
            s.get(URL, timeout=60); break
        except Exception as e:  # noqa: BLE001
            log.warning("Rwanda connect %d: %s", i + 1, str(e)[:120]); polite(20)
    else:
        rows, _ = rolling("rwanda", [])
        return rows, {"new": 0, "error": "unreachable"}
    t, new, seen, page = str(today()), [], set(), 1
    while page <= 40:
        r = s.post(URL, data={"currentPageNo": page, "recordCountPerPage": 50, "searchConditions": ""}, timeout=60)
        if r.status_code != 200:
            log.warning("Rwanda %s page %d", r.status_code, page); break
        body = r.text
        shown = {a: b for a, b in SHOWN.findall(body)}  # internal ref -> reference as published (ends with the entity)
        got = 0
        for v in RADIO.findall(body):
            p = html.unescape(v).split("|")
            if len(p) < 9 or p[0] in seen:
                continue
            seen.add(p[0]); got += 1
            ref, name, dl, method, typ = p[0], clean(p[1]), _date(p[3]), p[5], p[6]
            if dl and dl < t:
                continue
            pub_ref = shown.get(ref, ref)
            entity = pub_ref.rsplit("/", 1)[-1] if "/" in pub_ref else ""
            sector, how = classify(name)
            new.append({
                "id": "RW-" + re.sub(r"[^\w]", "", ref)[:40], "source": "Umucyo (Rwanda)", "group": "", "sector": sector,
                "nature": TYPE.get(typ, ""), "cpv": "", "classification": how, "country": "RWA", "buyer": clean(entity, 120),
                "title": name[:300], "notice_type": f"{method} {pub_ref}"[:60], "stage": "tender",
                "access": "International (ICB)" if method == "ICB" else "National (NCB)",
                "published": "", "deadline": dl, "value": "", "currency": "",
                "link": "https://www.umucyo.gov.rw/eb/bav/selectListAdvertisingListForGU.do", "lang": "", "contact": "",
            })
        if got == 0:
            break
        page += 1
        polite(1.5)
    rows, _ = rolling("rwanda", new)
    log.info("Rwanda new %d, open %d (pages %d)", len(new), len(rows), page)
    return rows, {"new": len(new)}
