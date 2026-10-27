"""World Bank financed procurement notices (goods) - free JSON API, no key."""
import datetime as dt
import re

from .common import clean, log, polite, session, today
from .taxonomy import GROUPS

URL = "https://search.worldbank.org/api/v2/procnotices"
NOISE = re.compile(r"vehicle|equipment|computer|medic|pharma|drug|vaccine|paracetamol|parac|amoxi|furniture|consult")
OPEN_TYPES = {"Invitation for Bids", "Request for Bids", "Request for Quotations", "Invitation for Prequalification",
              "Request for Expression of Interest", "General Procurement Notice"}


def _d(s, fmt=None):
    s = str(s or "")
    for f in ("%Y-%m-%dT%H:%M:%SZ", "%d-%b-%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s[:20] if "T" in s else s, f).date()
        except ValueError:
            continue
    return None


def fetch():
    s = session(); rows, seen, t = [], set(), today()
    for g in GROUPS:
        for kw in g["wb"]:
            try:
                r = s.get(URL, params={"format": "json", "rows": 100, "qterm": kw, "srt": "noticedate",
                                       "order": "desc"}, timeout=60)
                j = r.json()
            except Exception as e:  # noqa: BLE001
                log.warning("WB %s: %s", kw, e); continue
            for n in j.get("procnotices", []):
                if n.get("id") in seen or n.get("procurement_group") not in ("GO", None, ""):
                    continue
                if n.get("procurement_group") is None:
                    continue
                pub, dl = _d(n.get("noticedate")), _d(n.get("submission_deadline_date"))
                if not pub or (t - pub).days > 60 or (dl and dl < t):
                    continue
                if n.get("notice_type") not in OPEN_TYPES:
                    continue
                text = f"{n.get('bid_description', '')}".lower()
                if not re.search(r"\b" + re.escape(kw.lower()) + r"s?\b", text) or NOISE.search(text):
                    continue
                seen.add(n["id"])
                rows.append({
                    "id": f"WB-{n['id']}", "source": "World Bank", "group": g["id"],
                    "country": n.get("project_ctry_name", ""), "buyer": clean(n.get("contact_organization"), 120),
                    "title": clean(f"{n.get('bid_description', '')} | {n.get('project_name', '')}", 300),
                    "classification": f"keyword: {kw}", "notice_type": n.get("notice_type", ""),
                    "published": str(pub), "deadline": str(dl or ""), "value": "", "currency": "",
                    "link": f"https://projects.worldbank.org/en/projects-operations/procurement-detail/{n['id']}",
                    "contact": clean(f"{n.get('contact_name', '')} {n.get('contact_email', '')}", 120),
                })
            polite(1)
    log.info("World Bank rows: %d", len(rows))
    return rows, {}
