"""Buying signals from stock-exchange announcements (owner, 13 Nov 2026: "see if a company buys equipment, new goods,
changes its business focus or explores new markets").

Source: SEC EDGAR full-text search (https://efts.sec.gov/LATEST/search-index), official and free. Current reports of
US listed companies (8-K) and of foreign private issuers listed in the US (6-K: Israeli, Chinese, Indian, Brazilian,
European... companies), so the signals are not US-only. Searched by exact phrases in four signal groups over the last
14 days. SEC fair-access rules: a User-Agent naming the requester, under 10 requests per second (we use ~2).

A signal is NOT an opportunity: it has no deadline and no tender. It is a lead for the pre-tender approach (Layer 3),
kept in data/leads/filings_signals.csv with the exact phrase, form, date and the filing link as evidence.
Run: python -m leads.filings [days]"""
import csv
import datetime as dt
import re
import sys
import time

from .common import LEADS, log, session

FTS = "https://efts.sec.gov/LATEST/search-index"
UA = "Sinder research desk@sinder.pro"
SIGNALS = {
    "buys equipment / capex": ["new production line", "purchase of equipment", "capital expenditure program", "capacity expansion",
                               "construction of a new plant", "construction of a new facility", "new manufacturing facility",
                               "order for new", "procurement of equipment", "fleet expansion", "expansion of production capacity"],
    "new goods / supply contracts": ["entered into a supply agreement", "purchase agreement for", "supply contract",
                                     "offtake agreement", "framework agreement", "long-term supply"],
    "changes business focus": ["strategic review", "strategic alternatives", "new business segment", "change in business focus",
                               "shift its strategic focus", "diversification into", "exit the business"],
    "explores new markets": ["expansion into new markets", "enter the market", "entry into the", "new subsidiary in",
                             "joint venture in", "memorandum of understanding with", "market expansion"],
}
OUT = LEADS / "filings_signals.csv"
COLS = ["filed", "company", "cik", "form", "signal", "phrase", "link", "fetched"]


def parse(js, signal, phrase, fetched):
    out = []
    for h in ((js or {}).get("hits") or {}).get("hits") or []:
        s = h.get("_source") or {}
        names = s.get("display_names") or []
        ciks = s.get("ciks") or []
        adsh = s.get("adsh") or ""
        fid = str(h.get("_id") or "")
        fname = fid.split(":", 1)[1] if ":" in fid else ""
        if not names or not ciks or not adsh:
            continue
        cik = str(ciks[0]).lstrip("0")
        name = re.sub(r"\s*\(CIK \d+\)\s*$", "", names[0]).strip()
        link = f"https://www.sec.gov/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/{fname}" if fname else \
               f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"
        out.append({"filed": s.get("file_date", ""), "company": name[:120], "cik": cik, "form": s.get("form") or s.get("root_form", ""),
                    "signal": signal, "phrase": phrase, "link": link, "fetched": fetched})
    return out


def run(days=14):
    t = dt.date.today()
    s = session()
    s.headers["User-Agent"] = UA
    rows, calls, errors = {}, 0, 0
    for signal, phrases in SIGNALS.items():
        for ph in phrases:
            params = {"q": f'"{ph}"', "forms": "8-K,6-K", "dateRange": "custom",
                      "startdt": str(t - dt.timedelta(days=days)), "enddt": str(t)}
            try:
                r = s.get(FTS, params=params, timeout=40)
                calls += 1
                if r.status_code != 200:
                    errors += 1; log.warning("EDGAR %s: HTTP %s", ph, r.status_code); continue
                for x in parse(r.json(), signal, ph, str(t)):
                    k = (x["link"], x["signal"])
                    rows.setdefault(k, x)
            except Exception as e:  # noqa: BLE001
                errors += 1; log.warning("EDGAR %s: %s", ph, type(e).__name__)
            time.sleep(0.5)
    out = sorted(rows.values(), key=lambda x: (x["filed"], x["company"]), reverse=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(out)
    by = {}
    for x in out:
        by[x["signal"]] = by.get(x["signal"], 0) + 1
    log.info("filings: %d signals from %d companies (%s); %d calls, %d errors", len(out), len({x['cik'] for x in out}), by, calls, errors)
    return out


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 14)
