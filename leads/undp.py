"""UNDP procurement notices (procurement-notices.undp.org): all active notices on the public list page."""
import datetime as dt
import html
import re

from .common import cffi_get, clean, log, rolling, today
from .regions import iso3
from .sectors import classify

URL = "https://procurement-notices.undp.org/"
SKIP = re.compile(r"^IC\b|Individual contractor", re.I)  # individual consultant posts are jobs, not procurement
TYPES = {"ITB": "Invitation to bid", "RFP": "Request for proposal", "RFQ": "Request for quotation",
         "ITP": "Invitation to pre-qualify", "EOI": "Expression of interest", "RFI": "Request for information"}


def _d(s):
    m = re.search(r"(\d{1,2})-([A-Za-z]{3})-(\d{2})", s or "")
    if not m:
        return None
    try:
        return dt.datetime.strptime(f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "%d-%b-%y").date()
    except ValueError:
        return None


def fetch():
    r = cffi_get(URL)
    if r.status_code != 200:
        log.warning("UNDP %s", r.status_code); return [], {}
    t, new = today(), []
    for a in re.finditer(r'<a href="(view_notice\.cfm\?notice_id=(\d+))"[^>]*vacanciesTable__row[^>]*>(.*?)</a>', r.text, re.S):
        cells = [clean(html.unescape(re.sub(r"<[^>]+>", " ", c))) for c in re.findall(r"<span>(.*?)</span>", a.group(3), re.S)]
        if len(cells) < 6:
            continue
        title, ref, office, proc, deadline, posted = cells[:6]
        if SKIP.search(proc) or proc.startswith("RFI"):
            continue
        dl, pub = _d(deadline), _d(posted)
        if dl and dl < t:
            continue
        country = office.split("/")[-1].strip().title()
        sector, method = classify(title)
        new.append({
            "id": f"UNDP-{a.group(2)}", "source": "UNDP", "group": "", "sector": sector, "nature": "",
            "cpv": "", "classification": method, "country": iso3(country) or country, "buyer": office[:120],
            "title": title[:300], "notice_type": proc, "stage": "tender", "access": "International (UN)",
            "published": str(pub or ""), "deadline": str(dl or ""), "value": "", "currency": "",
            "link": URL + a.group(1), "contact": "", "lang": "",
        })
    rows, _ = rolling("undp", new)
    log.info("UNDP new %d, open %d", len(new), len(rows))
    return rows, {"new": len(new), "cache": len(rows)}
