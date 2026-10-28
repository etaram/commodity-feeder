"""Company contact enrichment from the company's own website: role-based e-mails (info@, sales@, export@ ...) and
phone found on the home page or a contact page. Only for suppliers that have a website and no e-mail yet.
Polite: one request at a time per site, short timeouts, robots.txt respected, ~500 sites per run.
Results go to the private contacts cache (never to the public repository)."""
import csv
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests

from .common import PRIVATE, log

UA = "Mozilla/5.0 (compatible; SinderSupplierResearch/1.0; +https://github.com/etaram/commodity-feeder)"
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ROLE = re.compile(r"^(info|sales|export|exports|contact|contacto|contato|kontakt|office|trade|trading|commercial|comercial|"
                  r"vendas|ventas|enquiries|inquiries|hello|marketing|orders|business|bd|procurement|tender|tenders)\b", re.I)
PHONE = re.compile(r"(?:\+|00)\d[\d\s().-]{7,18}\d")
PATHS = ["", "contact", "contact-us", "contacts", "contacto", "contato", "kontakt", "en/contact", "about"]
PER_RUN = 500


def _site(url):
    if not url.startswith("http"):
        url = "http://" + url
    base = "{0.scheme}://{0.netloc}/".format(urlsplit(url))
    dom = urlsplit(base).netloc.lower().removeprefix("www.")
    s = requests.Session(); s.headers["User-Agent"] = UA
    rp = RobotFileParser()
    try:
        rr = s.get(urljoin(base, "robots.txt"), timeout=8)
        rp.parse(rr.text.splitlines() if rr.status_code == 200 else [])
    except Exception:  # noqa: BLE001
        rp.parse([])
    emails, phones = [], []
    for path in PATHS:
        u = urljoin(base, path)
        if not rp.can_fetch(UA, u):
            continue
        try:
            r = s.get(u, timeout=10)
        except Exception:  # noqa: BLE001
            continue
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            continue
        txt = r.text[:400_000]
        for e in EMAIL.findall(txt.replace("mailto:", " ")):
            e = e.strip(".").lower()
            if e.endswith((".png", ".jpg", ".gif", ".webp", ".svg")):
                continue
            if dom.split(".")[-2] in e.split("@")[1] and ROLE.match(e.split("@")[0]) and e not in emails:
                emails.append(e)
        if not phones:
            phones = [p.strip() for p in PHONE.findall(re.sub(r"<[^>]+>", " ", txt))[:1]]
        if emails:
            break
        time.sleep(0.5)
    return {"email": "; ".join(emails[:2]), "phone": phones[0] if phones else "", "website": base}


def fetch():
    src = PRIVATE / "universe.csv"
    if not src.exists():
        return [], {"note": "no universe yet"}
    done_p = PRIVATE / "web_checked.txt"
    done = set(done_p.read_text().split("\n")) if done_p.exists() else set()
    todo = []
    for r in csv.DictReader(open(src, encoding="utf-8")):
        w = (r.get("website") or "").strip()
        if w and not r.get("email") and w not in done:
            todo.append((r["supplier"], r["country"], w))
        if len(todo) >= PER_RUN:
            break
    found = 0
    with ThreadPoolExecutor(max_workers=12) as ex, open(PRIVATE / "contacts_web.jsonl", "a", encoding="utf-8") as f:
        for (name, country, w), res in zip(todo, ex.map(lambda x: _safe(x[2]), todo)):
            done.add(w)
            if res and (res["email"] or res["phone"]):
                found += 1
                f.write(json.dumps({"name": name, "country": country, "email": res["email"], "phone": res["phone"],
                                    "website": res["website"], "address": "", "legal_id": "", "source": "website"},
                                   ensure_ascii=False) + "\n")
    done_p.write_text("\n".join(sorted(done)))
    log.info("web contacts: %d sites checked, %d with contacts", len(todo), found)
    return [], {"checked": len(todo), "found": found}


def _safe(url):
    try:
        return _site(url)
    except Exception:  # noqa: BLE001
        return None
