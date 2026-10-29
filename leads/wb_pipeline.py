"""World Bank project pipeline (official Projects API): projects under preparation or newly approved.
Each one becomes a 'planned' notice - the tenders have not been published yet, but the money and the
sector are known. They land in Tenders as stage=planned and in the Upcoming tab (Home: Upcoming tenders)."""
import re

from .common import clean, log, session, today
from .regions import iso3
from .sectors import classify
from .taxonomy import group_of_text

API = "https://search.worldbank.org/api/v3/projects"
FIELDS = "id,project_name,countryshortname,countrycode,status,totalamt,boardapprovaldate,sector1,impagency,url,lendinginstr,projectstatusdisplay,project_abstract"
ACCESS = "International (World Bank financed: open to firms from all member countries, Israel included)"


def _amount(v):
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return ""


def fetch():
    s, t, rows = session(), today(), []
    yr = t.year
    # the API ignores status filters, but returns projects newest board date first: read the first pages and
    # keep pipeline projects plus those approved in the last 15 months (their procurement is still ahead)
    cutoff = f"{yr - 1}-07-01"
    for start in range(0, 6000, 1000):
        try:
            j = s.get(API, params={"format": "json", "rows": 1000, "os": start, "fl": FIELDS}, timeout=120).json()
        except Exception as e:  # noqa: BLE001
            log.warning("wb pipeline page %d: %s", start, type(e).__name__); break
        projs = j.get("projects") or {}
        items = list(projs.values()) if isinstance(projs, dict) else projs
        if not items:
            break
        if True:
            for p in items:
                status = p.get("status") or p.get("projectstatusdisplay") or ""
                bd = (p.get("boardapprovaldate") or "")[:10]
                if status != "Pipeline" and not (bd >= cutoff):
                    continue
                pn = p.get("project_name")
                name = clean(pn[0] if isinstance(pn, list) else (pn or ""))
                if not name:
                    continue
                sec = ""
                s1 = p.get("sector1")
                if isinstance(s1, dict):
                    sec = s1.get("Name") or ""
                elif isinstance(s1, list) and s1:
                    sec = s1[0].get("Name", "") if isinstance(s1[0], dict) else str(s1[0])
                elif isinstance(s1, str):
                    sec = s1
                title = f"{name} ({sec})" if sec else name
                sector, method = classify(title)
                cc = p.get("countrycode") or p.get("countryshortname") or ""
                if isinstance(cc, list):
                    cc = cc[0] if cc else ""
                if isinstance(cc, dict):
                    cc = cc.get("code") or cc.get("name") or ""
                country = iso3(str(cc)) if cc else ""
                if not country or len(country) != 3:
                    continue  # regional / multi-country projects have no single buyer country
                amt = _amount(p.get("totalamt"))
                rows.append({
                    "id": f"WBP-{p.get('id')}", "source": "World Bank pipeline", "group": group_of_text(title) or "",
                    "sector": sector, "cpv": "", "country": country, "nature": "",
                    "buyer": clean(str(p.get("impagency") or f"Government of {p.get('countryshortname', '')}"))[:200],
                    "title": title[:300], "classification": method or "keyword",
                    "notice_type": f"Project {p.get('projectstatusdisplay') or status} | {p.get('lendinginstr') or ''}".strip(" |"),
                    "stage": "planned", "access": ACCESS, "published": (p.get("boardapprovaldate") or "")[:10],
                    "deadline": "", "value": amt, "currency": "USD" if amt != "" else "",
                    "link": p.get("url") or f"https://projects.worldbank.org/en/projects-operations/project-detail/{p.get('id')}",
                    "contact": "", "lang": "en"})
        if len(items) < 1000:
            break
    seen, out = set(), []
    for r in rows:
        if r["id"] not in seen:
            seen.add(r["id"]); out.append(r)
    log.info("World Bank pipeline: %d projects (pipeline + recently approved)", len(out))
    return out, {"projects": len(out)}


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    r, m = fetch()
    print(m)
    for x in r[:5]:
        print(x["country"], x["value"], x["title"][:70], x["buyer"][:40])
