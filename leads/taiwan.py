"""Taiwan Government e-Procurement System (web.pcc.gov.tw, Public Construction Commission): every tender notice now
within its bidding period (等標期內), from the public tender search: agency, case number, tender name, tendering
method, category (works / goods / services), notice date, bid deadline (截止投標, ROC calendar), budget, and the
link to the official notice.

Access (checked 2026-11-13 from the server): public, no sign-in, no CAPTCHA; 11,771 notices in the bidding period.
Rights note: the site's copyright statement allows reproduction for personal non-profit use and asks for consent for
other use. The owner decided on 13 Nov 2026 (21:04) to collect what is publicly visible; we keep facts only (who
buys what, by when, budget, official link), read politely (one page of 100 rows every 3 s), and link every row back
to its official notice. The decision and the statement are recorded in docs/team/rights_decisions.md."""
import datetime as dt
import html
import re
import time

from .common import clean, log, quarantine_future, session, snapshot, today
from .sectors import classify

BASE = "https://web.pcc.gov.tw"
LIST = (BASE + "/prkms/tender/common/basic/readTenderBasic?firstSearch=true&searchType=basic&isBinding=N&isLogIn=N"
        "&level_1=on&orgName=&orgId=&tenderName=&tenderId=&tenderType=TENDER_DECLARATION"
        "&tenderWay=TENDER_WAY_ALL_DECLARATION&dateType=isSpdt&tenderStartDate=&tenderEndDate=&radProctrgCate="
        "&policyAdvocacy=&pageSize=100&d-49738-p={page}")
MAX_PAGES = 200
TBODY = re.compile(r"<tbody>(.*?)</tbody>", re.S)
TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
NATURE = {"工程類": "works", "財物類": "goods", "勞務類": "services"}


def _txt(s):
    s = re.sub(r"<script.*?</script>", " ", s or "", flags=re.S)
    return clean(html.unescape(re.sub(r"<[^>]+>", " ", s)))


def roc(s):
    """'115/11/24' -> '2026-11-24' (ROC year + 1911); '' when not a date."""
    m = re.search(r"(\d{2,3})/(\d{1,2})/(\d{1,2})", s or "")
    if not m:
        return ""
    try:
        return str(dt.date(int(m.group(1)) + 1911, int(m.group(2)), int(m.group(3))))
    except ValueError:
        return ""


def parse(page, fetched):
    # the page has several tables (the search form comes first): use the body that holds notice links
    body = next((b for b in TBODY.findall(page) if "tpam?pk=" in b), None)
    if body is None:
        if "共有" in page and re.search(r"共有\s*<span[^>]*>\s*0\s*</span>", page):
            return []
        raise ValueError("Taiwan PCC: result table not found (page layout changed or error page)")
    rows = []
    for tr in TR.findall(body):
        tds = TD.findall(tr)
        if len(tds) < 9:
            continue
        org = _txt(tds[1])
        a = re.search(r'href="(/prkms/urlSelector/common/tpam\?pk=[^"]+)"', tds[2])
        t = re.search(r'pageCode2Img\("((?:[^"\\]|\\.)*)"\)', tds[2])
        title = clean(html.unescape(t.group(1))) if t else ""
        case_no = _txt(re.split(r"<br", tds[2])[0]).replace("(更正公告)", "").strip()
        dl = roc(_txt(tds[7]))
        if not org or not title or not case_no or not a:
            continue
        budget = re.sub(r"[^\d]", "", _txt(tds[8]))
        cat = _txt(tds[5])
        sector, how = classify(title)
        rows.append({"id": "TWN-" + re.sub(r"[^A-Za-z0-9]+", "-", f"{org[:20]}-{case_no}")[:90].strip("-"),
                     "source": "Taiwan Government e-Procurement (PCC)", "group": "", "sector": sector,
                     "nature": NATURE.get(cat, ""), "cpv": "", "classification": how, "country": "TWN", "buyer": org[:120],
                     "title": title[:300], "notice_type": _txt(tds[4])[:60] + (" (corrected notice)" if "更正公告" in tds[2] else ""),
                     "stage": "tender", "access": "Taiwan government procurement (foreign suppliers per tender terms; WTO GPA tenders open)",
                     "published": roc(_txt(tds[6])), "deadline": dl, "deadline_basis": "submission",
                     "value": int(budget) if budget else "", "currency": "TWD" if budget else "",
                     "link": BASE + html.unescape(a.group(1)), "source_url": BASE + "/prkms/tender/common/basic/indexTenderBasic",
                     "fetched": fetched, "contact": "", "lang": "zh"})
    return rows


def fetch():
    s = session()
    t = str(today())
    out, pages, total = [], 0, 0
    for page in range(1, MAX_PAGES + 1):
        r = s.get(LIST.format(page=page), timeout=60)
        r.raise_for_status()
        pages += 1
        if page == 1:
            m = re.search(r"共有\s*<span[^>]*>\s*([\d,]+)\s*</span>", r.text)
            total = int(m.group(1).replace(",", "")) if m else 0
        got = parse(r.text, t)
        if not got:
            break
        out += got
        if len(out) >= total or page * 100 >= total:
            break
        time.sleep(3)
    if not out:
        raise RuntimeError("Taiwan PCC: no rows read; previous snapshot kept")
    out, q = quarantine_future(out, "taiwan")
    out = list({x["id"]: x for x in out if x["deadline"] and x["deadline"] >= t}.values())
    complete = total and len(out) >= 0.9 * total
    keep, _ = snapshot("taiwan", out)
    log.info("Taiwan PCC: %d open kept of %d listed (%d pages)", len(keep), total, pages)
    return keep, {"new": len(keep), "listed": total, "pages": pages, "quarantined": q, "complete_snapshot": 1 if complete else 0}
