"""Turkey: public tender announcements (ihale ilanlari) published on ilan.gov.tr, the official notice portal of the
Press Advertising Agency (Basin Ilan Kurumu), which carries the official tender notices of ministries, municipalities,
universities and state companies. EKAP (ekap.kik.gov.tr / ekapv2) itself is not read: it sits behind a Cloudflare
Turnstile challenge and is marked noindex,nofollow (checked 2026-11-14).

Access (checked 2026-11-14): ilan.gov.tr/robots.txt allows everything except /*tebligat; the site's own JSON search
(POST /api/api/services/app/Ad/AdsByFilter, ad type 3 = ihale) and notice detail (GET .../AdDetail/GetAdDetail) need
no login. No relay is used: if the site refuses the runner's address the run fails and says so.

OPEN = a tender notice whose tender date (ihale tarihi, the bid submission deadline under Public Procurement Law 4734,
read from the notice) is today or later. Sales and rentals of public property are kept out (stage 'tender' only for
procurement of goods, services and works)."""
import datetime as dt
import json
import os
import re
import time

import requests

from .common import CACHE, chain_session, clean, log, quarantine_future, rolling, today
from .sectors import classify

BASE = "https://www.ilan.gov.tr"
SEARCH = BASE + "/api/api/services/app/Ad/AdsByFilter"
DETAIL = BASE + "/api/api/services/app/AdDetail/GetAdDetail"
BUDGET_S = int(os.environ.get("TURKEY_BUDGET_S", "600"))
GAP = 0.6
PAGE = 50
DAYS = 30
STATE = CACHE / "turkey_ilan_detail.jsonl"
SALE = re.compile(r"sat[ıi][şs]|kiraya|kiralama|kira ihale|tahsis|irtifak|hurda|devir|ortakl[ıi]k|arsa|ta[şs][ıi]nmaz|"
                  r"mahsul|ot ihale|av ihale|otlatma|kum ihale", re.I)
DATEPAT = re.compile(r"(\d{2})[./](\d{2})[./](\d{4})(?:\s*(?:-|,|günü)?\s*(?:saat\s*)?(\d{2})[:.](\d{2}))?", re.I)
WHEN = re.compile(r"(ihale|teklif|son\s+başvuru|son\s+teklif)[^<]{0,120}?(tarih|saat)", re.I)


class _Polite:
    def __init__(self):
        self.s = chain_session(BASE)   # the site omits its intermediate certificate: fetched via AIA, TLS still verified
        self.s.headers.update({"Accept": "application/json", "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
                               "Referer": BASE + "/ilan/tum-ilanlar"})
        self.last, self.calls = 0.0, 0

    def _wait(self):
        d = time.time() - self.last
        if d < GAP:
            time.sleep(GAP - d)
        self.last = time.time(); self.calls += 1

    def post(self, url, **kw):
        self._wait()
        return requests.Session.post(self.s, url, timeout=60, **kw)

    def get(self, url, **kw):
        self._wait()
        return requests.Session.get(self.s, url, timeout=60, **kw)


def to_date(m):
    try:
        d = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return "", ""
    return str(d), (f"{m.group(4)}:{m.group(5)} TRT" if m.group(4) else "")


def deadline_from(filters, html):
    """The tender date: a filter whose key names the tender date, else the date following 'ihale tarihi/saati'
    (or the bid deadline wording) in the notice text."""
    for f in filters or []:
        k = (f.get("key") or "").lower()
        if "tarih" in k and ("ihale" in k or "teklif" in k or "son" in k):
            m = DATEPAT.search(str(f.get("value") or ""))
            if m:
                return to_date(m) + (f.get("key"),)
    text = clean(html or "")
    for w in WHEN.finditer(text):
        m = DATEPAT.search(text, w.end(), w.end() + 160)
        if m:
            return to_date(m) + ("text: " + text[w.start():w.end()][:40],)
    return "", "", ""


def search(c, page, dmin, dmax):
    body = {"keys": {"ats": [3], "ppdmin": [dmin], "ppdmax": [dmax]}, "skipCount": page * PAGE, "maxResultCount": PAGE}
    if page:
        body["keys"]["currentPage"] = [page + 1]
    r = c.post(SEARCH, data=json.dumps(body), headers={"Content-Type": "application/json"})
    if r.status_code != 200:
        raise RuntimeError(f"search HTTP {r.status_code}: {r.text[:120]!r}")
    return (r.json().get("result") or {})


def probe(c):
    """What the public, crawler-facing side (robots.txt sitemaps and notice pages) gives the runner."""
    for u in [BASE + "/robots.txt", BASE + "/sitemap/daily-ads.xml", BASE + "/sitemap/ads.xml"]:
        try:
            r = c.get(u)
            locs = re.findall(r"<loc>([^<]+)</loc>", r.text)
            log.info("Turkey probe %s: HTTP %s %s %d bytes, %d locs, ihale locs %d, sample %s, head %r", u, r.status_code,
                     r.headers.get("content-type"), len(r.content), len(locs), sum("ihale" in x for x in locs),
                     [x for x in locs if "ihale" in x][:3] or locs[:3], " ".join(r.text[:200].split()))
        except Exception as e:  # noqa: BLE001
            log.warning("Turkey probe %s: %s", u, e)
            locs = []
        for x in [x for x in locs if "ihale" in x][:2]:
            try:
                rr = c.get(x)
                txt = clean(rr.text)
                i = txt.lower().find("tarih")
                log.info("Turkey probe page %s: HTTP %s %d bytes, has 'ihale' %s, near 'tarih': %r, ld+json %s",
                         x[:120], rr.status_code, len(rr.content), "ihale" in txt.lower(), txt[max(0, i - 150):i + 150],
                         "ld+json" in rr.text)
            except Exception as e:  # noqa: BLE001
                log.warning("Turkey probe page: %s", e)


def fetch():
    c, t0, t = _Polite(), time.time(), today()
    if os.environ.get("TURKEY_PROBE", "1") == "1":
        probe(c)
    ts = str(t)
    state = {}
    if STATE.exists():
        for line in STATE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                x = json.loads(line); state[str(x.pop("k"))] = x
    ads, page, total, cut = {}, 0, None, False
    dmin, dmax = (t - dt.timedelta(days=DAYS)).strftime("%d.%m.%Y"), t.strftime("%d.%m.%Y")
    while time.time() - t0 < BUDGET_S * 0.4:
        res = search(c, page, dmin, dmax)
        lst = res.get("ads") or []
        if total is None:
            total = res.get("numFound")
            if lst:
                log.info("Turkey ilan: %s notices of type ihale in %s..%s; first ad keys %s, filters %s, categories %s",
                         total, dmin, dmax, sorted(lst[0].keys()),
                         [(f.get("key"), str(f.get("value"))[:30]) for f in lst[0].get("adTypeFilters") or []][:12],
                         [x.get("name") for x in (lst[0].get("categories") or [])][:6])
        new = 0
        for a in lst:
            if a.get("id") and str(a["id"]) not in ads:
                ads[str(a["id"])] = a; new += 1
        page += 1
        if not lst or not new or page * PAGE >= int(total or 0) or page >= 400:
            break
    else:
        cut = True
    rows, details, sales, nodl, past, archived = [], 0, 0, 0, 0, 0
    for aid, a in ads.items():
        title = clean(a.get("title") or "")
        cats = " ".join(clean(x.get("name") or "") for x in a.get("categories") or [])
        if a.get("isArchived"):
            archived += 1; continue
        if SALE.search(cats) or SALE.search(title[:160]):
            sales += 1; continue
        st = state.get(aid)
        if not st:
            dl, hm, how = deadline_from(a.get("adTypeFilters"), "")
            if not dl:
                if time.time() - t0 > BUDGET_S:
                    cut = True; continue
                try:
                    r = c.get(DETAIL, params={"id": aid})
                    details += 1
                    d = (r.json().get("result") or {}) if r.status_code == 200 else {}
                except Exception as e:  # noqa: BLE001
                    log.warning("Turkey ilan detail %s: %s", aid, type(e).__name__); continue
                if details == 1:
                    log.info("Turkey ilan first detail: HTTP %s keys %s", r.status_code, sorted(d.keys())[:30])
                dl, hm, how = deadline_from(d.get("adTypeFilters"), d.get("content") or "")
                if details <= 3:
                    log.info("Turkey ilan detail %s: deadline %s %s (%s)", aid, dl, hm, how)
            st = {"deadline": dl, "time": hm, "how": how, "seen": ts}
            state[aid] = st
        dl = st.get("deadline") or ""
        if not dl:
            nodl += 1; continue
        if dl < ts:
            past += 1; continue
        city = clean(a.get("addressCityName") or "")
        sector, how = classify(title)
        rows.append({"id": f"TR-ILAN-{aid}", "source": "ilan.gov.tr (Turkey, Basin Ilan Kurumu)", "group": "", "sector": sector,
                     "nature": "works" if re.search(r"yap[ıi]m", cats, re.I) else "goods" if re.search(r"mal al", cats, re.I)
                     else "services" if re.search(r"hizmet", cats, re.I) else "",
                     "cpv": "", "classification": how, "country": "TUR",
                     "buyer": (clean(a.get("advertiserName") or "") + (f", {city}" if city else ""))[:120],
                     "title": title[:300], "notice_type": "Tender notice (ihale ilani)" + (f" | {cats[:80]}" if cats else "")
                     + (f" | {a.get('adNo')}" if a.get("adNo") else ""), "stage": "tender",
                     "access": "Turkish public procurement (EKAP registration; domestic-preference rules may apply; Turkish documents)",
                     "published": (a.get("publishStartDate") or "")[:10], "deadline": dl,
                     "deadline_basis": "tender date (" + st.get("how", "")[:40] + ")", "deadline_time": st.get("time", ""),
                     "value": "", "currency": "", "link": BASE + (a.get("urlStr") or f"/ilan/{aid}"), "source_url": SEARCH,
                     "fetched": ts, "contact": "", "lang": "tr"})
    keepst = {k: v for k, v in state.items() if k in ads or (v.get("deadline") or "") >= ts}
    CACHE.mkdir(parents=True, exist_ok=True)
    STATE.write_text("".join(json.dumps({"k": k, **v}, ensure_ascii=False, sort_keys=True) + "\n"
                             for k, v in sorted(keepst.items())), encoding="utf-8")
    if not ads:
        raise RuntimeError("Turkey ilan: no notice read; previous cache kept")
    rows, q = quarantine_future(rows, "turkey_ilan")
    keep, _ = rolling("turkey_ilan", rows, max_age_days=DAYS + 30)
    log.info("Turkey ilan: %d open tenders with a deadline (%d notices listed, %d calls, %d details, %d sales/rentals "
             "left out, %d archived, %d without a tender date, %d past, %s)", len(keep), len(ads), c.calls, details,
             sales, archived, nodl, past, "cut at the time budget" if cut else "complete")
    return keep, {"new": len(rows), "listed": len(ads), "calls": c.calls, "details": details, "quarantined": q,
                  "no_deadline": nodl, "deep_link": 1}
