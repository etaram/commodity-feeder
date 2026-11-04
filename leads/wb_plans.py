"""World Bank procurement plans and IPF contract awards: the buyers behind the money, before and after the tender.

1. Procurement plans: every IPF project publishes its STEP procurement plan as a document ("Procurement Plan" in
   the Documents & Reports API). A new or updated plan means packages are about to be tendered, months before
   the notices. We keep the latest plan per project (date, country, title, PDF link); the packages inside the PDF
   are read on request in the panel (AI, by click), never here.
2. Contract awards (Finances One dataset DS00005, CC BY 4.0): who won what, where, for how much, with the
   supplier's country. A repeat winner of Bank-financed supply contracts in a region is a customer for sourcing.

Outputs: data/leads/wb_plans.csv, data/leads/wb_awards.csv.  Run inside leads.run: python -m leads.wb_plans
"""
import csv
import datetime as dt

from .common import LEADS, log, session, today
from .regions import iso3, region

DOCS = "https://search.worldbank.org/api/v3/wds"
AWARDS = "https://datacatalogapi.worldbank.org/dexapps/fone/api/view"
PLAN_DAYS = 90


def plans(s):
    since = (today() - dt.timedelta(days=PLAN_DAYS)).strftime("%Y-%m-%d")
    out, seen = [], {}
    for os_ in range(0, 3000, 500):
        try:
            r = s.get(DOCS, params={"format": "json", "docty": "Procurement Plan", "strdate": since, "rows": 500, "os": os_,
                                    "fl": "id,docdt,count,projectid,display_title,pdfurl,url,docty,projn"}, timeout=120)
            docs = (r.json() or {}).get("documents") or {}
        except Exception as e:  # noqa: BLE001
            log.warning("wb plans page %d: %s", os_, type(e).__name__); break
        items = [v for k, v in docs.items() if isinstance(v, dict) and k != "facets"]
        if not items:
            break
        for d in items:
            pid = d.get("projectid") or ""
            cty = d.get("count") or ""
            if isinstance(cty, list):
                cty = cty[0] if cty else ""
            row = {"project_id": pid, "country": iso3(str(cty)) or "", "country_name": str(cty)[:60],
                   "date": (d.get("docdt") or "")[:10], "title": (d.get("display_title") or d.get("projn") or "")[:200],
                   "pdf": d.get("pdfurl") or "", "link": d.get("url") or "", "doc_id": d.get("id") or ""}
            if row["project_id"] and (row["project_id"] not in seen or seen[row["project_id"]]["date"] < row["date"]):
                seen[row["project_id"]] = row
        if len(items) < 500:
            break
    out = sorted(seen.values(), key=lambda x: x["date"], reverse=True)
    for r in out:
        r["region"] = region(r["country"]) if r["country"] else ""
    log.info("wb procurement plans: %d projects with a plan in the last %d days", len(out), PLAN_DAYS)
    return out


def awards(s):
    fy = today().year + (1 if today().month >= 7 else 0)  # Bank fiscal year starts 1 July
    out = []
    for fiscal in (fy, fy - 1):
        skip = 0
        while skip < 20000:
            try:
                r = s.get(AWARDS, params={"viewId": "DS00005", "top": 1000, "skip": skip, "type": "json", "filter": f"fiscal_year={fiscal}"}, timeout=120)
                j = r.json()
            except Exception as e:  # noqa: BLE001
                log.warning("wb awards fy%s skip %d: %s", fiscal, skip, type(e).__name__); break
            rows = j.get("data") if isinstance(j, dict) else j
            if not rows:
                break
            for a in rows:
                out.append({"fiscal_year": a.get("fiscal_year", ""), "country": iso3(str(a.get("borrower_country") or "")) or (a.get("borrower_country_code") or "")[:3],
                            "project_id": a.get("project_id", ""), "project": (a.get("project_name") or "")[:120], "category": a.get("procurement_category", ""),
                            "method": a.get("procurement_method", ""), "practice": a.get("project_global_practice", ""), "description": (a.get("contract_description") or "")[:200],
                            "signed": (a.get("contract_signing_date") or "")[:10], "supplier": (a.get("supplier") or "")[:120],
                            "supplier_country": iso3(str(a.get("supplier_country") or "")) or (a.get("supplier_country_code") or "")[:3],
                            "usd": a.get("supplier_contract_amount_usd", "")})
            if len(rows) < 1000:
                break
            skip += 1000
    log.info("wb contract awards: %d rows (FY%d-%d)", len(out), fy - 1, fy)
    return out


def build():
    s = session()
    p = plans(s)
    with open(LEADS / "wb_plans.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "country", "region", "country_name", "project_id", "title", "pdf", "link", "doc_id"]); w.writeheader(); w.writerows(p)
    a = awards(s)
    if a:
        with open(LEADS / "wb_awards.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(a[0].keys())); w.writeheader(); w.writerows(a)
    return p, a


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    p, a = build()
    print(p[:3]); print(a[:2])
