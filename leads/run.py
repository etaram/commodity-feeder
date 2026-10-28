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

TENDER_SOURCES = ["ted", "fts", "sam", "canadabuys", "za", "worldbank", "ebrd", "mrgov", "ungm", "undp", "aiib",
                  "isdb", "etimad", "prozorro", "pncp", "secop", "germany", "contractsfinder", "paraguay", "dominican", "austender", "oman", "france", "spain",
                  "kenya", "tanzania", "ghana", "zambia", "qatar"]
NEW_MODULES = {"ungm", "undp", "aiib", "isdb", "etimad", "prozorro", "pncp", "secop", "germany", "contractsfinder", "qatar",
               "paraguay", "dominican", "oman", "austender", "georgia", "moldova", "nigeria", "kenya", "ecuador", "france", "spain", "tanzania",
               "ghana", "zambia"}
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
    elif name in NEW_MODULES:
        import importlib
        m = importlib.import_module(f".{name}", __package__)
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
    (LEADS / f"error_{name}.txt").unlink(missing_ok=True)
    log.info("%s: %d rows", name, len(rows))


def _rates():
    """USD per unit for every currency (open.er-api covers ~160 incl. UAH, COP, SAR); ECB rates as fallback."""
    from .common import session
    try:
        j = session().get("https://open.er-api.com/v6/latest/USD", timeout=30).json()
        r = {k: 1.0 / v for k, v in j["rates"].items() if v}
        if len(r) > 100:
            return r
    except Exception:  # noqa: BLE001
        pass
    try:
        from feeder.fx import usd_per_unit
        return usd_per_unit()[0]
    except Exception:  # noqa: BLE001
        return {"USD": 1.0, "EUR": 1.08, "ILS": 0.27, "GBP": 1.27}


def _group_bench(bm):
    out = {}
    for gid, g in BY_ID.items():
        out[gid] = " | ".join(fmt_bench(bm[r]) for r in g["ref"] if r in bm)
    return out


def score(r, usd, days, new):
    """Objective 0-100, the same for every user: order size, time left to prepare a bid, openness to foreign
    bidders, completeness of the notice. Personal preferences are applied in the sheet (Profile tab)."""
    v = 10 if usd == "" else 6 if usd < 100_000 else 12 if usd < 500_000 else 16 if usd < 1_000_000 else \
        22 if usd < 5_000_000 else 26 if usd < 20_000_000 else 30
    if r.get("stage") == "planned":
        d = 18
    else:
        d = 10 if days == "" else 0 if days < 3 else 6 if days <= 7 else 14 if days <= 14 else 20 if days <= 45 else 16
    acc = (r.get("access") or "").lower()
    a = 15 if acc.startswith("international") else 12 if ("gpa" in acc or "open to foreign" in acc or "trade agreements" in acc
                                                          or "may bid" in acc) else 6
    info = (5 if r.get("contact") else 0) + (3 if usd != "" else 0) + (2 if not r.get("lang") else 0)
    pen = 15 if "exemption" in r["source"] else 0  # intent to contract with a named supplier: objection window only
    raw = v + d + a + info + (5 if new else 0) - pen
    return max(0, min(100, round(raw * 100 / 80)))


def merge_tenders(bm, seen):
    from .regions import region
    from .sectors import SECTORS, classify
    rates, gb, t = _rates(), _group_bench(bm), today()
    rows, status = [], []
    for s in TENDER_SOURCES:
        p = PARTIAL / f"{s}.json"
        err = LEADS / f"error_{s}.txt"
        if not p.exists():
            status.append([s, "", 0, "no data", ""]); continue
        j = json.loads(p.read_text())
        meta = {k: v for k, v in (j.get("meta") or {}).items() if isinstance(v, (int, str, float))}
        status.append([s, j.get("ran", ""), len(j["rows"]), "OK" if j["rows"] else "EMPTY",
                       "; ".join(f"{k}={v}" for k, v in meta.items())[:200] +
                       (" | last error: " + err.read_text()[-160:].replace("\n", " ") if err.exists() else "")])
        rows += j["rows"]
    out, dedup = [], {}
    for r in rows:
        if r.get("skip"):
            continue
        g = BY_ID.get(r.get("group") or "", {})
        codes = (r.get("cpv") or (r.get("classification") if re.match(r"^\d{8}", r.get("classification") or "") else "")).split()
        sec = r.get("sector") or classify(r.get("title", ""), codes or None)[0]
        first = seen.setdefault(r["id"], str(t))
        usd = ""
        if r.get("value") not in ("", None) and r.get("currency") in rates:
            try:
                usd = round(float(r["value"]) * rates[r["currency"]])
            except (TypeError, ValueError):
                usd = ""
            if usd != "" and usd > 5_000_000_000:
                usd = ""
        dl = r.get("deadline") or ""
        try:
            days = (dt.date.fromisoformat(dl) - t).days if dl else ""
        except ValueError:
            dl, days = "", ""
        new = (t - dt.date.fromisoformat(first)).days <= 2
        country = (r.get("country") or "").split(",")[0]
        rec = {
            "score": score(r, usd, days, new), "new": "NEW" if new else "", "deadline": dl, "days_left": days,
            "stage": r.get("stage") or "tender", "sector": SECTORS.get(sec, "Other"), "commodity": g.get("name", ""),
            "source": r["source"], "country": r.get("country", ""), "region": region(country),
            "buyer": r.get("buyer", ""), "title": r.get("title", ""), "est_value_usd": usd,
            "est_value": r.get("value", ""), "currency": r.get("currency", ""), "published": r.get("published", ""),
            "notice_type": r.get("notice_type", ""), "access": r.get("access", ""), "nature": r.get("nature", ""),
            "classification": r.get("classification", ""), "contact": r.get("contact", ""),
            "benchmark": gb.get(r.get("group") or "", ""), "link": r.get("link", ""), "lang": r.get("lang", ""),
            "first_seen": first, "id": r["id"],
            "group": g.get("name", ""),  # kept for older sheet formulas / opportunities
        }
        key = (re.sub(r"\W+", "", rec["title"].lower())[:80], rec["deadline"], rec["country"])
        if key in dedup and dedup[key]["source"] != rec["source"]:
            continue  # same notice republished by a second source
        dedup[key] = rec
        out.append(rec)
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


AWARD_ROWS = []


def merge_awards():
    """All award notices (TED all sectors + national OCDS sources + AIIB): recent awards, repeat buyers and the
    competitor table, keyed by sector."""
    from .sectors import SECTORS, from_cpv
    rates, t = _rates(), today()
    rows, seen = [], set()
    files = sorted((LEADS / "awards").glob("*.json")) + sorted((LEADS / "awards").glob("*/*.json"))
    for f in files:
        for r in json.loads(f.read_text()):
            if r.get("empty") or not r.get("winners"):
                continue
            rid = r.get("id") or f"TED-{r.get('pn')}"
            if rid in seen:
                continue
            seen.add(rid); r["id"] = rid
            r.setdefault("source", "TED")
            r["link"] = r.get("link") or (f"https://ted.europa.eu/en/notice/-/detail/{r['pn']}" if r.get("pn") else "")
            sec = r.get("sector") or from_cpv((r.get("cpv") or "").split()[:1]) or ""
            r["sector_name"] = SECTORS.get(sec, "Other")
            gid = r.get("group") or match_cpv((r.get("cpv") or "").split()[:1])[0] or ""
            r["group"] = gid
            r["pn"] = r.get("pn") or ""
            r["email"] = r.get("email", ""); r["bids"] = r.get("bids", "")
            r["winner_country"] = r.get("winner_country", ""); r["winner_size"] = r.get("winner_size", "")
            rows.append(r)
    for r in rows:
        v, c = r.get("value"), r.get("currency")
        r["usd"] = round(v * rates[c]) if isinstance(v, (int, float)) and c in rates else ""
        if r["usd"] != "" and r["usd"] > 2_000_000_000:  # framework ceilings and data-entry errors
            r["usd"] = ""
        r["gname"] = r["sector_name"]
    cut = str(t - dt.timedelta(days=180))
    recent = sorted((r for r in rows if r["published"] >= cut), key=lambda r: -(r["usd"] or 0))[:3000]
    write("awards.csv", [{
        "published": r["published"], "group": r["gname"], "country": r["country"], "buyer": r["buyer"],
        "title": r["title"][:200], "winners": "; ".join(r["winners"])[:200], "winner_country": r["winner_country"],
        "winner_size": r["winner_size"], "value_usd": r["usd"], "value": r["value"], "currency": r["currency"],
        "bids": r["bids"], "buyer_email": r["email"], "link": r["link"], "source": r["source"],
        "commodity": BY_ID.get(r["group"], {}).get("name", ""),
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
            "last_award": lst[-1]["published"], "next_expected": str(nxt),
            "current_suppliers": "; ".join(w for w, _ in sorted(wins.items(), key=lambda x: -x[1])[:3])[:200],
            "avg_bids": round(sum(r["bids"] for r in lst if isinstance(r["bids"], int)) / max(1, sum(1 for r in lst if isinstance(r["bids"], int))), 1),
            "buyer_email": next((r["email"] for r in reversed(lst) if r["email"]), ""),
            "last_notice": lst[-1]["link"],
            "median_award_usd": round(median([r["usd"] for r in lst if r["usd"]])) if any(r["usd"] for r in lst) else "",
        })
    buyers.sort(key=lambda b: (-b["total_usd"], -b["awards_12m"]))
    write("buyers.csv", buyers[:5000])
    global AWARD_ROWS
    AWARD_ROWS = rows
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
    write("competitors.csv", out[:5000])
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
            "opp_id": f"T:{r['id']}", "type": "Tender", "group": r["commodity"] or r["sector"], "country": r["country"],
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
        if p == "" or p < 4 or imp < 20_000_000:
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
    """Plain-text daily summary (Hebrew headings) used by the scheduled e-mail: the brain's best opportunities first."""
    t = today()
    def line(r):
        v = f"{r['est_value_usd']:,} USD" if r["est_value_usd"] != "" else "ללא היקף"
        ev = f" | EV {r['ev_usd']:,}" if r.get("ev_usd") not in ("", None) else ""
        title = r.get("title_en") or r["title"]
        return (f"- [{r.get('decision', '')}{ev}] {r['sector']} | {r['country']} | {r['buyer'][:60]} | {title[:120]} | "
                f"{v} | הגשה עד {r['deadline'] or 'לא צוין'} | {r['link']}")
    pursue = [r for r in tenders if r.get("decision") == "Pursue"][:15]
    intl = [r for r in tenders if (r.get("access") or "").startswith("International") and r["new"]][:10]
    isr = [r for r in tenders if r["country"] == "ISR"][:10]
    soon = [b for b in buyers if b["next_expected"] and str(t) <= b["next_expected"] <= str(t + dt.timedelta(days=45))]
    soon = sorted(soon, key=lambda b: -b["total_usd"])[:10]
    L = [f"Opportunity Engine - {t:%d/%m/%Y}", "",
         f"מכרזים פתוחים: {len(tenders):,} | חדשים: {sum(1 for r in tenders if r['new']):,} | "
         f"לרדוף (Pursue): {sum(1 for r in tenders if r.get('decision') == 'Pursue')} | "
         f"מדינות: {len({r['country'] for r in tenders})}", ""]
    L.append("ההזדמנויות המובילות לפי המוח (ערך צפוי):")
    L += [line(r) for r in pursue] or ["- אין"]
    L += ["", "חדשים מארגונים בינלאומיים ובנקי פיתוח:"]
    L += [line(r) for r in intl] or ["- אין"]
    L += ["", "ישראל:"]
    L += [line(r) for r in isr] or ["- אין"]
    L += ["", "קונים חוזרים שצפויים לצאת למכרז ב-45 הימים הקרובים:"]
    L += [f"- {b['buyer'][:70]} | {b['country']} | {b['group']} | {b['awards_12m']} זכיות ב-12 חודשים, "
          f"{b['total_usd']:,} USD | צפוי בסביבות {b['next_expected']} | ספקים נוכחיים: {b['current_suppliers'][:80]}"
          for b in soon] or ["- אין"]
    L += ["", "הטבלה המלאה: https://docs.google.com/spreadsheets/d/1YSeZ_7GHeSb5RxLk1SmwfWTaFtZOuWbktHLoRlDM83Y/edit"]
    (LEADS / "digest.txt").write_text("\n".join(L), encoding="utf-8")


def write_sheet_chunks(tenders):
    """The Google Sheet imports tenders in fixed-size chunks (IMPORTDATA has a per-file size limit); every chunk file
    always exists so the sheet formula never breaks. Highest score first."""
    rows = []
    for r in tenders:
        x = {c: r.get(c, "") for c in SHEET_COLS}
        x["title_en"] = (r.get("title_en") or r.get("title") or "")[:220]
        x["title_original"] = r.get("title", "")[:140] if r.get("lang") else ""
        x["buyer"] = (r.get("buyer") or "")[:90]
        x["contact"] = (r.get("contact") or "")[:80]
        x["why"] = (r.get("why") or "")[:160]; x["incumbent"] = (r.get("incumbent") or "")[:80]
        rows.append(x)
    for i in range(CHUNKS):
        write(f"sheet/tenders_{i + 1:02d}.csv", rows[i * CHUNK:(i + 1) * CHUNK], SHEET_COLS)
    write("tenders.csv", rows[:CHUNK], SHEET_COLS)


def write_accounts(tenders, buyers):
    """Dynamic buyer universe: every buyer seen in open notices (all sources) joined with award history.
    Ranked by activity: open notices, known open value and awarded value in the last 12 months."""
    import math
    from .regions import region
    acc = {}
    for r in tenders:
        b = (r.get("buyer") or "").strip()
        if len(b) < 3:
            continue
        k = (_norm_buyer(b)[:80], r["country"])
        a = acc.setdefault(k, {"buyer": b, "country": r["country"], "open": 0, "open_usd": 0, "sectors": defaultdict(int),
                               "sources": set(), "latest": "", "contact": "", "new": 0})
        a["open"] += 1; a["open_usd"] += r["est_value_usd"] or 0; a["sectors"][r["sector"]] += 1
        a["sources"].add(r["source"].split(" (")[0]); a["latest"] = max(a["latest"], r.get("published") or "")
        a["contact"] = a["contact"] or r.get("contact", ""); a["new"] += 1 if r["new"] else 0
    aw = {}
    for b in buyers:
        k = (_norm_buyer(b["buyer"])[:80], b["country"])
        x = aw.setdefault(k, {"awards": 0, "usd": 0, "next": ""})
        x["awards"] += b["awards_12m"]; x["usd"] += b["total_usd"] or 0
        x["next"] = min(filter(None, [x["next"], b["next_expected"]]), default="")
    out = []
    for k in set(acc) | set(aw):
        a = acc.get(k); x = aw.get(k, {"awards": 0, "usd": 0, "next": ""})
        if not a:
            continue
        sc = (math.log10(1 + a["open"]) * 20 + math.log10(1 + max(0, a["open_usd"])) * 6 + math.log10(1 + x["awards"]) * 10
              + math.log10(1 + max(0, x["usd"])) * 4)
        out.append({"account": a["buyer"][:100], "country": a["country"], "region": region(a["country"]),
                    "activity_score": round(sc, 1), "open_notices": a["open"], "new_48h": a["new"],
                    "open_value_usd": round(a["open_usd"]),
                    "main_sectors": "; ".join(s for s, _ in sorted(a["sectors"].items(), key=lambda y: -y[1])[:3]),
                    "awards_12m": x["awards"], "awarded_usd_12m": round(x["usd"]), "next_expected_tender": x["next"],
                    "sources": "; ".join(sorted(a["sources"])), "latest_notice": a["latest"], "contact": a["contact"][:80]})
    out.sort(key=lambda y: -y["activity_score"])
    write("accounts.csv", out[:4000])
    log.info("accounts %d", len(out))


def write_sector_summary(tenders):
    """Sector x region: open notices, notices with a value, total and median value (USD), new in 48h."""
    agg = defaultdict(lambda: {"open": 0, "valued": 0, "vals": [], "new": 0, "countries": set(), "sources": set()})
    for r in tenders:
        for key in ((r["sector"], r["region"]), (r["sector"], "All regions"), ("All sectors", r["region"]),
                    ("All sectors", "All regions")):
            a = agg[key]; a["open"] += 1; a["new"] += 1 if r["new"] else 0
            a["countries"].add(r["country"]); a["sources"].add(r["source"].split(" (")[0])
            if r["est_value_usd"] != "":
                a["valued"] += 1; a["vals"].append(r["est_value_usd"])
    out = [{"sector": k[0], "region": k[1], "open_notices": a["open"], "new_48h": a["new"], "with_value": a["valued"],
            "total_value_usd": round(sum(a["vals"])), "median_value_usd": round(median(a["vals"])) if a["vals"] else "",
            "countries": len(a["countries"]), "sources": len(a["sources"])} for k, a in agg.items()]
    out.sort(key=lambda x: (x["sector"] != "All sectors", x["region"] != "All regions", -x["open_notices"]))
    write("sectors.csv", out)
    cs = defaultdict(lambda: {"open": 0, "vals": 0, "sources": set()})
    for r in tenders:
        c = cs[r["country"]]; c["open"] += 1; c["vals"] += r["est_value_usd"] or 0; c["sources"].add(r["source"])
    from .regions import region
    write("countries.csv", sorted(({"country": k, "region": region(k), "open_notices": v["open"],
                                    "total_value_usd": round(v["vals"]), "sources": "; ".join(sorted(v["sources"]))[:150]}
                                   for k, v in cs.items()), key=lambda x: -x["open_notices"]))


def write(name, rows, cols=None):
    (LEADS / name).parent.mkdir(parents=True, exist_ok=True)
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
    try:
        from .sectors import SECTORS, classify
        from .translate import summary, translate_rows
        translate_rows(tenders)
        for r in tenders:
            if r["sector"] == "Other" and r.get("title_en"):
                sec, _ = classify(r["title_en"])
                if sec:
                    r["sector"] = SECTORS[sec]
            r["summary_en"] = summary(r, r["sector"])
    except Exception as e:  # noqa: BLE001
        log.warning("translation skipped: %s", e)
    enp = LEADS / "enrich.json"
    imp, sup, n = merge_importyeti(bm, json.loads(enp.read_text()) if enp.exists() else {})
    buyers = merge_awards()
    try:
        from . import brain
        st = brain.enrich(tenders, AWARD_ROWS)
        comp = []
        for (c, sec), (fw, n) in st.foreign.items():
            if sec == "*" or n < 5:
                continue
            b = st.bids_cs.get((c, sec)) or []
            comp.append({"country": c, "sector": sec, "awards_12m": n, "foreign_wins": fw,
                         "foreign_win_rate": round(fw / n, 3), "median_bids": median(b) if b else ""})
        write("competition.csv", sorted(comp, key=lambda x: -x["awards_12m"]))
        tenders.sort(key=lambda x: ({"Pursue": 0, "Watch": 1, "Ignore": 2}[x["decision"]], -(x["ev_usd"] or 0), -x["score"]))
    except Exception as e:  # noqa: BLE001
        log.warning("brain: %s", e)
    markets = merge_markets(bm)
    merge_opportunities(tenders, buyers or [], markets or [])
    cols = ["score", "new", "deadline", "days_left", "stage", "sector", "commodity", "source", "country", "region",
            "buyer", "title_en", "summary_en", "title", "est_value_usd", "est_value", "currency", "published", "notice_type", "access", "nature",
            "classification", "contact", "benchmark", "link", "lang", "first_seen", "id", "decision", "ev_usd",
            "p_win_market", "est_bidders", "foreign_win_rate", "buyer_awards_12m", "buyer_median_award_usd", "incumbent",
            "margin_pct", "why"]
    write_digest(tenders, buyers or [])
    write("tenders_all.csv", tenders, cols)
    write_sheet_chunks(tenders)
    write_sector_summary(tenders)
    try:
        write_accounts(tenders, buyers or [])
    except Exception as e:  # noqa: BLE001
        log.warning("accounts: %s", e)
    write("importers.csv", imp)
    write("suppliers.csv", sup)
    iyp = PARTIAL / "importyeti.json"
    iym = json.loads(iyp.read_text()) if iyp.exists() else {}
    status.append(["importyeti", iym.get("ran", ""), n, "OK",
                   f"{n} HS headings cached; this run {iym.get('meta', {}).get('scanned', 0)}, "
                   f"due {iym.get('meta', {}).get('due', '')}"])
    gb = _group_bench(bm)
    write("groups.csv", [{"group": g["name"], "hs_chapters": " ".join(g["hs"]), "ted_cpv": " ".join(g["cpv"]),
                          "worldbank_keywords": ", ".join(g["wb"]), "mr_gov_categories": " ".join(g["mr"]),
                          "benchmark": gb.get(g["id"], ""), "supplier_regex": g["sup"]} for g in BY_ID.values()])
    write("status.csv", [dict(zip(["source", "last_run_utc", "rows", "note", "detail"], s)) for s in status])
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
