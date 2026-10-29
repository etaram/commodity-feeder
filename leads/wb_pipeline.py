"""World Bank project pipeline (official Projects API): projects under preparation or newly approved.
Each one becomes a 'planned' notice - the tenders have not been published yet, but the money and the
sector are known. They land in Tenders as stage=planned and in the Upcoming tab (Home: Upcoming tenders)."""
import re

from .common import clean, log, session, today
from .regions import iso3
from .sectors import classify
from .taxonomy import group_of_text

API = "https://search.worldbank.org/api/v3/projects"
FIELDS = "id,project_name,countryshortname,countrycode,status,totalamt,boardapprovaldate,sector1,impagency,url,lendinginstr,projectstatusdisplay"
ACCESS = "International (World Bank financed: open to firms from all member countries, Israel included)"


def _amount(v):
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return ""


def fetch():
    s, t, rows = session(), today(), []
    yr = t.year
    for status in ("Pipeline", "Active"):
        for start in range(0, 3000, 500):
            params = {"format": "json", "rows": 500, "os": start, "fl": FIELDS, "status": status}
            if status == "Active":  # only recently approved projects still have their procurement ahead
                params["boardapprovaldate_exact"] = f"[{yr - 1}-07-01T00:00:00Z TO {yr + 1}-12-31T00:00:00Z]"
            try:
                j = s.get(API, params=params, timeout=90).json()
            except Exception as e:  # noqa: BLE001
                log.warning("wb pipeline %s page %d: %s", status, start, type(e).__name__); break
            projs = j.get("projects") or {}
            items = list(projs.values()) if isinstance(projs, dict) else projs
            if not items:
                break
            for p in items:
                name = clean(p.get("project_name") or "")
                if not name:
                    continue
                sec = ""
                s1 = p.get("sector1")
                if isinstance(s1, dict):
                    sec = s1.get("Name") or ""
                elif isinstance(s1, str):
                    sec = s1
                title = f"{name} ({sec})" if sec else name
                sector, method = classify(title)
                cc = p.get("countrycode") or p.get("countryshortname") or ""
                country = iso3(cc) if cc else ""
                if country in ("", None):
                    continue
                amt = _amount(p.get("totalamt"))
                rows.append({
                    "id": f"WBP-{p.get('id')}", "source": "World Bank pipeline", "group": group_of_text(title) or "",
                    "sector": sector, "cpv": "", "country": country, "nature": "",
                    "buyer": clean(p.get("impagency") or f"Government of {p.get('countryshortname', '')}")[:200],
                    "title": title[:300], "classification": method or "keyword",
                    "notice_type": f"Project {p.get('projectstatusdisplay') or status} | {p.get('lendinginstr') or ''}".strip(" |"),
                    "stage": "planned", "access": ACCESS, "published": (p.get("boardapprovaldate") or "")[:10],
                    "deadline": "", "value": amt, "currency": "USD" if amt != "" else "",
                    "link": p.get("url") or f"https://projects.worldbank.org/en/projects-operations/project-detail/{p.get('id')}",
                    "contact": "", "lang": "en"})
            if len(items) < 500:
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
