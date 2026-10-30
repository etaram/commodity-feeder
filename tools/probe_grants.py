"""Probe official grant / call-for-proposal APIs and the World Bank governance indicators.
Writes data/probe/grants/<name>.json (first 200 KB) and summary.json. Read-only."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
from leads.common import session  # noqa: E402

OUT = Path("data/probe/grants"); OUT.mkdir(parents=True, exist_ok=True)
s = session()
res = {}


def rec(name, r, note=""):
    body = r.text if hasattr(r, "text") else str(r)
    (OUT / f"{name}.txt").write_text(body[:200_000], encoding="utf-8")
    res[name] = {"status": getattr(r, "status_code", None), "len": len(body), "ctype": r.headers.get("content-type", "") if hasattr(r, "headers") else "", "note": note,
                 "head": body[:600].replace("\n", " ")}
    print(name, res[name]["status"], res[name]["len"], res[name]["ctype"][:40], flush=True)


# 1. grants.gov official search API (free, no key)
try:
    r = s.post("https://api.grants.gov/v1/api/search2", json={"rows": 20, "keyword": "", "oppStatuses": "forecasted|posted"}, timeout=60)
    rec("grants_gov", r)
except Exception as e:
    res["grants_gov"] = {"error": str(e)[:200]}; print("grants_gov ERR", e, flush=True)

# 2. EU Funding & Tenders portal search (SEDIA public API)
for name, url, payload in [
    ("eu_ft", "https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA&text=***&pageSize=20&pageNumber=1", None),
]:
    try:
        r = s.post(url, files={"query": (None, json.dumps({"bool": {"must": [{"terms": {"type": ["1", "2", "8"]}}, {"terms": {"status": ["31094501", "31094502"]}}]}})),
                               "languages": (None, '["en"]'), "sort": (None, '{"field":"sortStatus","order":"ASC"}')}, timeout=60)
        rec(name, r)
    except Exception as e:
        res[name] = {"error": str(e)[:200]}; print(name, "ERR", e, flush=True)

# 3. World Bank governance indicators (free API)
for ind in ["CC.EST", "RQ.EST", "GE.EST", "RL.EST"]:
    try:
        r = s.get(f"https://api.worldbank.org/v2/country/all/indicator/{ind}", params={"format": "json", "per_page": 500, "mrnev": 1}, timeout=60)
        rec("wgi_" + ind.split(".")[0], r)
    except Exception as e:
        res["wgi_" + ind] = {"error": str(e)[:200]}; print(ind, "ERR", e, flush=True)
    time.sleep(1)

# 4. Israel: data.gov.il procurement / exemptions (CKAN)
for name, url, params in [
    ("datagov_search", "https://data.gov.il/api/3/action/package_search", {"q": "התקשרויות", "rows": 20}),
    ("datagov_search2", "https://data.gov.il/api/3/action/package_search", {"q": "פטור ממכרז", "rows": 20}),
    ("datagov_grants", "https://data.gov.il/api/3/action/package_search", {"q": "קול קורא", "rows": 20}),
]:
    try:
        r = s.get(url, params=params, timeout=60)
        rec(name, r)
    except Exception as e:
        res[name] = {"error": str(e)[:200]}; print(name, "ERR", e, flush=True)
    time.sleep(1)

# 5. UN / development agency calls
for name, url in [
    ("ungm_api", "https://www.ungm.org/Public/Notice/Search"),
    ("devex_robots", "https://www.devex.com/robots.txt"),
    ("gef", "https://www.thegef.org/robots.txt"),
]:
    try:
        rec(name, s.get(url, timeout=40))
    except Exception as e:
        res[name] = {"error": str(e)[:200]}; print(name, "ERR", e, flush=True)
    time.sleep(1)

(OUT / "summary.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("DONE")
