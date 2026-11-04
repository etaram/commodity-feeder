import sys; sys.path.insert(0, ".")
from leads.common import session, relay_get
from leads.briefing import _feed, _telegram
from leads.attention import trending
s = session()
r = s.get("https://www.reddit.com/r/supplychain/new/.rss", timeout=30); print("reddit direct", r.status_code, len(r.content))
rr = relay_get("https://www.reddit.com/r/supplychain/new/.rss"); print("reddit relay", rr.status_code if rr else None, len(rr.content) if rr else 0)
print("reddit items via _feed", len(_feed(s, "https://www.reddit.com/r/Kenya/new/.rss")))
print("telegram", len(_telegram(s, "bloomberg")))
r = s.get("https://trends.google.com/trending/rss", params={"geo": "KE"}, timeout=30); print("trends rss", r.status_code, r.headers.get("content-type"), r.text[:200].replace("\n", " "))
print("trending KE", trending(s, "KE")[:3])
