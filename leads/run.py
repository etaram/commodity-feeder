"""Leads engine: tenders (TED, World Bank, mr.gov.il) + US import buyers and suppliers (ImportYeti).

  python -m leads.run --source ted|worldbank|mrgov|importyeti   one source -> data/leads/partial/<source>.json
  python -m leads.run --merge                                    -> data/leads/*.csv for the Leads sheet
"""
import argparse
import csv
import datetime as dt
import json
import logging
import re
import sys
import traceback
from collections import defaultdict
from statistics import median
from urllib.parse import quote_plus

from .common import DATA, LEADS, PARTIAL, benchmarks, fmt_bench, log, master_rows, save_partial, today
from .taxonomy import BY_ID, CH2GROUP, match_cpv

TENDER_SOURCES = ["ted", "fts", "sam", "canadabuys", "za", "worldbank", "ebrd", "mrgov"]
STOP = {"products", "other", "than", "with", "from", "parts", "thereof", "whether", "nonalloy", "including",
        "articles", "prepared", "preserved", "fresh", "chilled", "frozen", "similar", "suitable", "kind", "used"}


def run_source(name):
    if name == "ted":
        from . import ted as m
    elif name == "worldbank":
        from . import worldbank as m
    elif name == "mrgov":
        from . import mrgov as m
    elif name == "importyeti":
        from . import importyeti as m
    elif name == "sam":
        from . import sam as m
    elif name == "canadabuys":
        from . import canadabuys as m
    elif name == "za":
        from . import za as m
    elif name == "markets":
        from . import markets as m
    elif name == "fts":
        from . import fts as m
    elif name == "ebrd":
        from . import ebrd as m
    elif name == "awards":
        from . import awards as m
    elif name == "enrich":
        from . import enrich
        imp, _, _ = merge_importyeti(benchmarks(), {})
        names = [r["company"] for r in sorted(imp, key=lambda r: (r["relevance"] != "match", -r["shipments_12m"]))]
        enrich.run(list(dict.fromkeys(names)))
        return
    else:
        raise SystemExit(f"unknown source {name}")
    rows, meta = m.fetch()
    save_partial(name, rows, meta)
    log.info("%s: %d rows", name, len(rows))


def _rates():
    try:
        from feeder.fx import usd_per_unit
        return usd_per_unit()[0]
    except Exception:  # noqa: BLE001
        return {"EUR": 1.08, "ILS": 0.27, "GBP": 1.27}


def _group_bench(bm):
    out = {}
    for gid, g in BY_ID.items():
        out[gid] = " | ".join(fmt_bench(bm[r]) for r in g["ref"] if r in bm)
    return out


def score(r, usd, days, new):
    """0-100: size of the order, time left to bid, how precisely it matches a tracked commodity, region."""
    v = 8 if usd == "" else 4 if usd < 50_000 else 10 if usd < 250_000 else 18 if usd < 1_000_000 else \
        25 if usd < 5_000_000 else 30
    d = 10 if days == "" else 0 if days < 3 else 10 if days <= 7 else 20 if days <= 30 else 15
    m = r.get("match")
    m = 15 if m in (None, "") else 20 if m >= 5 else 14 if m >= 4 else 8
    reg = 20 if r["country"] == "ISR" else 15 if r["source"] in ("World Bank", "eTenders (South Africa)") else 10
    pen = 15 if "exemption" in r["source"] else 0  # intent to contract with a named supplier: objection window only
    return max(0, v + d + m + reg + (5 if new else 0) + (5 if r.get("contact") else 0) - pen)


def merge_tenders(bm, seen):
    rates, gb, t = _rates(), _group_bench(bm), today()
    rows, status = [], []
    for s in TENDER_SOURCES:
        p = PARTIAL / f"{s}.json"
        if not p.exists():
            status.append([s, "", 0, "no data"]); continue
        j = json.loads(p.read_text())
        status.append([s, j.get("ran", ""), len(j["rows"]), "OK" if j["rows"] else "EMPTY"])
        rows += j["rows"]
    out = []
    for r in rows:
        g = BY_ID.get(r["group"], {})
        first = seen.setdefault(r["id"], str(t))
        usd = ""
        if r.get("value") not in ("", None) and r.get("currency") in rates:
            usd = round(float(r["value"]) * rates[r["currency"]])
        dl = r.get("deadline") or ""
        days = (dt.date.fromisoformat(dl) - t).days if dl else ""
        new = (t - dt.date.fromisoformat(first)).days <= 2
        out.append({
            "score": score(r, usd, days, new),
            "new": "NEW" if new else "",
            "deadline": dl, "days_left": days, "group": g.get("name", r["group"]), "source": r["source"],
            "country": r["country"], "buyer": r["buyer"], "title": r["title"], "est_value_usd": usd,
            "est_value": r.get("value", ""), "currency": r.get("currency", ""), "published": r["published"],
            "notice_type": r["notice_type"], "classification": r["classification"], "contact": r.get("contact", ""),
            "benchmark": gb.get(r["group"], ""), "link": r["link"], "first_seen": first, "id": r["id"],
        })
    out.sort(key=lambda x: (-x["score"], x["deadline"] or "9999"))
    return out, status


def _relevant(title, products, g):
    extra = " ".join([g.get("name", "")] + g.get("wb", []))
    words = {w for w in re.findall(r"[a-z]{4,}", f"{title} {extra}".lower()) if w not in STOP}
    p = products.lower()
    return "match" if any(w[:5] in p for w in words) else "unclear"


def merge_importyeti(bm, web=None):
    web = web or {}
    hs_rows = {}
    for r in master_rows():
        h = (r["hs6"] or "")[:4]
        if len(h) == 4:
            hs_rows.setdefault(h, []).append(int(r["row"]))
    imp, sup, n = [], [], 0
    for f in sorted((LEADS / "importyeti").glob("*.json")):
        p = json.loads(f.read_text()); n += 1
        h = p["hs4"]; g = BY_ID.get(CH2GROUP.get(h[:2], ""), {})
        title = re.sub(r"^\d{4}-", "", p["title"]).replace("-", " ").title()
        bench = next((fmt_bench(bm[r]) for r in hs_rows.get(h, []) if r in bm), "")
        recs = sorted(p["records"], key=lambda x: (-x["shipments_12m"], -x["total_shipments"]))
        for role, lst, cap in (("importer", imp, 10), ("supplier", sup, 6)):
            k = 0
            for x in recs:
                if x["role"] != role or (role == "importer" and x["forwarder"]):
                    continue
                k += 1
                if k > cap:
                    break
                lst.append({
                    "hs4": f"HS {h}", "heading": title[:70], "group": g.get("name", ""), "company": x["company"],
                    "country": x["country"], "shipments_12m": x["shipments_12m"],
                    "total_shipments": x["total_shipments"], "weight_t": x["weight_t"], "teu": x["teu"],
                    "hs_codes": "HS " + x["hs_codes"], "products": x["products"][:100],
                    "relevance": _relevant(title, x["products"], g), "flags": x["flags"],
                    "address": x["address"][:70], "benchmark": bench if role == "importer" else "", "profile": x["profile"], "scanned": p["scanned"],
                    "website_wikidata": (web.get(x["company"]) or {}).get("website", "") if role == "importer" else "",
                })
    return imp, sup, n


def _norm_buyer(b):
    return re.sub(r"\s+", " ", re.sub(r"[^\w ]", " ", b.lower())).strip()


def merge_awards():
    rates, t = _rates(), today()
    rows = []
    for f in sorted((LEADS / "awards").glob("*.json")):
        for r in json.loads(f.read_text()):
            gid, _ = match_cpv(r["cpv"].split()[:1])
            if gid:
                r["group"] = gid; rows.append(r)
    for r in rows:
        v, c = r.get("value"), r.get("currency")
        r["usd"] = round(v * rates[c]) if isinstance(v, (int, float)) and c in rates else ""
        if r["usd"] != "" and r["usd"] > 2_000_000_000:  # framework ceilings and data-entry errors
            r["usd"] = ""
        r["gname"] = BY_ID.get(r["group"], {}).get("name", r["group"])
    cut = str(t - dt.timedelta(days=180))
    recent = sorted((r for r in rows if r["published"] >= cut), key=lambda r: -(r["usd"] or 0))[:2000]
    write("awards.csv", [{
        "published": r["published"], "group": r["gname"], "country": r["country"], "buyer": r["buyer"],
        "title": r["title"][:200], "winners": "; ".join(r["winners"])[:200], "winner_country": r["winner_country"],
        "winner_size": r["winner_size"], "value_usd": r["usd"], "value": r["value"], "currency": r["currency"],
        "bids": r["bids"], "buyer_email": r["email"], "link": f"https://ted.europa.eu/en/notice/-/detail/{r['pn']}",
    } for r in recent])
    by = defaultdict(list)
    for r in rows:
        by[(_norm_buyer(r["buyer"]), r["country"], r["gname"])].append(r)
    buyers = []
    for (_, country, g), lst in by.items():
        if len(lst) < 2:
            continue
        lst.sort(key=lambda r: r["published"])
        dates = [dt.date.fromisoformat(r["published"]) for r in lst if r["published"]]
        gaps = [(b - a).days for a, b in zip(dates, dates[1:]) if (b - a).days > 20]
        step = median(gaps) if gaps else 365
        nxt = dates[-1] + dt.timedelta(days=step) if dates else ""
        wins = defaultdict(int)
        for r in lst:
            for w in r["winners"]:
                wins[w] += 1
        months = sorted({d.strftime("%b") for d in dates}, key=lambda m: dt.datetime.strptime(m, "%b").month)
        buyers.append({
            "buyer": lst[-1]["buyer"], "country": country, "group": g, "awards_12m": len(lst),
            "total_usd": round(sum(r["usd"] or 0 for r in lst)), "award_months": " ".join(months),
            "median_award_usd": round(median([r["usd"] for r in lst if r["usd"]])) if any(r["usd"] for r in lst) else "",
            "last_award": lst[-1]["published"], "next_expected": str(nxt),
            "current_suppliers": "; ".join(w for w, _ in sorted(wins.items(), key=lambda x: -x[1])[:3])[:200],
            "avg_bids": round(sum(r["bids"] for r in lst if r["bids"] != "") / max(1, sum(1 for r in lst if r["bids"] != "")), 1),
            "buyer_email": next((r["email"] for r in reversed(lst) if r["email"]), ""),
            "last_notice": f"https://ted.europa.eu/en/notice/-/detail/{lst[-1]['pn']}",
        })
    buyers.sort(key=lambda b: (-b["total_usd"], -b["awards_12m"]))
    write("buyers.csv", buyers[:3000])
    comp = defaultdict(lambda: {"wins": 0, "usd": 0, "buyers": set(), "countries": set(), "wc": ""})
    for r in rows:
        share = (r["usd"] or 0) / max(1, len(r["winners"]))
        for w in r["winners"]:
            c = comp[(w, r["gname"])]
            c["wins"] += 1; c["usd"] += share; c["buyers"].add(_norm_buyer(r["buyer"])); c["countries"].add(r["country"])
            c["wc"] = c["wc"] or r["winner_country"].split(",")[0]
    out = [{"supplier": w, "group": g, "supplier_country": c["wc"], "wins_12m": c["wins"], "won_usd_est": round(c["usd"]),
            "buyers": len(c["buyers"]), "buyer_countries": " ".join(sorted(c["countries"]))[:80]}
           for (w, g), c in comp.items()]
    out.sort(key=lambda x: (-x["won_usd_est"], -x["wins_12m"]))
    write("competitors.csv", out[:2500])
    log.info("awards %d (12m), recent %d, buyers %d, competitors %d", len(rows), len(recent), len(buyers), len(out))
    return buyers


def _bench_usd_kg(bm, hs6):
    rows = [r for r in master_rows() if r["hs6"] == hs6]
    for r in rows:
        b = bm.get(int(r["row"]))
        if b and b[2] in ("USD/kg", "USD/t"):
            return (b[1] if b[2] == "USD/kg" else b[1] / 1000), b[3]
    return None, ""


def merge_markets(bm):
    d = LEADS / "markets"
    if not d.exists():
        return []
    names = json.loads((d / "_reporters.json").read_text()) if (d / "_reporters.json").exists() else {}
    hs_name = {r["hs6"]: r["name"] for r in master_rows()}
    out = []
    for f in sorted(d.glob("[0-9]*.json")):
        m = json.loads(f.read_text()); h = m["hs6"]
        world = sum(x["v"] for x in m["last"].values()) or 1
        bench, bsrc = _bench_usd_kg(bm, h)
        for code, cur in m["last"].items():
            if code in ("0", "97", "490") or cur["v"] < 5_000_000:
                continue
            prev = m["prev"].get(code, {}).get("v", 0)
            growth = (cur["v"] / prev - 1) if prev else None
            uv = cur["v"] / cur["kg"] if cur["kg"] else None
            prem = (uv / bench - 1) if (uv and bench) else None
            score = min(40, cur["v"] / world * 400) + (min(40, max(0, growth) * 100) if growth is not None else 20) + \
                (min(20, max(0, prem) * 50) if prem is not None else 0)
            out.append({
                "hs6": f"HS {h}", "product": hs_name.get(h, "")[:80], "group": BY_ID[m["group"]]["name"],
                "country": names.get(code, code), "year": m["years"][1], "imports_usd": round(cur["v"]),
                "prev_year_usd": round(prev), "growth_pct": round(growth * 100, 1) if growth is not None else "",
                "world_share_pct": round(cur["v"] / world * 100, 2),
                "unit_value_usd_kg": round(uv, 3) if uv else "", "benchmark_usd_kg": round(bench, 3) if bench else "",
                "premium_vs_benchmark_pct": round(prem * 100, 1) if prem is not None else "",
                "benchmark_source": bsrc, "signal_score": round(score), "fetched": m["fetched"],
            })
    out.sort(key=lambda x: -x["signal_score"])
    write("markets.csv", out[:3000])
    log.info("market signals rows %d", len(out))
    return out


def merge_opportunities(tenders, buyers, markets):
    """One pool of deal hypotheses for the Deal Desk: open tenders, predicted re-tenders, price arbitrage."""
    from .regions import region
    t = today(); out = []
    bids = {(_norm_buyer(b["buyer"]), b["country"]): b for b in buyers}
    for r in tenders:
        if r["score"] < 55:
            continue
        b = bids.get((_norm_buyer(r["buyer"]), r["country"]))
        out.append({
            "opp_id": f"T:{r['id']}", "type": "Tender", "group": r["group"], "country": r["country"],
            "region": region(r["country"]), "buyer": r["buyer"], "what": r["title"][:160], "hs6": "",
            "buyer_price_usd_kg": "", "benchmark_usd_kg": "", "spread_pct": "",
            "deal_value_usd": r["est_value_usd"], "market_imports_usd": "",
            "competitors_est": b["avg_bids"] if b and b["avg_bids"] else "",
            "incumbent": b["current_suppliers"][:120] if b else "", "key_date": r["deadline"],
            "link": r["link"], "evidence": f"open tender, score {r['score']}, closes {r['deadline'] or 'n/a'}",
            "contact": r.get("contact", ""),
        })
    for b in buyers:
        nxt = b["next_expected"]
        if not nxt or not (str(t) <= nxt <= str(t + dt.timedelta(days=120))) or not b["total_usd"]:
            continue
        out.append({
            "opp_id": f"R:{_norm_buyer(b['buyer'])[:40]}|{b['country']}|{b['group'][:12]}", "type": "Recompete",
            "group": b["group"], "country": b["country"], "region": region(b["country"]), "buyer": b["buyer"],
            "what": f"Expected new tender ({b['award_months']} buying pattern, {b['awards_12m']} awards in 12 months)",
            "hs6": "", "buyer_price_usd_kg": "", "benchmark_usd_kg": "", "spread_pct": "",
            "deal_value_usd": b["median_award_usd"], "market_imports_usd": "",
            "competitors_est": b["avg_bids"] or "", "incumbent": b["current_suppliers"][:120], "key_date": nxt,
            "link": b["last_notice"], "evidence": f"last award {b['last_award']}, avg {b['avg_bids']} bids per award",
            "contact": b["buyer_email"],
        })
    for m in markets:
        p, imp = m["premium_vs_benchmark_pct"], m["imports_usd"]
        if p == "" or p < 10 or imp < 20_000_000:
            continue
        out.append({
            "opp_id": f"A:{m['hs6'].replace('HS ', '')}|{m['country'][:30]}", "type": "Arbitrage", "group": m["group"],
            "country": m["country"], "region": region(m["country"]), "buyer": "(importers in market)",
            "what": f"{m['product'][:110]} - pays {p}% above benchmark", "hs6": m["hs6"],
            "buyer_price_usd_kg": m["unit_value_usd_kg"], "benchmark_usd_kg": m["benchmark_usd_kg"], "spread_pct": p,
            "deal_value_usd": "", "market_imports_usd": imp, "competitors_est": "", "incumbent": "",
            "key_date": "", "link": "https://comtradeplus.un.org/",
            "evidence": f"{m['year']} imports {imp:,} USD, growth {m['growth_pct']}%, benchmark {m['benchmark_source']}",
            "contact": "",
        })
    write("opportunities.csv", out)
    log.info("opportunities %d", len(out))


def write_digest(tenders, buyers):
    """Plain-text daily summary (Hebrew headings) used by the scheduled e-mail."""
    t = today()
    new = [r for r in tenders if r["new"] and r["score"] >= 50][:15]
    isr = [r for r in tenders if r["country"] == "ISR"][:10]
    soon = [b for b in buyers if b["next_expected"] and str(t) <= b["next_expected"] <= str(t + dt.timedelta(days=45))]
    soon = sorted(soon, key=lambda b: -b["total_usd"])[:10]
    L = [f"Leads Engine - {t:%d/%m/%Y}", "",
         f"מכרזים פתוחים: {len(tenders)} | חדשים: {sum(1 for r in tenders if r['new'])} | "
         f"נסגרים תוך 14 יום: {sum(1 for r in tenders if r['days_left'] != '' and 0 <= r['days_left'] <= 14)}", ""]
    def line(r):
        v = f"{r['est_value_usd']:,} USD" if r["est_value_usd"] != "" else "ללא היקף"
        return (f"- [{r['score']}] {r['group']} | {r['country']} | {r['buyer'][:60]} | {r['title'][:120]} | "
                f"{v} | הגשה עד {r['deadline'] or 'לא צוין'} | {r['link']}")
    L.append("מכרזים חדשים עם ציון 50 ומעלה:")
    L += [line(r) for r in new] or ["- אין חדשים"]
    L += ["", "ישראל (מכרזים והודעות פטור פתוחות):"]
    L += [line(r) for r in isr] or ["- אין"]
    L += ["", "קונים חוזרים שצפויים לצאת למכרז ב-45 הימים הקרובים (לפי היסטוריית TED):"]
    L += [f"- {b['buyer'][:70]} | {b['country']} | {b['group']} | {b['awards_12m']} זכיות ב-12 חודשים, "
          f"{b['total_usd']:,} USD | צפוי בסביבות {b['next_expected']} | ספקים נוכחיים: {b['current_suppliers'][:80]}"
          for b in soon] or ["- אין"]
    L += ["", "הטבלה המלאה: https://docs.google.com/spreadsheets/d/1YSeZ_7GHeSb5RxLk1SmwfWTaFtZOuWbktHLoRlDM83Y/edit"]
    (LEADS / "digest.txt").write_text("\n".join(L), encoding="utf-8")


def write(name, rows, cols=None):
    LEADS.mkdir(parents=True, exist_ok=True)
    cols = cols or (list(rows[0].keys()) if rows else ["empty"])
    with open(LEADS / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(cols)
        for r in rows:
            w.writerow([r.get(c, "") for c in cols])


def merge():
    bm = benchmarks()
    seen_p = LEADS / "seen.json"
    seen = json.loads(seen_p.read_text()) if seen_p.exists() else {}
    tenders, status = merge_tenders(bm, seen)
    cutoff = str(today() - dt.timedelta(days=120))
    seen = {k: v for k, v in seen.items() if v >= cutoff}
    seen_p.write_text(json.dumps(seen, sort_keys=True, indent=0))
    enp = LEADS / "enrich.json"
    imp, sup, n = merge_importyeti(bm, json.loads(enp.read_text()) if enp.exists() else {})
    buyers = merge_awards()
    markets = merge_markets(bm)
    merge_opportunities(tenders, buyers or [], markets or [])
    write_digest(tenders, buyers or [])
    write("tenders.csv", tenders)
    write("importers.csv", imp)
    write("suppliers.csv", sup)
    iyp = PARTIAL / "importyeti.json"
    iym = json.loads(iyp.read_text()) if iyp.exists() else {}
    status.append(["importyeti", iym.get("ran", ""), n,
                   f"{n} HS headings cached; this run {iym.get('meta', {}).get('scanned', 0)}, "
                   f"due {iym.get('meta', {}).get('due', '')}"])
    gb = _group_bench(bm)
    write("groups.csv", [{"group": g["name"], "hs_chapters": " ".join(g["hs"]), "ted_cpv": " ".join(g["cpv"]),
                          "worldbank_keywords": ", ".join(g["wb"]), "mr_gov_categories": " ".join(g["mr"]),
                          "benchmark": gb.get(g["id"], ""), "supplier_regex": g["sup"]} for g in BY_ID.values()])
    write("status.csv", [dict(zip(["source", "last_run_utc", "rows", "note"], s)) for s in status])
    log.info("tenders %d, importers %d, suppliers %d", len(tenders), len(imp), len(sup))


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--source"); ap.add_argument("--merge", action="store_true")
    a = ap.parse_args()
    try:
        if a.source:
            run_source(a.source)
        if a.merge:
            merge()
    except Exception:  # noqa: BLE001
        LEADS.mkdir(parents=True, exist_ok=True)
        (LEADS / f"error_{a.source or 'merge'}.txt").write_text(traceback.format_exc())
        raise


if __name__ == "__main__":
    sys.exit(main())
