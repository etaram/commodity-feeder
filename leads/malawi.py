"""Malawi: PPDA procurement notices (ppda.mw/tenders): title, institution, reference, publish and closing dates."""
import html
import re

from .common import clean, log, rolling, today
from .sectors import classify

URL = "https://www.ppda.mw/tenders"
TR = re.compile(r"<tr>\s*(<td.*?)</tr>", re.S)
TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)


def fetch():
    from curl_cffi import requests as cr
    s = cr.Session(impersonate="chrome")
    t, new = str(today()), []
    for page in range(1, 6):
        try:
            r = s.get(URL, params={"page": page} if page > 1 else None, timeout=60)
        except Exception as e:  # noqa: BLE001
            log.warning("Malawi page %d: %s", page, str(e)[:120]); break
        if r.status_code != 200:
            break
        got = 0
        for tr in TR.findall(r.text):
            tds = TD.findall(tr)
            if len(tds) < 5:
                continue
            title, inst, ref, pub, dl = (clean(html.unescape(re.sub(r"<[^>]+>", " ", x))) for x in tds[:5])
            doc = re.search(r'href="([^"]+)"', tds[5]) if len(tds) > 5 else None
            got += 1
            if not re.match(r"\d{4}-\d\d-\d\d", dl) or dl < t:
                continue
            sector, how = classify(title)
            new.append({
                "id": "MW-" + re.sub(r"[^\w]", "", ref or title)[:50], "source": "PPDA (Malawi)", "group": "", "sector": sector,
                "nature": "", "cpv": "", "classification": how, "country": "MWI", "buyer": inst[:120], "title": title[:300],
                "notice_type": ref[:60], "stage": "tender", "access": "Open (check eligibility in the bidding document)",
                "published": pub, "deadline": dl, "value": "", "currency": "",
                "link": doc.group(1).replace(" ", "%20") if doc else URL, "lang": "", "contact": "",
            })
        if got == 0 or "page=" + str(page + 1) not in r.text:
            break
    rows, _ = rolling("malawi", new)
    log.info("Malawi new %d, open %d", len(new), len(rows))
    return rows, {"new": len(new)}
