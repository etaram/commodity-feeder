"""US federal award notices (SAM.gov public search, notice type 'a'): who won, for how much, from which agency.

Purpose: US solicitations almost never state a value, so the deal engine had to guess from other countries' awards.
With SAM award notices it learns the typical award size per US buyer (same agency names as the solicitations) and
per sector, plus how often foreign firms win. Written as an award file (data/leads/awards/sam/<date>.json) that the
normal award merge reads. Public data only.
Run: python -m leads.sam_awards [days=90]
"""
import datetime as dt
import json
import sys

from .common import LEADS, clean, log, polite, session, today
from .sam import URL, _sector

OUT = LEADS / "awards" / "sam"


def _amount(o):
    for path in (("award", "amount"), ("award", "awardAmount"), ("awardAmount",), ("award", "dollarsObligated")):
        x = o
        for k in path:
            x = x.get(k) if isinstance(x, dict) else None
        try:
            v = float(str(x).replace(",", "").replace("$", ""))
            if v > 0:
                return v
        except (TypeError, ValueError):
            continue
    return None


def _awardee(o):
    a = (o.get("award") or {}).get("awardee") or o.get("awardee") or {}
    if isinstance(a, list):
        a = a[0] if a else {}
    name = clean(a.get("name") or a.get("legalBusinessName") or "", 120)
    loc = a.get("location") or {}
    ctry = loc.get("country") or {}
    code = (ctry.get("code") if isinstance(ctry, dict) else ctry) or ""
    return name, (code or "USA")[:3].upper() if len(code or "") >= 2 else "USA"


def fetch(days=90):
    s = session(); s.headers["Accept"] = "application/hal+json"
    t = today()
    since = t - dt.timedelta(days=days)
    rows, sample_logged = [], False
    # weekly windows keep each query under the 10,000-result cap
    for w in range(0, days, 7):
        a, b = since + dt.timedelta(days=w), min(t, since + dt.timedelta(days=w + 6))
        for page in range(100):
            try:
                r = s.get(URL, params={"index": "opp", "page": page, "size": 100, "mode": "search", "notice_type": "a",
                                       "modified_date.from": f"{a}-05:00", "modified_date.to": f"{b}-05:00"}, timeout=60)
                j = r.json()
            except Exception as e:  # noqa: BLE001
                log.warning("SAM awards %s page %d: %s", a, page, e); break
            res = (j.get("_embedded") or {}).get("results") or []
            if not res:
                break
            if not sample_logged:
                log.info("SAM award sample keys: %s | award: %s", sorted(res[0].keys())[:40],
                         json.dumps(res[0].get("award"))[:400])
                sample_logged = True
            for o in res:
                amt = _amount(o)
                name, wc = _awardee(o)
                if not amt or not name:
                    continue
                title = clean(o.get("title"))
                org = o.get("organizationHierarchy") or []
                sector, _ = _sector(title)
                rows.append({
                    "id": f"SAMA-{o.get('_id')}", "source": "SAM.gov awards", "sector": sector or "", "title": title[:200],
                    "buyer": clean(" / ".join(dict.fromkeys(x.get("name") or "" for x in (org[:1] + org[-1:]))), 120),
                    "country": "USA", "cpv": "", "published": (o.get("publishDate") or o.get("modifiedDate") or "")[:10],
                    "winners": [name], "winner_country": wc, "value": round(amt), "currency": "USD", "bids": "",
                    "link": f"https://sam.gov/opp/{o.get('_id')}/view"})
            tot = (j.get("page") or {}).get("totalPages", 0)
            if page + 1 >= min(tot, 100):
                break
            polite(0.3)
    seen, out = set(), []
    for r in rows:
        if r["id"] not in seen:
            seen.add(r["id"]); out.append(r)
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.json"):
        f.unlink()
    (OUT / f"{t}.json").write_text(json.dumps(out))
    log.info("SAM awards: %d award notices with amount and awardee (last %d days)", len(out), days)
    return out


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    rows = fetch(int(sys.argv[1]) if len(sys.argv) > 1 else 90)
    import statistics
    v = [r["value"] for r in rows]
    print(len(rows), "awards; median", statistics.median(v) if v else None,
          "foreign winners", sum(1 for r in rows if r["winner_country"] != "USA"))
