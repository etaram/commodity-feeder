import re, html, logging
logging.basicConfig(level=logging.INFO)
from leads import qatar
from leads.common import chain_session, clean, today
from curl_cffi import requests as cr
bundle = chain_session(qatar.BASE).verify
print("bundle", bundle, "today", today())
r = cr.get(qatar.URL.format(1), impersonate="chrome", verify=bundle, timeout=60)
print("status", r.status_code, len(r.text))
ids = re.findall(r"/TendersOnlineServices/TenderDetails/(\d+)", r.text); print("ids", len(ids), ids[:3])
txt = re.sub(r"<script.*?</script>|<style.*?</style>", "", r.text, flags=re.S)
segs = [clean(html.unescape(x)) for x in re.split(r"<[^>]+>", txt)]; segs = [x for x in segs if x]
starts = [i for i, x in enumerate(segs) if re.fullmatch(r"\d{1,6}/20\d\d", x)]
print("segs", len(segs), "starts", len(starts))
for i in starts[:2]: print("BLOCK", segs[i:i+30])
if not starts:
    print("SEGS SAMPLE", segs[60:140])
try:
    rows = qatar.fetch(); print("fetch rows", len(rows)); print(rows[:1])
except Exception as e:
    import traceback; traceback.print_exc()
