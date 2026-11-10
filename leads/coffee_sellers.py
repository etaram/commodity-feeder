"""Coffee producers, cooperatives and exporters worldwide from the public seller profiles of Algrano (a green-coffee
marketplace; its robots.txt allows the seller-profile pages and its sitemap lists them).

Each profile states the seller's name, country and what it is (single farm, cooperative, washing station, exporter,
trader) and tells its story in its own words. That is the producer-level detail the supplier index lacks for coffee:
who actually grows and processes it, by origin. A profile is the seller's own statement, so the index shows it as a
directory listing to check, never as proof.

Incremental and polite: a few hundred profiles a run, one request about every 1.2 seconds, resumes where it stopped,
stops after five refusals in a row. Output: data/leads/coffee_sellers.csv (public profile facts only).

  python -m leads.coffee_sellers --max 400 --minutes 12
"""
import argparse
import csv
import html
import json
import re
import time
from datetime import date

import requests

from .common import LEADS, log

BASE = "https://www.algrano.com"
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)", "Accept-Language": "en"}
OUT, STATE = LEADS / "coffee_sellers.csv", LEADS / "coffee_sellers_state.json"
FIELDS = ["supplier", "country", "country_name", "kinds", "role", "about", "source", "source_url", "fetched"]
KINDS = r"Single Farm|Farm|Cooperative|Association|Washing station|Dry mill|Wet mill|Mill|Estate|Exporter|Trader|Producer group|Producer|Importer|Roaster"


def iso3(name):
    try:
        import pycountry
        fix = {"Bolivia": "BOL", "Tanzania": "TZA", "Vietnam": "VNM", "Laos": "LAO", "Ivory Coast": "CIV", "DR Congo": "COD", "Democratic Republic of the Congo": "COD", "Venezuela": "VEN"}
        if name in fix:
            return fix[name]
        return pycountry.countries.lookup(name).alpha_3
    except Exception:  # noqa: BLE001
        return ""


def parse(page):
    t = re.sub(r"<[^>]+>", " | ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", page, flags=re.S))
    t = re.sub(r"(\|\s*)+", "| ", re.sub(r"\s+", " ", html.unescape(t)))
    m = re.search(r"\| ([^|]{2,90}) \| ([A-Z][^|]{2,45}) \| ((?:(?:" + KINDS + r")(?:, )?)+) \| ", t)
    if not m:
        return None
    name, country, kinds = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
    a = re.search(r"\| About \| (?:Want to get in touch[^|]*\| [^|]*\| (?:Connect \| )?(?:About \| )?)?([^|]{60,})", t[m.end():])
    about = re.sub(r"\s+", " ", a.group(1)).strip()[:260] if a else ""
    grows = re.search(r"Farm|Cooperative|Association|Washing station|mill|Estate|Producer", kinds, re.I)
    return {"supplier": name[:90], "country": iso3(country), "country_name": country, "kinds": kinds, "role": "producer" if grows else "trader", "about": about}


def main(max_pages=400, minutes=12.0):
    st = json.loads(STATE.read_text()) if STATE.exists() else {"done": {}, "urls": [], "sitemap_at": ""}
    today, t0 = date.today().isoformat(), time.time()
    s = requests.Session(); s.headers.update(UA)
    if not st.get("urls") or st.get("sitemap_at", "") < today[:7]:   # the list of profiles, refreshed monthly
        sm = s.get(BASE + "/sitemap.xml", timeout=60).text
        st["urls"] = sorted(set(re.findall(r"<loc>(https://www\.algrano\.com/en/seller-profiles/\d+[^<?]*)</loc>", sm)), key=lambda u: -int(re.search(r"/(\d+)", u.split("seller-profiles")[1]).group(1)))
        st["sitemap_at"] = today
        log.info("coffee sellers: %d profiles in the sitemap", len(st["urls"]))
    rows = {r["source_url"]: r for r in csv.DictReader(open(OUT, encoding="utf-8"))} if OUT.exists() else {}
    n = streak = added = 0
    for u in st["urls"]:
        if u in st["done"]:
            continue
        if n >= max_pages or time.time() - t0 > minutes * 60:
            break
        try:
            r = s.get(u, timeout=30)
        except requests.RequestException:
            streak += 1
            if streak >= 5:
                break
            continue
        n += 1
        if r.status_code != 200:
            if r.status_code in (404, 410):
                st["done"][u] = today   # a removed profile
            else:
                streak += 1
                if streak >= 5:
                    log.warning("coffee sellers: 5 refusals in a row (HTTP %s), stopping this run", r.status_code); break
            time.sleep(2.5)
            continue
        streak = 0
        st["done"][u] = today
        p = parse(r.text)
        if p and p["supplier"]:
            rows[u] = {**p, "source": "Algrano seller profile", "source_url": u, "fetched": today}
            added += 1
        time.sleep(1.2)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader()
        for u in sorted(rows):
            w.writerow({k: rows[u].get(k, "") for k in FIELDS})
    STATE.write_text(json.dumps(st))
    by = {}
    for r in rows.values():
        by[r["country"]] = by.get(r["country"], 0) + 1
    print("coffee sellers:", json.dumps({"pages": n, "added": added, "total": len(rows), "left": sum(1 for u in st["urls"] if u not in st["done"]), "top": sorted(by.items(), key=lambda x: -x[1])[:12]}))


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    ap = argparse.ArgumentParser(); ap.add_argument("--max", type=int, default=400); ap.add_argument("--minutes", type=float, default=12)
    a = ap.parse_args(); main(a.max, a.minutes)
