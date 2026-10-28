"""World Bank financed procurement notices - free JSON API, no key.

Sweeps every recent notice (goods, works, non-consulting and consulting services), keeps open calls and general
procurement notices (early pipeline), and classifies each by sector. Rolling cache keeps the open set.
"""
import datetime as dt
import html
import re

from .common import cache_empty, clean, log, polite, rolling, session, today
from .regions import iso3
from .sectors import classify
from .taxonomy import group_of_text

URL = "https://search.worldbank.org/api/v2/procnotices"
OPEN_TYPES = {"Invitation for Bids", "Request for Bids", "Request for Quotations", "Invitation for Prequalification",
              "Request for Expression of Interest", "Request for Proposals", "Invitation for Prequalification"}
PLANNED = {"General Procurement Notice"}
GROUP = {"GO": "goods", "CW": "works", "NC": "services", "CS": "services"}


def _d(s):
    s = str(s or "")
    for f in ("%Y-%m-%dT%H:%M:%SZ", "%d-%b-%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s[:20] if "T" in s else s, f).date()
        except ValueError:
            continue
    return None


def fetch():
    s, t = session(), today()
    days = 60 if cache_empty("worldbank") else 10
    cut = t - dt.timedelta(days=days)
    new, offset, done = [], 0, False
    while not done and offset < 20000:
        try:
            j = s.get(URL, params={"format": "json", "rows": 500, "os": offset, "srt": "noticedate", "order": "desc"},
                      timeout=90).json()
        except Exception as e:  # noqa: BLE001
            log.warning("WB offset %d: %s", offset, e); break
        batch = j.get("procnotices", [])
        if not batch:
            break
        for n in batch:
            pub, dl = _d(n.get("noticedate")), _d(n.get("submission_deadline_date"))
            if pub and pub < cut:
                done = True; continue
            nt = n.get("notice_type", "")
            if nt not in OPEN_TYPES and nt not in PLANNED:
                continue
            if dl and dl < t:
                continue
            desc = html.unescape(n.get("bid_description", "") or "")
            text = f"{desc} | {n.get('project_name', '')}"
            sector, method = classify(desc) if desc else ("", "")
            if not sector:
                sector, method = classify(text)
            pg = n.get("procurement_group") or ""
            new.append({
                "id": f"WB-{n['id']}", "source": "World Bank", "group": group_of_text(desc) or "" if pg == "GO" else "",
                "sector": sector, "nature": GROUP.get(pg, ""), "cpv": "", "classification": f"{pg} {method}".strip(),
                "country": iso3(n.get("project_ctry_name", "")) or n.get("project_ctry_name", ""),
                "buyer": clean(n.get("contact_organization"), 120), "title": clean(text, 300),
                "notice_type": nt, "stage": "planned" if nt in PLANNED else "tender",
                "access": "International (World Bank rules)" if n.get("procurement_method_code") in
                          ("RFB", "ICB", "RFP", "PQ", "IPQ", "QCBS", "QBS", "CQS") else "World Bank financed",
                "published": str(pub or ""), "deadline": str(dl or ""), "value": "", "currency": "",
                "link": f"https://projects.worldbank.org/en/projects-operations/procurement-detail/{n['id']}",
                "contact": clean(f"{n.get('contact_name', '')} {n.get('contact_email', '')} {n.get('contact_phone_no', '')}", 140),
                "project": clean(f"{n.get('project_id', '')} {n.get('project_name', '')}", 140),
            })
        offset += 500
        polite(0.5)
    rows, size = rolling("worldbank", new)
    log.info("World Bank new %d, open cache %d", len(new), len(rows))
    return rows, {"new": len(new), "cache": len(rows), "days": days}
