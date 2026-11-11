"""Winner dossier: for the best fresh contract winners, the company's official website and the business contact it
publishes itself (role mailboxes such as info@, sales@, procurement@, and switchboard numbers).

How a website is found, without guessing: Wikidata's search for the winner's name, accepted only when the label
matches the name closely and the item is described as a company; then its "official website" property (P856).
How the contact is found: the website's home page and its contact page, fetched only where robots.txt allows.
Only role addresses are kept, never a named person's mailbox, and nothing about individuals is collected.

Results are cached in data/private/winner_dossier.json (30 days per winner) so each run adds new winners and
re-checks old ones slowly. Output: fields added to each winner row in leads/winners.py before it is encrypted:
  ws  website, ce  role e-mails, cp  phone numbers, cs  the page the contact was read from, wd  Wikidata id
"""
import datetime as dt
import json
import re
import time
from urllib import robotparser
from urllib.parse import urljoin, urlparse

import requests

from .common import PRIVATE, log

CACHE = PRIVATE / "winner_dossier.json"
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)"}
PER_RUN = 120
TTL_DAYS = 30
ROLE = re.compile(r"^(info|sales|contact|contacts|enquir(y|ies)|inquir(y|ies)|procurement|purchas(e|ing)|supply|supplier|suppliers|tender|tenders|bid|bids|office|admin|mail|hq|headoffice|business|marketing|export|international|overseas|commercial|service|general|reception|pr|media|communications?)[\w.-]*@", re.I)
COMPANY = re.compile(r"company|corporation|enterprise|group|construction|engineering|contractor|firm|business|manufacturer|conglomerate|state-owned|subsidiary|limited|holding", re.I)
STOP = {"co", "ltd", "limited", "llc", "inc", "plc", "sa", "sas", "srl", "spa", "gmbh", "ag", "bv", "pvt", "private", "the", "and", "of", "corporation", "corp", "company", "group", "sdn", "bhd", "pte", "jsc", "ojsc", "pjsc", "cjsc", "&", "s.a.", "s.a", "pty"}
_robots = {}


def _norm(name):
    return [t for t in re.findall(r"[a-z0-9]+", (name or "").lower()) if t not in STOP and len(t) > 1]


def _close(a, b):
    x, y = set(_norm(a)), set(_norm(b))
    if not x or not y:
        return False
    return len(x & y) / max(len(x), len(y)) >= 0.6


def _allowed(url):
    host = "{0.scheme}://{0.netloc}".format(urlparse(url))
    if host not in _robots:
        rp = robotparser.RobotFileParser(host + "/robots.txt")
        try:
            rp.read()
        except Exception:  # noqa: BLE001
            rp = None
        _robots[host] = rp
    rp = _robots[host]
    return True if rp is None else rp.can_fetch(UA["User-Agent"], url)


def _get(url, timeout=20):
    if not _allowed(url):
        return None
    try:
        r = requests.get(url, headers=UA, timeout=(8, timeout), allow_redirects=True)
        return r if r.ok and "html" in r.headers.get("content-type", "html") else None
    except Exception:  # noqa: BLE001
        return None


def wikidata_site(name):
    """(website, qid) for a company name, or ("", "")."""
    try:
        s = requests.get("https://www.wikidata.org/w/api.php", params={"action": "wbsearchentities", "search": name[:80], "language": "en", "type": "item", "limit": 5, "format": "json"},
                         headers=UA, timeout=20).json()
    except Exception:  # noqa: BLE001
        return "", ""
    for hit in s.get("search", []):
        label = hit.get("label") or ""
        if not (_close(label, name) or any(_close(a, name) for a in (hit.get("aliases") or []))):
            continue
        if not COMPANY.search(hit.get("description") or ""):
            continue
        try:
            e = requests.get("https://www.wikidata.org/w/api.php", params={"action": "wbgetentities", "ids": hit["id"], "props": "claims", "format": "json"}, headers=UA, timeout=20).json()
            claims = e["entities"][hit["id"]]["claims"].get("P856", [])
            for c in claims:
                v = c["mainsnak"].get("datavalue", {}).get("value")
                if v and v.startswith("http"):
                    return v.rstrip("/"), hit["id"]
        except Exception:  # noqa: BLE001
            continue
        time.sleep(0.3)
    return "", ""


def contacts(site):
    """(emails, phones, page) read from the home page and its contact page."""
    emails, phones, page = [], [], ""
    home = _get(site)
    if not home:
        return emails, phones, page
    pages = [(home.url, home.text)]
    for href in re.findall(r'href="([^"#]+)"', home.text):
        if re.search(r"contact|contacto|contato|kontakt|nous-contacter|contactez|lianxi|%E8%81%94%E7%B3%BB|reach-us|get-in-touch|enquir", href, re.I):
            u = urljoin(home.url, href)
            if urlparse(u).netloc.split(":")[0].endswith(urlparse(home.url).netloc.split(":")[0].replace("www.", "")):
                c = _get(u)
                if c:
                    pages.append((c.url, c.text))
                break
    for url, h in pages:
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)
        for e in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text):
            e = e.lower().strip(".")
            if ROLE.match(e) and not e.endswith((".png", ".jpg", ".gif", ".webp")) and e not in emails:
                emails.append(e); page = page or url
        for t in re.findall(r'href="tel:([^"]+)"', h):
            t = re.sub(r"[^\d+]", "", t)
            if 8 <= len(t.lstrip("+")) <= 15 and t not in phones:
                phones.append(t); page = page or url
    return emails[:4], phones[:3], page


def enrich(rows):
    """Add ws/ce/cp/cs/wd to winner rows in place; looks up at most PER_RUN new or stale winners per run."""
    try:
        cache = json.load(open(CACHE, encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    today = dt.date.today()
    done = 0
    seen = set()
    for r in rows:   # rows come best first, so the lookups go to the best leads
        name = (r.get("w") or [""])[0].strip()
        key = " ".join(_norm(name))
        if not key or key in seen:
            continue
        seen.add(key)
        hit = cache.get(key)
        fresh = hit and (today - dt.date.fromisoformat(hit["at"])).days < TTL_DAYS
        if not fresh and done < PER_RUN:
            site, qid = wikidata_site(name)
            em, ph, page = contacts(site) if site else ([], [], "")
            hit = cache[key] = {"at": today.isoformat(), "ws": site, "wd": qid, "ce": em, "cp": ph, "cs": page}
            done += 1
            time.sleep(1.0)
    found = sum(1 for v in cache.values() if v.get("ws"))
    with_contact = sum(1 for v in cache.values() if v.get("ce") or v.get("cp"))
    for r in rows:
        hit = cache.get(" ".join(_norm((r.get("w") or [""])[0])))
        if hit and hit.get("ws"):
            r.update({k: hit[k] for k in ("ws", "wd", "ce", "cp", "cs") if hit.get(k)})
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    log.info("winner dossier: %d looked up this run; cache %d winners, %d with an official website, %d with a published contact", done, len(cache), found, with_contact)
    return rows
