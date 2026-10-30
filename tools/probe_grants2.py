"""Second probe: correct World Bank governance indicator ids, and the EU Funding & Tenders search format."""
import json, sys, time
from pathlib import Path
sys.path.insert(0, ".")
from leads.common import session  # noqa: E402
OUT = Path("data/probe/grants"); OUT.mkdir(parents=True, exist_ok=True)
s = session(); res = {}
def rec(n, r):
    b = r.text; (OUT / f"{n}.txt").write_text(b[:200_000], encoding="utf-8")
    res[n] = {"status": r.status_code, "len": len(b), "head": b[:400].replace("\n", " ")}
    print(n, r.status_code, len(b), b[:160].replace("\n", " "), flush=True)

# World Bank governance: try the WGI source and several id spellings
for n, url, p in [
    ("wgi_src3", "https://api.worldbank.org/v2/country/all/indicator/CC.EST", {"format": "json", "per_page": 1000, "source": 3, "mrnev": 1}),
    ("wgi_plain", "https://api.worldbank.org/v2/country/all/indicator/CC.EST", {"format": "json", "per_page": 5}),
    ("wgi_list", "https://api.worldbank.org/v2/source/3/indicator", {"format": "json", "per_page": 100}),
    ("wgi_cpia", "https://api.worldbank.org/v2/country/all/indicator/IQ.CPA.TRAN.XQ", {"format": "json", "per_page": 5, "mrnev": 1}),
]:
    try: rec(n, s.get(url, params=p, timeout=60))
    except Exception as e: print(n, "ERR", e, flush=True)
    time.sleep(1)

# EU Funding & Tenders portal
for n, q in [
    ("eu_a", {"bool": {"must": [{"terms": {"type": ["1", "2"]}}]}}),
    ("eu_b", {"terms": {"type": ["1", "2", "8"]}}),
]:
    try:
        rec(n, s.post("https://api.tech.ec.europa.eu/search-api/prod/rest/search?apiKey=SEDIA&text=***&pageSize=20&pageNumber=1",
                      files={"query": (None, json.dumps(q)), "languages": (None, '["en"]')}, timeout=60))
    except Exception as e: print(n, "ERR", e, flush=True)
    time.sleep(2)

# grants.gov: one full opportunity record
try:
    rec("grants_detail", s.post("https://api.grants.gov/v1/api/fetchOpportunity", json={"opportunityId": 355824}, timeout=60))
except Exception as e: print("detail ERR", e, flush=True)
(OUT / "summary2.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
print("DONE")
