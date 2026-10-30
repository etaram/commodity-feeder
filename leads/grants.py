"""Calls for proposals, grants and government incentive programmes - official sources only.

  US grants.gov (official API, no key): posted and forecasted funding opportunities. Searched with Sinder's themes
      (energy, water, infrastructure, agriculture, health, Africa, Israel, international) and kept when the
      opportunity is open to any applicant type ("unrestricted") or concerns work abroad.
  EU Funding & Tenders portal (public SEDIA search API): open and forthcoming calls.
  Israel data.gov.il: government calls for proposals published as open datasets (קולות קוראים).

Output: data/leads/grants.csv, one row per call, soonest deadline first. The incentives agent reads it and adds the
programmes that need judgement (foreign investor incentives, export credit, development finance windows).
"""
import csv
import datetime as dt
import json
import re
import time

from .common import LEADS, clean, log, session, today

OUT = LEADS / "grants.csv"
GG = "https://api.grants.gov/v1/api/search2"
EU = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
IL = "https://data.gov.il/api/3/action/package_search"
THEMES = ["energy", "solar", "water", "infrastructure", "agriculture", "food security", "health equipment", "Africa",
          "Israel", "international", "trade", "manufacturing", "clean technology", "transport", "defense industrial"]
SECTOR = [("Energy, fuels & utilities", r"energy|solar|power|grid|electric|renewable|hydrogen|fuel"),
          ("Water & wastewater", r"water|sanitation|wastewater|irrigation"),
          ("Agriculture & food", r"agricultur|food|farm|crop|fisher"),
          ("Healthcare & pharmaceuticals", r"health|medical|hospital|vaccine|pharma"),
          ("Transport & civil infrastructure works", r"transport|road|rail|port|infrastructure|bridge"),
          ("ICT & telecom", r"digital|cyber|broadband|telecom|software|data"),
          ("Defence & security", r"defen[cs]e|security|military"),
          ("Industrial & construction machinery", r"manufactur|industr|equipment|machinery")]


DOMESTIC = re.compile(r"crime|violen|justice|police|tribal|indian|native american|k-12|school|student|youth|"
                      r"housing|homeless|veteran|opioid|substance|mental|juvenile|museum|librar|arts|humanities|"
                      r"historic|appalach|rural community|faith|child|elder|aging|disabilit|prison|court", re.I)
ABROAD = re.compile(r"international|global|foreign|africa|asia|latin america|middle east|israel|overseas|export|"
                    r"usaid|development|humanitarian|bilateral", re.I)


def _sector(text):
    return next((n for n, rx in SECTOR if re.search(rx, text, re.I)), "Other")


def _gg_date(s):
    try:
        return str(dt.datetime.strptime(s, "%m/%d/%Y").date())
    except (TypeError, ValueError):
        return ""


def grants_gov(s):
    seen, out = set(), []
    for kw in THEMES:
        for start in (0, 100):
            try:
                r = s.post(GG, json={"rows": 100, "startRecordNum": start, "keyword": kw, "oppStatuses": "forecasted|posted",
                                     "eligibilities": "99|25"}, timeout=60)
                hits = ((r.json() or {}).get("data") or {}).get("oppHits") or []
            except Exception as e:  # noqa: BLE001
                log.warning("grants.gov %s: %s", kw, str(e)[:120]); break
            for h in hits:
                if h["id"] in seen:
                    continue
                seen.add(h["id"])
                title = clean(h.get("title") or "", 250)
                if DOMESTIC.search(title) or _sector(title) == "Other" and not ABROAD.search(title):
                    continue  # US domestic social programmes and topics Sinder cannot supply
                out.append({
                    "source": "grants.gov (US)", "program": h.get("number", ""), "title": title,
                    "funder": clean(h.get("agency") or h.get("agencyCode") or "", 120), "region": "United States / worldwide",
                    "sector": _sector(title), "status": h.get("oppStatus", ""), "opens": _gg_date(h.get("openDate")),
                    "closes": _gg_date(h.get("closeDate")), "eligibility": "unrestricted or other (check the notice)",
                    "link": f"https://www.grants.gov/search-results-detail/{h['id']}", "id": f"GG-{h['id']}",
                })
            if len(hits) < 100:
                break
            time.sleep(0.5)
        time.sleep(0.5)
    log.info("grants.gov: %d calls", len(out))
    return out


def eu_calls(s):
    out = []
    for page in range(1, 6):
        try:
            r = s.post(EU, params={"apiKey": "SEDIA", "text": "***", "pageSize": 100, "pageNumber": page},
                       files={"query": ("blob", json.dumps({"bool": {"must": [{"terms": {"type": ["1", "2"]}},
                                                                              {"terms": {"status": ["31094501", "31094502"]}}]}}), "application/json"),
                              "languages": ("blob", json.dumps(["en"]), "application/json"),
                              "sort": ("blob", json.dumps({"field": "sortStatus", "order": "ASC"}), "application/json")}, timeout=60)
            res = (r.json() or {}).get("results") or []
        except Exception as e:  # noqa: BLE001
            log.warning("EU calls p%d: %s", page, str(e)[:120]); break
        for x in res:
            md = x.get("metadata") or {}
            g = lambda k: (md.get(k) or [""])[0] if isinstance(md.get(k), list) else (md.get(k) or "")  # noqa: E731
            ident = g("identifier") or x.get("reference", "")
            title = clean(g("title") or x.get("summary") or "", 250)
            close = (g("deadlineDate") or "")[:10]
            if close and close < str(today()):
                continue
            out.append({
                "source": "EU Funding & Tenders", "program": clean(g("frameworkProgramme") or g("programmeDivision") or "", 80),
                "title": title, "funder": "European Commission", "region": "EU and associated countries",
                "sector": _sector(title), "status": "open" if g("status") == "31094502" else "forthcoming",
                "opens": (g("startDate") or "")[:10], "closes": close,
                "eligibility": "EU and associated countries (Israel is associated to Horizon Europe)",
                "link": f"https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/{ident.lower()}" if ident else x.get("url", ""),
                "id": f"EU-{ident}",
            })
        if len(res) < 100:
            break
        time.sleep(1)
    log.info("EU calls: %d", len(out))
    return out


def israel_calls(s):
    out = []
    try:
        r = s.get(IL, params={"q": "קול קורא", "rows": 100, "sort": "metadata_modified desc"}, timeout=60)
        res = (r.json() or {}).get("result", {}).get("results") or []
    except Exception as e:  # noqa: BLE001
        log.warning("IL calls: %s", str(e)[:120]); res = []
    for p in res:
        mod = (p.get("metadata_modified") or "")[:10]
        if mod < str(today() - dt.timedelta(days=400)):
            continue
        out.append({
            "source": "data.gov.il (Israel)", "program": p.get("name", ""), "title": clean(p.get("title") or "", 250),
            "funder": clean((p.get("organization") or {}).get("title") or "", 120), "region": "Israel",
            "sector": _sector(p.get("title") or ""), "status": "published", "opens": mod, "closes": "",
            "eligibility": "see the call", "link": f"https://data.gov.il/dataset/{p.get('name', '')}", "id": f"IL-{p.get('name', '')}",
        })
    log.info("Israel calls: %d", len(out))
    return out


def fetch():
    s = session()
    rows = []
    for fn in (grants_gov, eu_calls, israel_calls):
        try:
            rows += fn(s)
        except Exception as e:  # noqa: BLE001
            log.warning("grants %s: %s", fn.__name__, e)
    rows.sort(key=lambda r: (r["closes"] or "9999", r["source"]))
    if rows:
        with open(OUT, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    stats = {"calls": len(rows), **{k: sum(1 for r in rows if r["source"].startswith(k)) for k in ("grants.gov", "EU", "data.gov.il")}}
    log.info("grants %s", stats)
    return [], stats


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    fetch()
