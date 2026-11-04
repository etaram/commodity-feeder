"""Probe the GDELT DOC API from Actions: status and body head for a few query shapes."""
import requests
API = "https://api.gdeltproject.org/api/v2/doc/doc"
tests = [
    {"query": "Kenya procurement", "mode": "ArtList", "maxrecords": 5, "format": "json", "timespan": "7d"},
    {"query": "Kenya (procurement OR tender OR infrastructure)", "mode": "ArtList", "maxrecords": 5, "format": "json", "timespan": "1w"},
    {"query": '"Kenya" (procurement OR tender) sourcelang:english', "mode": "ArtList", "maxrecords": 5, "format": "json", "timespan": "7d"},
    {"query": "Kenya infrastructure sourcelang:eng", "mode": "artlist", "maxrecords": 5, "format": "json", "timespan": "7days"},
]
for p in tests:
    try:
        r = requests.get(API, params=p, timeout=40, headers={"User-Agent": "sinder-deal-desk/1.0"})
        print(p["query"], p["timespan"], "->", r.status_code, r.headers.get("content-type"), repr(r.text[:200]))
    except Exception as e:  # noqa: BLE001
        print(p["query"], "EXC", type(e).__name__, e)
