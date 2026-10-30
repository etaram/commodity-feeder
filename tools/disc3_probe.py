import subprocess, sys, re
def sh(c, t=900): return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t)
sh(f"{sys.executable} -m pip install -q 'scrapling[fetchers]'"); sh("scrapling install")
from scrapling.fetchers import Fetcher, StealthyFetcher
def look(tag, u, stealth=False):
    try:
        p = StealthyFetcher.fetch(u, headless=True, network_idle=True, timeout=90000) if stealth else Fetcher.get(u, impersonate="chrome", timeout=60, verify=False)
        b = p.html_content
        print(f"### {tag} {u} st={p.status} len={len(b)} tr={b.lower().count('<tr')}", flush=True)
        trs = re.findall(r"<tr[^>]*>(.*?)</tr>", b, flags=re.S | re.I)
        for tr in trs[:8]:
            cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip()[:90] for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S | re.I)]
            href = re.findall(r'href=["\']([^"\']+)["\']', tr)[:2]
            print("ROW", cells, href, flush=True)
        if not trs:
            t = re.sub(r"\s+", " ", re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", b, flags=re.S)); print("TEXT", t[:900], flush=True)
        print("PAGER", re.findall(r'(?:page=\d+|/page/\d+|offset=\d+)', b)[:6], flush=True)
    except Exception as e:
        print(f"### {tag} ERR {str(e)[:120]}", flush=True)
look("BH public", "https://tenderboard.gov.bh/Tenders/PublicTenders/", True)
look("BH public fetcher", "https://tenderboard.gov.bh/Tenders/PublicTenders/")
look("BH publicDash", "https://etendering.tenderboard.gov.bh/Tenders/publicDash?CTRL_STRDIRECTION=LTR", True)
for k in ["pre-tenders", "opening-tenders", "closing-tenders"]:
    look("KW " + k, f"https://www.capt.gov.kw/en/tenders/{k}/", True)
look("MY adv", "https://myprocurement.treasury.gov.my/advertisements/tender")
look("MY adv stealth", "https://myprocurement.treasury.gov.my/advertisements/tender", True)
