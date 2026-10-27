"""Israel: Government Procurement Administration tender search (mr.gov.il), open notices by category."""
import datetime as dt
import html
import re
from urllib.parse import quote

from .common import cffi_get, clean, log, polite, today
from .taxonomy import GROUPS

BASE = "https://mr.gov.il"
ACTIVE = {"פורסם", "חדש", "עודכן", "בעדכון", "עתידי", "Published"}
FIELD = {"שם המפרסם": "buyer", "מס' פרסום": "pubno", "סטטוס": "status", "מס׳ הליך": "procno",
         "תאריך פרסום": "published", "תאריך עדכון": "updated", "מועד אחרון להגשה": "deadline"}


def _d(s):
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", s or "")
    return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def parse(page):
    out = []
    parts = re.split(r'<a href="/ilgstorefront/he/p/(\d+)">', page)
    for i in range(1, len(parts), 2):
        pid, body = parts[i], parts[i + 1][:6000]
        title = re.search(r"<h2[^>]*>(.*?)</h2>", body, re.S)
        kind = re.search(r'search-result-sub-head">([^<]+)<', parts[i - 1][-800:])
        text = re.sub(r"<[^>]+>", " ", html.unescape(body))
        text = re.sub(r"\s+", " ", text)
        rec = {"pid": pid, "title": clean(html.unescape(title.group(1))) if title else "",
               "kind": clean(kind.group(1)) if kind else ""}
        for lab, key in FIELD.items():
            m = re.search(re.escape(lab) + r":\s*(.*?)(?:\s\|\s|$| (?=[^\s]+ ?[^\s]*:))", text)
            if m:
                rec[key] = clean(m.group(1), 150)
        out.append(rec)
    return out


def fetch(max_pages=3):
    rows, seen, t = [], set(), today()
    for g in GROUPS:
        for cat in g["mr"]:
            for page in range(max_pages):
                q = quote(f":updateDate:archive:false:category:{cat}", safe=":")
                url = f"{BASE}/ilgstorefront/he/search/?q={q}&s=TENDER&page={page}"
                try:
                    r = cffi_get(url)
                except Exception as e:  # noqa: BLE001
                    log.warning("mr.gov.il %s: %s", cat, e); break
                items = parse(r.text) if r.status_code == 200 else []
                for it in items:
                    st = it.get("status", "").split(" ")[0]
                    if it["pid"] in seen or not any(it.get("status", "").startswith(a) for a in ACTIVE):
                        continue
                    dl = _d(it.get("deadline"))
                    if dl and dl < t:
                        continue
                    seen.add(it["pid"])
                    rows.append({
                        "id": f"MR-{it['pid']}", "source": "mr.gov.il (Israel)", "group": g["id"],
                        "country": "ISR", "buyer": it.get("buyer", ""), "title": it["title"][:300],
                        "classification": f"mr.gov.il category {cat}", "notice_type": f"{it.get('kind', '')} | {st}",
                        "published": str(_d(it.get("published")) or ""), "deadline": str(dl or ""),
                        "value": "", "currency": "", "link": f"{BASE}/ilgstorefront/he/p/{it['pid']}", "contact": "",
                    })
                polite(1.5)
                if len(items) < 20:
                    break
    log.info("mr.gov.il rows: %d", len(rows))
    return rows, {}
