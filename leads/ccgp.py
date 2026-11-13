"""China Government Procurement Network (ccgp.gov.cn, Ministry of Finance): public tender announcements (公开招标公告)
of central government buyers (中央公告) and of provincial and local governments (地方公告): title, buyer, province,
publication time and link, newest first, 20 per page.

Access (checked 2026-11-12): plain HTTP from the runner (method: http); robots.txt absent (404); no terms-of-use page
found, footer "© 中华人民共和国财政部 版权所有" only. These are statutory public notices; we keep facts (title, buyer,
province, date, link) and link back. Polite: 2 s between pages, stops at notices older than DAYS.
Deadlines are inside each notice, not on the list: each new notice page is read once (time-boxed per run) for the
bid submission deadline (提交投标文件截止时间 / 于...前递交投标文件), the budget (预算金额) and whether imported products
are allowed (是否可采购进口产品). A notice whose page has not been read yet has no deadline and is not counted as OPEN."""
import datetime as dt
import html
import re

from .common import clean, log, polite, quarantine_future, rolling, today
from .sectors import classify

BASE = "https://www.ccgp.gov.cn/cggg"
LISTS = {"zygg/gkzb": ("central", 20), "dfgg/gkzb": ("local", 120)}   # path -> (level, max pages)
UA = "Mozilla/5.0 (compatible; SinderSources/1.0; +https://desk.sinder.pro)"
DAYS = 25            # open tenders usually close 20+ days after publication
DETAIL_BUDGET_S = 1500
CN_DATE = r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
DUE = [re.compile(r"于\s*" + CN_DATE + r"[^。；;]{0,30}?前\s*(?:递交|提交)(?:投标|响应)?文件"),
       re.compile(r"(?:投标|响应)?(?:文件)?(?:递交|提交)?截止时间[：:\s]*" + CN_DATE)]
BUDGET = re.compile(r"预算金额[：:\s]*[￥¥]?\s*([\d,.]+)\s*[（(]?\s*(万元|元)")
IMPORT = re.compile(r"是否(?:可|允许)?采购进口产品[：:\s]*(是|否)")
LI = re.compile(r'<li>\s*<a href="\./([^"]+)"[^>]*title="([^"]+)"[^>]*>.*?</a>\s*发布时间：<em>(\d{4}-\d\d-\d\d)[^<]*</em>\s*地域：<em>([^<]*)</em>\s*采购人：<em>([^<]*)</em>', re.S)


def parse(body, path, fetched):
    level = LISTS.get(path, ("", 0))[0]
    out = []
    for href, title, date, prov, buyer in LI.findall(body):
        title = clean(html.unescape(title))
        sector, how = classify(title)
        out.append({"id": "CCGP-" + re.sub(r"\D", "", href.split("/")[-1])[-12:], "source": "China Government Procurement (CCGP)", "group": "",
                    "sector": sector, "nature": "", "cpv": "", "classification": how, "country": "CHN", "buyer": clean(html.unescape(buyer), 120),
                    "title": title[:300], "notice_type": "公开招标公告 (open tender)", "stage": "tender",
                    "access": "Open tender (Chinese government procurement law; domestic goods preference)", "published": date, "deadline": "",
                    "value": "", "currency": "", "link": f"{BASE}/{path}/{href}", "source_url": f"{BASE}/{path}/", "fetched": fetched,
                    "contact": "", "lang": "zh", "province": clean(prov, 30), "gov_level": level})
    return out


def detail(text):
    """deadline (YYYY-MM-DD), budget in CNY, imports allowed ('yes'/'no'/'') from a notice page."""
    t = re.sub(r"<[^>]+>", " ", text)
    t = html.unescape(t)
    dl = ""
    for rx in DUE:
        m = rx.search(t)
        if m:
            try:
                dl = str(dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))); break
            except ValueError:
                continue
    v, m = "", BUDGET.search(t)
    if m:
        try:
            v = round(float(m.group(1).replace(",", "")) * (10000 if m.group(2) == "万元" else 1))
        except ValueError:
            v = ""
    imp = IMPORT.search(t)
    return dl, v, {"是": "yes", "否": "no"}.get(imp.group(1), "") if imp else ""


def fetch():
    import json
    import time
    import requests
    from .common import CACHE
    s = requests.Session(); s.headers.update({"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5"})
    t = today(); cut = str(t - dt.timedelta(days=DAYS)); new, pages = [], 0
    for path, (level, max_pages) in LISTS.items():
        for page in range(max_pages):
            url = f"{BASE}/{path}/index.htm" if page == 0 else f"{BASE}/{path}/index_{page}.htm"
            r = s.get(url, timeout=40)
            pages += 1
            if r.status_code != 200:
                log.warning("CCGP %s page %d: HTTP %s", path, page, r.status_code); break
            r.encoding = "utf-8"
            rows = parse(r.text, path, str(t))
            new += [x for x in rows if x["published"] >= cut]
            polite(2)
            if not rows or min(x["published"] for x in rows) < cut:
                break
    # carry details already read; read the pages of notices not read yet, newest first, within the time box
    known = {}
    p = CACHE / "ccgp.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line); known[r["id"]] = r
    t0, read, failed = time.time(), 0, 0
    for x in sorted(new, key=lambda r: r["published"], reverse=True):
        k = known.get(x["id"])
        if k and k.get("detail_read"):
            for f in ("deadline", "value", "currency", "imports", "detail_read", "access"):
                if f in k:
                    x[f] = k[f]
            continue
        if time.time() - t0 > DETAIL_BUDGET_S:
            continue
        try:
            r = s.get(x["link"], timeout=30); r.encoding = "utf-8"
            if r.status_code != 200:
                failed += 1; continue
            dl, v, imp = detail(r.text)
            x.update(deadline=dl, detail_read=str(t), imports=imp)
            if v:
                x.update(value=v, currency="CNY")
            if imp == "no":
                x["access"] = "Open tender; imported products NOT allowed (domestic goods only)"
            elif imp == "yes":
                x["access"] = "Open tender; imported products allowed"
            read += 1
        except Exception:  # noqa: BLE001
            failed += 1
        polite(1)
    new, q = quarantine_future(new, "ccgp")
    keep, _ = rolling("ccgp", new, max_age_days=60)
    log.info("CCGP: %d open-tender notices in %d days (%d pages; central %d, local %d), %d kept", len(new), DAYS, pages,
             sum(1 for x in new if x["gov_level"] == "central"), sum(1 for x in new if x["gov_level"] == "local"), len(keep))
    with_dl = sum(1 for x in keep if x.get("deadline"))
    log.info("CCGP details: %d pages read this run, %d failed; %d of %d kept notices have a stated deadline", read, failed, with_dl, len(keep))
    return keep, {"new": len(new), "pages": pages, "details_read": read, "details_failed": failed, "with_deadline": with_dl}
