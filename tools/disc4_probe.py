import subprocess, sys, re
def sh(c, t=900): return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
sh(f"{sys.executable} -m pip install -q 'scrapling[fetchers]'"); sh("scrapling install")
from scrapling.fetchers import StealthyFetcher
def fx(u): return StealthyFetcher.fetch(u, headless=True, network_idle=True, timeout=90000).html_content
b = fx("https://etendering.tenderboard.gov.bh/Tenders/publicDash?CTRL_STRDIRECTION=LTR")
i = b.find("502/2026/BTB"); print("### BH ROW HTML\n", b[max(0, i-900):i+1100], flush=True)
print("### BH any headers:", re.findall(r"<h\d[^>]*>(.*?)</h\d>", b, flags=re.S)[:10], flush=True)
m = fx("https://myprocurement.treasury.gov.my/advertisements/tender")
j = m.find("Iklan Tender", m.find("Carian Tajuk")); k = m.find("Tarikh Pelawaan")
print("### MY AFTER SEARCH\n", re.sub(r"\s+", " ", m[k:k+200]), flush=True)
cards = re.findall(r'(?:Tarikh Tutup|Tarikh Iklan|No\. Tender|Tajuk)[^<]{0,80}', m)[:12]; print("### MY labels", cards, flush=True)
n = m.find("modal"); idx = [x.start() for x in re.finditer(r"Lawatan Tapak", m)][:1]
if idx: print("### MY CONTEXT\n", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", m[max(0, idx[0]-3500):idx[0]+300])), flush=True)
w = fx("https://www.capt.gov.kw/en/tenders/opening-tenders/")
print("### KW has JSON api:", sorted(set(re.findall(r'(?:url|fetch|ajax)[^;]{0,40}["\'](/[^"\']*(?:api|json|ajax|data)[^"\']*)', w)))[:10], flush=True)
for mm in re.findall(r"(https?://[^\s\"']*(?:api|json)[^\s\"']*)", w)[:10]: print("KW url", mm, flush=True)
t = re.sub(r"\s+", " ", re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", w, flags=re.S)); i = t.find("Opening Tenders", 600); print("### KW TEXT\n", t[i:i+1800], flush=True)
