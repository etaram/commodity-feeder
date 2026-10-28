"""Qatar: Monaqasat (state procurement portal) - open ministry and government-entity tenders. Arabic.
Value is estimated from the published bid bond (temporary guarantee), taken as 2% of contract value."""
import datetime as dt
import html
import re

from .common import chain_session, clean, log, polite, rolling, today
from .etimad import _sector

BASE = "https://monaqasat.mof.gov.qa"
URL = BASE + "/TendersOnlineServices/AvailableMinistriesTenders/{}"


def _d(s):
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", s or "")
    return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def fetch():
    s, t, new = chain_session(BASE), today(), []
    for page in range(1, 40):
        r = s.get(URL.format(page), timeout=60)
        if r.status_code != 200:
            log.warning("Qatar %s p%d", r.status_code, page); break
        ids = re.findall(r"/TendersOnlineServices/TenderDetails/(\d+)", r.text)
        txt = re.sub(r"<script.*?</script>|<style.*?</style>", "", r.text, flags=re.S)
        segs = [clean(html.unescape(x)) for x in re.split(r"<[^>]+>", txt)]
        segs = [x for x in segs if x]
        starts = [i for i, x in enumerate(segs) if re.fullmatch(r"\d{1,6}/20\d\d", x)]
        if not starts:
            break
        ids = list(dict.fromkeys(ids))
        for k, i in enumerate(starts):
            block = segs[i:(starts[k + 1] if k + 1 < len(starts) else i + 30)]
            def after(label):
                return block[block.index(label) + 1] if label in block and block.index(label) + 1 < len(block) else ""
            ref, title = block[0], block[1] if len(block) > 1 else ""
            close = _d(after("تاريخ الإغلاق"))
            if close and close < t:
                continue
            bond = after("التأمين المؤقت (رق)").replace(",", "")
            ent = after("الجهة")
            try:
                est = round(float(bond) * 50) if bond else ""
            except ValueError:
                est = ""
            new.append({
                "id": f"QA-{ref.replace('/', '-')}", "source": "Monaqasat (Qatar)", "group": "",
                "sector": _sector(title, ent), "nature": "", "cpv": "",
                "classification": f"bid bond QAR {bond}" if bond else "", "country": "QAT", "buyer": ent[:120],
                "title": title[:300], "notice_type": after("النوع")[:40], "stage": "tender",
                "access": "National (Qatari CR / local partner)", "published": str(_d(after("تاريخ الطرح")) or ""),
                "deadline": str(close or ""), "value": est, "currency": "QAR" if est else "",
                "link": f"{BASE}/TendersOnlineServices/TenderDetails/{ids[k]}" if k < len(ids) else URL.format(page),
                "contact": "", "lang": "ar",
            })
        polite(1)
    rows, _ = rolling("qatar", new)
    log.info("Qatar new %d, open %d", len(new), len(rows))
    return rows, {"new": len(new)}
