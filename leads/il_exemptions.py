"""Israeli government contracts awarded without a tender (exemptions), from the Government Procurement
Administration's open dataset on data.gov.il ("דוח התקשרויות בפטור והליכים תחרותיים", CKAN datastore).

Why it matters: each row says which ministry buys what, from which supplier, for how much, under which exemption
clause, and until when. A running exemption contract that ends soon is a renewal the ministry must re-procure -
the moment to offer an alternative supplier or ask for an open tender.

Output: data/leads/il_exempt.csv - contracts still running (or ended in the last 6 months), largest first.
Note: the publisher updates this dataset irregularly; the 'published' column shows how recent each row is.
"""
import csv
import datetime as dt
import time

from .common import LEADS, log, session, today

API = "https://data.gov.il/api/3/action/datastore_search"
RESOURCE = "65c8fced-c50c-400e-94fb-ef1a208c43e5"
OUT = LEADS / "il_exempt.csv"
F = {"office": "שם המשרד", "unit": "שם יחידה מפרסמת", "kind": "סוג הליך", "title": "שם הליך", "clause": "תקנה",
     "decision": "מהות החלטה", "published": "תאריך פרסום", "objection_until": "תאריך אחרון להגשת השגות",
     "supplier": "שם ספק", "supplier_id": "מספר חפ ספק", "amount": "היקף כספי", "currency": "מטבע",
     "start": "תאריך תחילת תקופת התקשרות", "end": "תאריך סיום תקופת התקשרות", "number": "מספר פרסום"}


def _d(s):
    try:
        return dt.datetime.strptime((s or "").strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


def _amt(s):
    try:
        return float(str(s).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def fetch(page=32000):
    s, t = session(), today()
    rows, offset, total = [], 0, None
    while total is None or offset < total:
        try:
            r = s.get(API, params={"resource_id": RESOURCE, "limit": page, "offset": offset}, timeout=180)
            j = r.json()["result"]
        except Exception as e:  # noqa: BLE001
            log.warning("IL exemptions offset %d: %s", offset, str(e)[:160]); break
        total = j.get("total") or 0
        recs = j.get("records") or []
        if not recs:
            break
        for x in recs:
            end = _d(x.get(F["end"]))
            if not end or end < t - dt.timedelta(days=180):
                continue  # finished contracts are history, not leads
            amt = _amt(x.get(F["amount"]))
            if amt < 100_000:
                continue
            months = round((end - t).days / 30.4, 1)
            rows.append({
                "office": x.get(F["office"]) or "", "unit": x.get(F["unit"]) or "", "title": (x.get(F["title"]) or "")[:200],
                "supplier": x.get(F["supplier"]) or "", "amount": round(amt), "currency": x.get(F["currency"]) or "ILS",
                "clause": (x.get(F["clause"]) or "")[:120], "kind": x.get(F["kind"]) or "", "decision": x.get(F["decision"]) or "",
                "start": x.get(F["start"]) or "", "end": x.get(F["end"]) or "", "months_to_end": months,
                "renewal_window": "ended - re-procurement due" if months < 0 else "next 6 months" if months <= 6
                else "6-18 months" if months <= 18 else "later",
                "published": x.get(F["published"]) or "", "number": x.get(F["number"]) or "",
                "link": "https://data.gov.il/dataset/exemptions",
            })
        offset += len(recs)
        log.info("IL exemptions: %d/%d read, %d kept", offset, total, len(rows))
        time.sleep(1)
    order = {"next 6 months": 0, "ended - re-procurement due": 1, "6-18 months": 2, "later": 3}
    rows.sort(key=lambda r: (order[r["renewal_window"]], -r["amount"]))
    if rows:
        with open(OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows[:20000])
    stats = {"read": offset, "kept": len(rows), **{k: sum(1 for r in rows if r["renewal_window"] == k) for k in order}}
    log.info("IL exemptions %s", stats)
    return [], stats


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    fetch()
