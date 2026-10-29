"""US federal contract awards (USAspending.gov official API): who won, for how much, from which agency.

Purpose: US solicitations almost never state a value, so the deal engine had to guess from other countries' awards.
With recent federal awards it learns the typical award size per US buyer (same agency names as the solicitations) and
per sector, plus how often foreign firms win. Written as an award file (data/leads/awards/sam/<date>.json) that the
normal award merge reads. Public data only.
Run: python -m leads.sam_awards [days=90]
"""
import datetime as dt
import json
import sys

from .common import LEADS, clean, log, polite, session, today
from .sam import _sector

OUT = LEADS / "awards" / "sam"


USAS = "https://api.usaspending.gov/api/v2/search/spending_by_award/"


def fetch(days=90, pages=60):
    """Most recent federal contract awards (newest first, no amount filter, so medians are not biased), with the
    Product/Service Code mapped to the same sectors as SAM solicitations."""
    s = session()
    t = today()
    since = t - dt.timedelta(days=days)
    fields = ["Award ID", "Recipient Name", "Award Amount", "Description", "Awarding Agency", "Awarding Sub Agency",
              "Start Date", "PSC", "NAICS", "Recipient Location", "generated_internal_id"]
    flt = {"award_type_codes": ["A", "B", "C", "D"], "time_period": [{"start_date": str(since), "end_date": str(t)}]}
    rows = []
    for page in range(1, pages + 1):
        try:
            r = s.post(USAS, json={"filters": flt, "fields": fields, "limit": 100, "page": page,
                                   "sort": "Start Date", "order": "desc"}, timeout=120)
        except Exception as e:  # noqa: BLE001
            log.warning("USAspending page %d: %s", page, e); break
        if r.status_code in (429, 500, 502, 503):
            polite(10); continue
        if r.status_code != 200:
            log.warning("USAspending %s %s", r.status_code, r.text[:200]); break
        j = r.json()
        for a in j.get("results") or []:
            amt = a.get("Award Amount") or 0
            name = clean(a.get("Recipient Name") or "", 120)
            if not name or not amt or amt <= 0:
                continue
            psc = a.get("PSC") or {}
            code = (psc.get("code") if isinstance(psc, dict) else str(psc or "")) or ""
            desc = clean(a.get("Description") or "", 200)
            sector, _ = _sector(f"{code[:2] if code[:1].isdigit() else code[:1]}--{desc}") if code else _sector(desc)
            loc = a.get("Recipient Location") or {}
            agency = clean(a.get("Awarding Agency") or "", 80)
            sub = clean(a.get("Awarding Sub Agency") or "", 80)
            rows.append({
                "id": f"USAS-{a.get('generated_internal_id') or a.get('Award ID')}", "source": "USAspending awards",
                "sector": sector or "", "title": desc, "buyer": " / ".join(x for x in dict.fromkeys([agency, sub]) if x)[:120],
                "country": "USA", "cpv": "", "published": (a.get("Start Date") or "")[:10], "winners": [name],
                "winner_country": (loc.get("location_country_code") or "USA")[:3].upper(), "value": round(amt),
                "currency": "USD", "bids": "",
                "link": f"https://www.usaspending.gov/award/{a.get('generated_internal_id')}" if a.get("generated_internal_id") else ""})
        if not (j.get("page_metadata") or {}).get("hasNext"):
            break
        polite(0.4)
    seen, out = set(), []
    for r in rows:
        if r["id"] not in seen:
            seen.add(r["id"]); out.append(r)
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.json"):
        f.unlink()
    (OUT / f"{t}.json").write_text(json.dumps(out))
    log.info("US awards (USAspending): %d recent contract awards (last %d days)", len(out), days)
    return out


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    rows = fetch(int(sys.argv[1]) if len(sys.argv) > 1 else 90, int(sys.argv[2]) if len(sys.argv) > 2 else 60)
    import statistics
    v = [r["value"] for r in rows]
    print(len(rows), "awards; median", statistics.median(v) if v else None,
          "foreign winners", sum(1 for r in rows if r["winner_country"] != "USA"))
