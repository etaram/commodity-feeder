"""The brain: turns open notices into ranked, explained pursuit decisions.

Everything here uses public data only (award history, notice fields). Private inputs (your supplier coverage,
relationships, profile weights) are applied in the Google Sheet on top of these columns.

Per tender it adds:
  est_bidders         expected number of competing bids (buyer history > country+sector > sector > default)
  foreign_win_rate    share of awards in the buyer's country and sector won by suppliers from another country
  buyer_awards_12m    awards by this buyer in the last 12 months; buyer_median_award_usd; incumbent
  p_win_market        win probability for a capable outside supplier before supplier coverage (sheet adds that)
  margin_pct          gross margin: sector default x competition factor +/- commodity price trend (World Bank)
  ev_usd              expected value = p_win x deal value x net margin x sqrt(value confidence) - pursuit cost
  deal_value_usd ...  the full deal calculation (see deal()): value basis, addressable share, framework split,
                      net margin after financing and bonds, gross profit, pursuit cost, ROI
  decision            Pursue (EV over threshold, p_win >= 5%, ROI >= 2) / Watch / Ignore, and why (one line)
"""
import re
from collections import defaultdict
from statistics import median

DEFAULT_BIDS = 4.0
PURSUIT_COST = {"tender": 3000, "planned": 1000}
# Default gross margin for a supplier / prime that sources internationally, by sector.
MARGIN = {
    "Agriculture & food": 0.04, "Energy, fuels & utilities": 0.03, "Power & electrical equipment": 0.10,
    "Mining, minerals & metals": 0.04, "Chemicals & plastics": 0.06, "Textiles, apparel & leather": 0.10,
    "Construction materials & building systems": 0.08, "Building construction works": 0.07,
    "Transport & civil infrastructure works": 0.07, "Water & wastewater": 0.09,
    "Industrial & construction machinery": 0.10, "Vehicles, rolling stock, ships & aircraft": 0.08,
    "Defence & security": 0.12, "Healthcare & pharmaceuticals": 0.10, "Scientific & measuring instruments": 0.12,
    "ICT & telecom": 0.10, "Furniture, appliances & consumer goods": 0.10, "Repair, maintenance & installation": 0.12,
    "Transport & logistics services": 0.08, "Engineering & architecture services": 0.15,
    "Consulting, business & financial services": 0.15, "Environment, waste & cleaning": 0.10,
    "Education, social & hospitality services": 0.10, "Other": 0.08,
}


# How tradable a sector is for a supplier based outside the buyer's country (goods travel, local services do not).
TRADABLE = {
    "Education, social & hospitality services": 0.15, "Environment, waste & cleaning": 0.3,
    "Repair, maintenance & installation": 0.35, "Transport & logistics services": 0.4,
    "Consulting, business & financial services": 0.45, "Building construction works": 0.45,
    "Transport & civil infrastructure works": 0.6, "Engineering & architecture services": 0.7,
}
FRAMEWORK = re.compile(r"framework|rahmenvereinbarung|accord[- ]cadre|acuerdo marco|dynamic purchasing|"
                       r"\bdps\b|multi[- ]party|panel|standing offer|idiq|registro de pre", re.I)


def _norm(b):
    return re.sub(r"\s+", " ", re.sub(r"[^\w ]", " ", (b or "").lower())).strip()[:80]


def _c(code):
    return (code or "").split(",")[0].strip().upper()[:3]


class Stats:
    def __init__(self, awards):
        self.bids_cs, self.bids_s = defaultdict(list), defaultdict(list)
        self.foreign = defaultdict(lambda: [0, 0])
        self.buyer = defaultdict(lambda: {"n": 0, "usd": [], "bids": [], "wins": defaultdict(int), "foreign": 0})
        self.usd_cs, self.usd_s = defaultdict(list), defaultdict(list)
        for a in awards:
            c, s = _c(a.get("country")), a.get("sector_name") or "Other"
            b = a.get("bids")
            if isinstance(b, int) and 0 < b < 200:
                self.bids_cs[(c, s)].append(b); self.bids_s[s].append(b)
            wc = _c(a.get("winner_country"))
            is_foreign = None
            if wc and c:
                is_foreign = wc != c
                f = self.foreign[(c, s)]; f[0] += 1 if is_foreign else 0; f[1] += 1
                g = self.foreign[(c, "*")]; g[0] += 1 if is_foreign else 0; g[1] += 1
            k = (_norm(a.get("buyer")), c)
            x = self.buyer[k]; x["n"] += 1
            if a.get("usd"):
                x["usd"].append(a["usd"])
                self.usd_cs[(c, s)].append(a["usd"]); self.usd_s[s].append(a["usd"])
            if isinstance(b, int) and 0 < b < 200:
                x["bids"].append(b)
            for w in a.get("winners") or []:
                x["wins"][w] += 1
            x["foreign"] += 1 if is_foreign else 0

    def est_bidders(self, buyer, country, sector):
        x = self.buyer.get((_norm(buyer), _c(country)))
        if x and len(x["bids"]) >= 2:
            return median(x["bids"]), "buyer history"
        cs = self.bids_cs.get((_c(country), sector))
        if cs and len(cs) >= 5:
            return median(cs), "country+sector history"
        s = self.bids_s.get(sector)
        if s and len(s) >= 10:
            return median(s), "sector history"
        return DEFAULT_BIDS, "default"

    def est_value(self, buyer, country, sector):
        """Typical award size when the notice states no value: buyer history, then country+sector, then sector."""
        x = self.buyer.get((_norm(buyer), _c(country)))
        if x and len(x["usd"]) >= 2:
            return median(x["usd"]), "buyer's past awards"
        cs = self.usd_cs.get((_c(country), sector))
        if cs and len(cs) >= 8:
            return median(cs), "country+sector awards"
        s = self.usd_s.get(sector)
        if s and len(s) >= 30:
            return median(s), "sector awards"
        return None, ""

    def foreign_rate(self, country, sector):
        f = self.foreign.get((_c(country), sector)) or [0, 0]
        if f[1] >= 10:
            return (f[0] + 1) / (f[1] + 4), f[1]
        g = self.foreign.get((_c(country), "*")) or [0, 0]
        if g[1] >= 20:
            return (g[0] + 1) / (g[1] + 4), g[1]
        return None, 0


def _access_prior(access):
    a = (access or "").lower()
    if a.startswith("international"):
        return 0.45
    if "gpa" in a or "open to foreign" in a or "trade agreements" in a:
        return 0.12
    if "may bid" in a:
        return 0.10
    return 0.05


# ------------------------------------------------------------------ deal model (v2)
# Share of the contract value that a sourcing company like Sinder actually supplies: all of a goods contract, the
# materials and equipment part of works, a small part of services.
ADDRESSABLE = {
    "Building construction works": 0.35, "Transport & civil infrastructure works": 0.35, "Water & wastewater": 0.5,
    "Repair, maintenance & installation": 0.3, "Environment, waste & cleaning": 0.3,
    "Transport & logistics services": 0.2, "Engineering & architecture services": 0.1,
    "Consulting, business & financial services": 0.05, "Education, social & hospitality services": 0.15,
}
PAYMENT_DAYS = {"Israel": 45, "Europe": 60, "North America": 45, "Oceania": 45}  # others: 90
COST_OF_CAPITAL = 0.10   # a year, on the goods Sinder pays for before the buyer pays
BOND_COST = 0.003        # bid + performance guarantee fees, share of revenue
GROUP_ID = {}
PLACES = re.compile(r"(?:up to|maximum of|max\.?|a maximum of|até|hasta|bis zu|jusqu'à)\s*(\d{1,2})\s*"
                    r"(?:operators|suppliers|economic operators|participants|places|contractors|firms|bidders)|"
                    r"עד\s*(\d{1,2})\s*(?:זוכים|ספקים|מציעים)", re.I)


SERVICE_TXT = re.compile(r"\bservices?\b|\bcare\b|consultan|management of|maintenance|cleaning|catering|training|"
                         r"operation of|provision of|support|fostering|advisory|audit|insurance|legal|security guard|"
                         r"שירות|שירותי|ייעוץ|יועץ|תחזוקה|אחזקה|ניקיון|הסעדה|הדרכה|אבטחה|ליווי|הפעלת|ניהול", re.I)
GOODS_TXT = re.compile(r"\bsuppl(y|ies)\b|delivery of|purchase of|procurement of|equipment|materials?\b|products?\b|"
                       r"devices?|vehicles?|spare parts|consumables|machinery|pipes?|cables?|fuel|food|"
                       r"אספקת|רכישת|ציוד|חומרי|מוצרי|כלי רכב|חלקי חילוף|מתכלים", re.I)


def _group_id(name):
    if not GROUP_ID:
        from .taxonomy import BY_ID
        GROUP_ID.update({g["name"]: gid for gid, g in BY_ID.items()})
    return GROUP_ID.get(name or "", "")


def deal(r, st, trends, prefs=None, edge=None):
    """Deal economics for one notice. Returns a dict of numbers plus a one-line explanation.

    value  V      stated value, else the buyer's median award, else country+sector median, else sector median
    share  s      framework ceiling split across its places (parsed, else 30%); x addressable share of the scope
    margin m      sector default x competition factor (few bidders = more room) +/- commodity price trend effect
    net    n      m - financing of the goods until the buyer pays - bond fees
    p_win  p      fair share among expected bidders x openness to foreign winners x tradability x incumbent x time
    EV            p x V x s x n - pursuit cost;  ROI = EV / pursuit cost
    """
    sec, country = r["sector"], r["country"]
    region = r.get("region") or ""
    home = _c(country) == "ISR"
    bidders, bsrc = st.est_bidders(r.get("buyer"), country, sec)
    fr, n_aw = st.foreign_rate(country, sec)
    fsrc = f"{n_aw} awards"
    if fr is None:
        fr, fsrc = _access_prior(r.get("access")), "access rules"
    x = st.buyer.get((_norm(r.get("buyer")), _c(country)))
    inc = "; ".join(w for w, _ in sorted(x["wins"].items(), key=lambda y: -y[1])[:2])[:120] if x and x["wins"] else ""
    text = f"{r.get('title', '')} {r.get('title_en', '')} {r.get('notice_type', '')}"
    fw = bool(FRAMEWORK.search(text))
    pm = PLACES.search(text)
    places = int(pm.group(1) or pm.group(2)) if pm else 0

    # --- value
    usd, basis, conf = r.get("est_value_usd"), "stated", 1.0
    if usd in ("", None):
        usd, src = st.est_value(r.get("buyer"), country, sec)
        basis = src or "unknown"
        conf = {"buyer's past awards": 0.7, "country+sector awards": 0.5, "sector awards": 0.35}.get(src, 0)
    nature = (r.get("nature") or "").lower()
    if not nature:
        svc, goods = SERVICE_TXT.search(text), GOODS_TXT.search(text)
        nature = "services" if svc and not goods else "supplies" if goods and not svc else ""
    addr = 1.0 if nature.startswith("supp") or nature.startswith("goods") else ADDRESSABLE.get(sec, 1.0)
    if nature.startswith("serv") and sec not in ADDRESSABLE:
        addr = 0.1
    if nature.startswith("work"):
        addr = min(addr, 0.35)
    split = (1.0 / places if places else 0.3) if fw else 1.0
    deal_v = min(usd, 100_000_000) * split * addr if usd not in ("", None) else None

    # --- win probability
    if home:
        openness, trad, fsrc = 1.3, 1.0, "home market"
    else:
        openness = min(1.3, max(0.15, fr / 0.3))
        trad = TRADABLE.get(sec) or (0.4 if nature.startswith("serv") else 1.0)
        if fsrc != "access rules":
            trad = trad ** 0.5
    p = (1.0 / (bidders + 1.0)) * openness * trad
    if fw and places:
        p = max(p, min(0.85, places / max(bidders, 1.0)) * min(openness, 1.0) * trad)
    if inc and x and x["n"] >= 2:
        p *= 0.8
    if "set-aside" in (r.get("access") or ""):
        p *= 0.02  # reserved for US small businesses
    if "exemption" in (r.get("source") or "").lower() or re.search(r"התקשרות בפטור|כוונה להתקשר|exemption", text, re.I):
        p *= 0.1  # intent to contract with a named supplier: only an objection window
    days = r.get("days_left")
    if isinstance(days, int) and r.get("stage") != "planned":
        p *= 0.5 if days < 7 else 0.85 if days < 14 else 1.0
    p = min(0.45 if not (fw and places) else 0.85, p)

    # --- margin
    m = MARGIN.get(sec, 0.08) * min(1.2, max(0.6, 1.3 - 0.075 * bidders))
    gid = _group_id(r.get("commodity") or r.get("group"))
    tr = trends.get(gid) if gid else None
    tnote = ""
    if tr and tr.get("chg_3m_pct") is not None:
        c3 = tr["chg_3m_pct"]
        long_contract = fw or bool(re.search(r"\b\d+\s*(months|years|meses|años|mois|ans|monate|jahre)\b|חודשים|שנים", text, re.I))
        if c3 >= 8:
            m -= 0.015 if long_contract else 0.007
            tnote = f"{gid} prices +{c3}% in 3m: fixed-price risk"
        elif c3 >= 3:
            m -= 0.007 if long_contract else 0.0
            tnote = f"{gid} prices +{c3}% in 3m"
        elif c3 <= -8:
            m += 0.01
            tnote = f"{gid} prices {c3}% in 3m: cost tailwind"
        elif c3 <= -3:
            m += 0.005
            tnote = f"{gid} prices {c3}% in 3m"
    m = max(0.015, m)
    # --- trade-agreement edge: preferential origin removes the import duty competitors pay
    fta_up, fta_note, fta_duty, fta_origins = 0.0, "", None, []
    if edge is not None:
        goods = not (nature.startswith("serv") or nature.startswith("work")) and addr >= 0.5
        fta_up, fta_note, fta_duty, fta_origins = edge.of(country, r.get("commodity") or r.get("group") or "", goods)
        m += fta_up
    pay_days = PAYMENT_DAYS.get(region, 90) + 30   # buyer terms + transit and acceptance
    fin = (1 - m) * COST_OF_CAPITAL * pay_days / 365
    net = m - fin - BOND_COST

    # --- cost of pursuit
    cost = PURSUIT_COST.get(r.get("stage") or "tender", 3000) * (0.5 if home else 1.0)
    if usd not in ("", None) and usd > 10_000_000:
        cost += 2000
    gp = deal_v * net if deal_v is not None else None
    ev = round(p * gp * (conf ** 0.5) - cost) if gp is not None else ""
    route = "direct"
    # --- alternative routes when a direct bid is weak: through a local partner, or as a supplier to the winner
    prefs = prefs or {}
    ps = (prefs.get("partners") or {}).get(_c(country), 0.0)
    acc = (r.get("access") or "").lower()
    direct_ok = home or acc.startswith("international") or any(k in acc for k in ("gpa", "open to foreign", "may bid", "trade agreements"))
    if usd not in ("", None) and not home:
        alts = []
        if not direct_ok or ps:
            pp = min(0.45, (1.0 / (bidders + 1.0)) * trad * ((0.5 + 0.5 * ps) if ps else 0.35))
            npart = net - 0.03  # partner's share
            if deal_v and npart > 0:
                alts.append(("via local partner" if ps else "needs local partner", pp, deal_v * npart, cost + 1000))
        works = sec in ("Building construction works", "Transport & civil infrastructure works", "Water & wastewater") \
            or nature.startswith("work")
        if works and usd >= 1_000_000:
            v_sub = min(usd, 100_000_000) * 0.35
            n_sub = max(0.0, 0.07 - (0.93 * COST_OF_CAPITAL * pay_days / 365) - BOND_COST)
            alts.append(("sub-supply to the winner", 0.1, v_sub * n_sub, 800, v_sub))
        for alt in alts:
            name, pr, g, c = alt[:4]
            e = round(pr * g * (conf ** 0.5) - c)
            if ev == "" or e > ev:
                route, p, gp, ev, cost = name, pr, g, e, c
                if len(alt) > 4:
                    deal_v, addr = alt[4], 0.35
    roi = round(ev / cost, 1) if ev != "" and cost else ""
    w = (prefs.get("sector") or {}).get(sec, 1.0) * (prefs.get("region") or {}).get(region, 1.0)
    return {"route": route, "edge": w, "priority_ev": round(ev * w) if ev != "" and ev > 0 else ev, 
        "home": home, "bidders": bidders, "bsrc": bsrc, "fr": fr, "fsrc": fsrc, "inc": inc, "x": x, "fw": fw,
        "places": places, "trad": trad, "p": p, "m": m, "net": net, "deal_v": deal_v, "basis": basis, "conf": conf,
        "addr": addr, "split": split, "gp": gp, "ev": ev, "roi": roi, "cost": cost, "trend": tr, "tnote": tnote,
        "pay_days": pay_days, "fta_up": fta_up, "fta_note": fta_note, "fta_duty": fta_duty, "fta_origins": fta_origins,
    }


def enrich(tenders, awards, trends=None, prefs=None):
    """prefs: {"sector": {name: weight}, "region": {name: weight}, "partners": {iso3: strength}} from the sheet."""
    st = Stats(awards)
    trends = trends or {}
    try:
        from .fta import Edge
        edge = Edge()
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger("leads").warning("fta edge unavailable: %s", e)
        edge = None
    for r in tenders:
        d = deal(r, st, trends, prefs, edge)
        days, ev, p = r.get("days_left"), d["ev"], d["p"]
        why = []
        if ev != "":
            why.append(f"EV ${ev:,.0f} = {p:.0%} x GP ${d['gp']:,.0f} - cost ${d['cost']:,.0f}"
                       + (f" [{d['route']}]" if d["route"] != "direct" else ""))
            why.append(f"deal ${d['deal_v']:,.0f} ({d['basis']}{', framework 1/' + str(d['places']) if d['fw'] and d['places'] else ', framework 30%' if d['fw'] else ''}"
                       f"{', ' + format(d['addr'], '.0%') + ' of scope' if d['addr'] < 1 else ''}) x net {d['net']:.1%}")
        else:
            why.append("value unknown")
        if isinstance(days, int) and days < 7 and r.get("stage") != "planned":
            why.append(f"only {days} days left")
        why.append(f"{d['bidders']:g} bidders ({d['bsrc']})")
        why.append("Israel: home market" if d["home"] else f"foreign win rate {d['fr']:.0%} ({d['fsrc']})")
        if d["tnote"]:
            why.append(d["tnote"])
        if d["fta_up"]:
            why.append(f"FTA origin {'/'.join(d['fta_origins'][:3])} +{d['fta_up']:.1%}")
        if d["inc"]:
            why.append(f"incumbent: {d['inc'][:50]}")
        thr = 8_000 if d["home"] else 25_000
        if isinstance(days, int) and days < 5 and r.get("stage") != "planned":
            decision = "Ignore"
        elif d["net"] <= 0:
            decision = "Ignore"
        elif d["route"] == "sub-supply to the winner" and (d["priority_ev"] or 0) >= 2_000:
            decision = "Watch"  # the opportunity opens at award: approach the winner then
            why.append("track the award, then offer materials to the winner")
        elif ev != "" and (d["priority_ev"] or 0) >= thr and p >= 0.05 and (d["roi"] or 0) >= 2:
            decision = "Pursue"
        elif (ev != "" and ev >= 2_000) or (ev == "" and r["score"] >= 60 and p >= 0.08) or r.get("stage") == "planned":
            decision = "Watch"
        else:
            decision = "Ignore"
        x = d["x"]
        tr = d["trend"] or {}
        r.update({
            "est_bidders": round(d["bidders"], 1), "foreign_win_rate": round(d["fr"], 3),
            "buyer_awards_12m": x["n"] if x else 0,
            "buyer_median_award_usd": round(median(x["usd"])) if x and x["usd"] else "",
            "incumbent": d["inc"], "p_win_market": round(p, 3), "margin_pct": round(d["m"], 4), "ev_usd": ev,
            "decision": decision, "why": "; ".join(why)[:300],
            "deal_value_usd": round(d["deal_v"]) if d["deal_v"] is not None else "", "value_basis": d["basis"],
            "value_confidence": d["conf"], "addressable_share": d["addr"], "framework_split": round(d["split"], 3),
            "gross_margin_pct": round(d["m"], 4), "net_margin_pct": round(d["net"], 4),
            "gross_profit_usd": round(d["gp"]) if d["gp"] is not None else "", "pursuit_cost_usd": round(d["cost"]),
            "roi": d["roi"], "payment_days": d["pay_days"], "price_trend_3m_pct": tr.get("chg_3m_pct", ""),
            "price_signal": tr.get("signal", ""), "route": d["route"], "edge_weight": round(d["edge"], 2),
            "priority_ev_usd": d["priority_ev"],
            "import_duty_pct": round(d["fta_duty"], 4) if d["fta_duty"] is not None else "",
            "fta_edge_pct": round(d["fta_up"], 4) if d["fta_up"] else "", "fta_note": d["fta_note"],
        })
    return st
