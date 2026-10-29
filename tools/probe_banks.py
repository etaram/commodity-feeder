"""Probe official procurement pages of AfDB, ADB, IDB and NATO agencies: robots.txt check, page size, feed links.
Writes data/probe/banks/<name>.html (first 300 KB) and data/probe/banks/summary.json. Read-only, one request per page."""
import json
import re
import sys
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import urljoin, urlparse

sys.path.insert(0, ".")
from leads.common import session  # noqa: E402

PAGES = {
    "adb_tenders": "https://www.adb.org/projects/tenders",
    "adb_howto": "https://www.adb.org/business/how-to/where-to-find-current-tenders-bidding-opportunities",
    "adb_rss": "https://www.adb.org/rss",
    "afdb_proc": "https://www.afdb.org/en/projects-and-operations/procurement",
    "afdb_notices": "https://www.afdb.org/en/projects-and-operations/procurement/notices",
    "afdb_rss": "https://www.afdb.org/en/rss-feeds",
    "idb_notices": "https://projectprocurement.iadb.org/en/procurement-notices",
    "idb_proc": "https://www.iadb.org/en/how-we-can-work-together/procurement",
    "nspa_open": "https://www.nspa.nato.int/business/procurement/open-procurements",
    "nspa_biz": "https://www.nspa.nato.int/business/procurement",
    "ncia_biz": "https://www.ncia.nato.int/business/procurement.html",
}
OUT = Path("data/probe/banks"); OUT.mkdir(parents=True, exist_ok=True)
s = session()
summary = {}
robots = {}
for name, url in PAGES.items():
    host = urlparse(url).scheme + "://" + urlparse(url).netloc
    if host not in robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = s.get(host + "/robots.txt", timeout=30)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:  # noqa: BLE001
            rp.parse([])
        robots[host] = rp
    allowed = robots[host].can_fetch("*", url)
    info = {"url": url, "robots_allowed": allowed}
    if allowed:
        try:
            r = s.get(url, timeout=45)
            info.update(status=r.status_code, final=r.url, size=len(r.text), ctype=r.headers.get("content-type", ""))
            (OUT / f"{name}.html").write_text(r.text[:300_000], encoding="utf-8")
            links = re.findall(r'href="([^"]+)"', r.text)
            info["feeds"] = sorted({urljoin(r.url, h) for h in links if re.search(r"rss|feed|\.xml|\.csv|\.json|api|export", h, re.I)})[:40]
            info["sample_links"] = sorted({urljoin(r.url, h) for h in links if re.search(r"tender|procure|notice|bid|opportunit", h, re.I)})[:40]
        except Exception as e:  # noqa: BLE001
            info["error"] = str(e)[:200]
    summary[name] = info
    print(name, info.get("status"), info.get("size"), allowed, flush=True)
    time.sleep(2)
(OUT / "summary.json").write_text(json.dumps(summary, indent=1))
