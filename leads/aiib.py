"""Asian Infrastructure Investment Bank: project procurement notices, procurement plans and contract awards
(the public page's data file ppo-data-all.js)."""
import datetime as dt
import hashlib
import re

from .common import cffi_get, clean, log, rolling, today
from .regions import iso3
from .sectors import classify

URL = "https://www.aiib.org/en/opportunities/business/project-procurement/_common/ppo-data-all.js"
BASE = "https://www.aiib.org"
ST = {"transport": "INFRA", "water": "WATER", "energy": "POWER", "urban": "BUILDING", "health": "HEALTH",
      "education": "BUILDING", "digital": "ICT", "rural": "AGRI_FOOD", "roads": "INFRA", "public health": "HEALTH"}
OPEN = re.compile(r"specific procurement|invitation for (tenders|bids)|request for (bids|tender)|expressions? of interest|"
                  r"pre-?qualification|tender notice", re.I)
PLAN = re.compile(r"procurement plan|general procurement|early market|advance (procurement|contracting)", re.I)


def _d(s):
    try:
        return dt.datetime.strptime(s.strip(), "%b %d, %Y").date()
    except ValueError:
        return None


def _f(rec, k):
    m = re.search(k + r':"((?:[^"\\]|\\.)*)"', rec)
    return clean(m.group(1)) if m else ""


def fetch():
    r = cffi_get(URL)
    if r.status_code != 200:
        log.warning("AIIB %s", r.status_code); return [], {}
    t, new, awards = today(), [], []
    for rec in re.findall(r"\{id:.*?\}", r.text):
        tp, ct = _f(rec, "tp"), _f(rec, "ct")
        pub, dl = _d(_f(rec, "id")), _d(_f(rec, "cd"))
        doc = _f(rec, "dc")
        fname = re.sub(r"[-_]+", " ", doc.rsplit("/", 1)[-1].rsplit(".", 1)[0])
        proj, member, st = _f(rec, "pj"), _f(rec, "mb"), _f(rec, "st").lower()
        title = clean(f"{_f(rec, 'ds') or fname} | {proj}", 300)
        sec = next((v for k, v in ST.items() if k in st), "") or classify(title)[0]
        base = {"source": "AIIB", "group": "", "sector": sec, "nature": "", "cpv": "", "classification": f"AIIB {st}",
                "country": iso3(member) or member, "buyer": f"{proj} (AIIB-financed)"[:120], "title": title,
                "notice_type": tp, "published": str(pub or ""), "value": "", "currency": "",
                "link": BASE + doc if doc.startswith("/") else doc, "contact": "", "lang": ""}
        key = hashlib.md5(f"{doc}|{tp}|{title}".encode()).hexdigest()[:12]
        if ct == "Contract Awards":
            awards.append(dict(base, id=f"AIIB-A-{key}", winner=_f(rec, "cr"), price=_f(rec, "pc"), signed=_f(rec, "sd")))
            continue
        if pub and (t - pub).days > 365:
            continue
        if OPEN.search(tp) and not re.search(r"addend|corrigend|cancel|amend|extension|clarif", tp, re.I):
            if dl and dl < t or (not dl and pub and (t - pub).days > 60):
                continue
            new.append(dict(base, id=f"AIIB-{key}", stage="tender", access="International (AIIB rules)",
                            deadline=str(dl or "")))
        elif PLAN.search(tp) or ct == "Procurement Plan":
            if pub and (t - pub).days > 180:
                continue
            new.append(dict(base, id=f"AIIB-P-{key}", stage="planned", access="International (AIIB rules)",
                            deadline=""))
    rows, _ = rolling("aiib", new, max_age_days=365)
    log.info("AIIB new %d, kept %d, awards %d", len(new), len(rows), len(awards))
    return rows, {"new": len(new), "awards": awards[:400]}
