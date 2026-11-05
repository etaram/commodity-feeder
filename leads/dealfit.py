"""Deal fit: the ranking brain, built for what the system is for.

The goal is not "which tender is big and open" but "which notice can become a Sinder deal": cross-border supply of
goods and commodities, equipment for infrastructure, energy, defence and health projects, with proven foreign
suppliers, as principal (buy and sell), as agent (commission) or as a partner or sub-supplier to the winning
contractor. Services delivered on site, products that need a local marketing licence and routine municipal
purchases through local dealers are not Sinder deals, however large or open they are.

Inputs: the enriched notice (brain.enrich already set EV, route, margins, bidders), the owner's Profile weights
and partner countries (prefs), and how many proven suppliers the universe holds per sector.
Output per notice: score 0-100 (continuous, no saturation: a tie is broken by expected value), fit_why (what
earned the rank) and fit_flags (what cost it, so the owner can correct the rule).
Every rule is a named constant below; tools/fit_calibrate.py compares the result with the owner's labels.
"""
import csv
import math
import re

from .common import LEADS

EMERGING = {"Sub-Saharan Africa", "Middle East & North Africa", "South Asia", "Southeast Asia", "CIS & Central Asia",
            "Latin America"}
IFI = re.compile(r"world bank|afdb|african development|aiib|asian infrastructure|\bidb\b|inter-american|ebrd|\bebrd\b|"
                 r"\bicb\b|international competitive|undp|unops|\bun\b procurement|ungm", re.I)
# goods that need a local marketing authorisation or a licensed local distributor: not a cross-border supply deal
# "blood" and "plasma" only as products (not blood-pressure monitors or plasma cutters)
LICENSED = re.compile(r"pharmaceutical|medicinal|medicines?\b|drugs?\b|vaccin|blood(?![\s-]*(pressure|glucose|gas|bank refrigerat|collection (chair|bed)))|"
                      r"plasma(?![\s-]*(cutt|torch|weld|tv|screen|display|cleaner))|narcotic|insulin|radiopharm|"
                      r"läkemedel|lægemid|medicamento|médicament|arzneimittel|farmac", re.I)
# work that has to be done on site by local staff: no goods cross a border
ON_SITE = re.compile(r"cleaning|catering|canteen|security guard|guarding|staffing|temporary staff|recruit|insurance|"
                     r"legal services|audit|accounting|training|consultan|advisory|social care|home care|nursing|"
                     r"childcare|fostering|facility management|maintenance services|repair services|it services|"
                     r"software support|hosting|printing services|translation|marketing|advertis|event|travel agency|"
                     r"waste collection|refuse collection|street cleaning|grounds maintenance|landscap|"
                     r"servicio de limpieza|servicio de seguridad|nettoyage|gardiennage|reinigung|bewachung", re.I)
# routine purchases a town makes through its local dealer
LOCAL_ROUTINE = re.compile(r"passenger cars?|\bsuv\b|4x4|pick-?up|minibus|school bus|refuse truck|garbage truck|"
                           r"fire engine|ambulance|lawn ?mower|office furniture|stationery|toner|school meals|"
                           r"playground|sports equipment|uniforms? for|\bbooks?\b|library", re.I)
MUNICIPAL = re.compile(r"municipal|municipio|commune|comune|gemeinde|kommun|city of|town of|council|county|"
                       r"regional council|מועצה|עיריית|עירייה|school|university|kindergarten|hospital trust", re.I)
TRADED_GOODS = re.compile(r"wheat|maize|rice|sugar|oil\b|fertili|urea|steel|rebar|cement|bitumen|asphalt|diesel|fuel|"
                          r"coal|copper|aluminium|aluminum|pipe|cable|transformer|generator|solar|pump|meter|"
                          r"equipment|machinery|vehicles|trucks|spare parts|medical equipment|devices|textile|"
                          r"ppe\b|gloves|masks", re.I)

W = {  # points; the sum of the maxima is about 100 before penalties
    "ev_max": 30,       # log-scaled expected value (already weighted by the owner's sector and region preferences)
    "size_max": 10,     # deal size in the range a sourcing firm can finance and still be worth the work
    "goods_max": 18,    # how much of the contract is goods that cross a border (addressable share)
    "access_max": 14,   # open to foreign bidders by rule, or financed by an international bank
    "suppliers_max": 10,  # proven suppliers in the universe for this sector
    "timing_max": 8,    # time to prepare a bid
    "emerging": 5,      # Sinder's markets
    "traded": 4,        # a commodity or equipment line the firm trades
    "repeat_buyer": 3,  # a buyer that buys this every year
    "partner": 5,       # a country with a local partner
    "pen_licensed": 28, "pen_on_site": 26, "pen_routine": 14, "pen_small_local": 10, "pen_closed": 20,
    "pen_set_aside": 25, "pen_exempt": 15, "pen_late": 15, "pen_huge": 6,
}


def _num(v, d=None):
    """A finite number or the default: NaN and infinity never reach the score (min(100, nan) is 100 in Python)."""
    try:
        x = float(str(v).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return d
    return x if math.isfinite(x) else d


def supplier_counts():
    """Tier 1-2 suppliers per sector (data/leads/supplier_sectors.csv, written by the suppliers workflow)."""
    p = LEADS / "supplier_sectors.csv"
    if not p.exists():
        return {}
    return {r["sector"]: int(r["suppliers"] or 0) for r in csv.DictReader(open(p, encoding="utf-8"))}


def supplier_table():
    """Full aggregate rows: sector -> {suppliers, exporters, asia_exporters}; and hs4 -> {suppliers, asia_suppliers}."""
    out = {"sector": {}, "hs": {}}
    for name, key, fn in (("supplier_sectors.csv", "sector", "sector"), ("supplier_hs.csv", "hs4", "hs")):
        p = LEADS / name
        if p.exists():
            for r in csv.DictReader(open(p, encoding="utf-8")):
                out[fn][r[key]] = {k: int(v or 0) for k, v in r.items() if k != key}
    return out


def _log_points(x, lo, hi, pmax):
    """0 at lo, pmax at hi, log scale between."""
    if x is None or x <= lo:
        return 0.0
    return min(pmax, pmax * math.log(x / lo) / math.log(hi / lo))


def fit(r, prefs=None, sup=None):
    prefs, sup = prefs or {}, sup or {}
    text = f"{r.get('title_en') or ''} {r.get('title') or ''} {r.get('commodity') or ''} {r.get('notice_type') or ''}"
    buyer = r.get("buyer") or ""
    sec, region, country = r.get("sector") or "Other", r.get("region") or "", (r.get("country") or "")[:3]
    acc = (r.get("access") or "").lower()
    stage = r.get("stage") or "tender"
    usd = _num(r.get("est_value_usd"))
    ev = _num(r.get("priority_ev_usd"), None)
    if ev is None:
        ev = _num(r.get("ev_usd"), None)
    addr_raw = _num(r.get("addressable_share"), None)
    # an unknown goods share is not a full goods share: half credit and a flag, until the scope is read
    addr = min(1.0, max(0.0, addr_raw)) if addr_raw is not None else 0.5
    days = _num(r.get("days_left"))
    route = r.get("route") or "direct"
    why, flags, pts = [], [], 0.0

    # --- what the deal is worth
    if ev is not None and ev > 0:
        p = _log_points(ev, 1_000, 3_000_000, W["ev_max"]); pts += p
        why.append(f"EV ${ev:,.0f}")
    elif usd is None:
        pts += 4; why.append("value unknown")
    if usd is not None:
        if 300_000 <= usd <= 50_000_000:
            pts += W["size_max"]
        elif 100_000 <= usd < 300_000:
            pts += 4
        elif usd > 50_000_000:
            pts += 5
            if usd > 300_000_000 and route == "direct":
                pts -= W["pen_huge"]; flags.append("very large: realistic only as a sub-supplier to the winner")
        else:
            flags.append("under $100k")

    # --- is it goods that cross a border
    g = W["goods_max"] * addr
    pts += g
    if addr_raw is None:
        flags.append("goods share unknown (counted as half)")
    else:
        why.append("goods supply" if addr >= 0.9 else f"{addr:.0%} of scope is goods" if addr >= 0.3 else "mostly services or works")
    if route != "direct":
        why.append(route)

    # --- can a foreign firm win it
    ifi = bool(IFI.search(f"{acc} {r.get('source') or ''} {text}"))
    # an explicit restriction wins over any positive wording or an IFI mention ("not open to foreign bidders"
    # contains "open to foreign"); a closed notice keeps the partner / sub-supplier routes, flagged, not erased
    closed = bool(re.search(r"\bnot open\b|\bclosed to\b|\bnationals? only\b|\bdomestic (bidders|firms|suppliers) only\b|"
                            r"\blocal (bidders|firms|suppliers) only\b|\b(ncb|national competitive)\b|\brestricted to (national|local|domestic)", acc))
    if country == "ISR":
        pts += 11; why.append("home market")
    elif closed:
        pts -= W["pen_closed"]; flags.append("closed to foreign bidders: partner or sub-supplier route only" + (" (IFI mentioned, restriction applies)" if ifi else ""))
    elif acc.startswith("international") or ifi:
        pts += W["access_max"]; why.append("international: open to foreign bidders" + (" (IFI financed)" if ifi else ""))
    elif any(k in acc for k in ("gpa", "open to foreign", "trade agreements", "may bid")):
        pts += 8; why.append("open under trade agreements")
    elif "local" in acc or "domestic" in acc:
        pts -= W["pen_closed"]; flags.append("local or domestic procurement: partner route only")
    else:
        pts += 3
    if "set-aside" in acc:
        pts -= W["pen_set_aside"]; flags.append("reserved for local small businesses")
    if re.search(r"exempt|direct award|sole source|intent to contract|פטור", f"{acc} {r.get('source') or ''} {r.get('notice_type') or ''}", re.I):
        pts -= W["pen_exempt"]; flags.append("no open competition: a named supplier is already chosen")

    # --- do we have the supply side
    n_sup = sup.get(sec, 0)
    if n_sup:
        s = _log_points(n_sup, 20, 5_000, W["suppliers_max"]); pts += s
        why.append(f"{n_sup:,} proven suppliers in this sector")
    else:
        why.append("no proven suppliers in this sector yet")
    if TRADED_GOODS.search(text) and addr >= 0.5:
        pts += W["traded"]
    if region in EMERGING:
        pts += W["emerging"]; why.append("emerging market")
    partners = prefs.get("partners") or {}
    pv = partners.get(country)
    if pv and str(pv).strip().lower() not in ("0", "false", "no", "none", "candidate"):  # a false or candidate value is not a partner
        pts += W["partner"]; why.append("local partner")
    if (_num(r.get("buyer_awards_12m"), 0) or 0) >= 5:
        pts += W["repeat_buyer"]; why.append("repeat buyer")

    # --- timing
    if stage == "planned":
        pts += 5; why.append("planned: approach before the tender")
    elif days is None:
        pts += 4
    elif days < 0:
        flags.append("deadline passed"); return 0, "; ".join(why), "; ".join(flags)
    elif days < 5:
        pts -= W["pen_late"]; flags.append(f"only {int(days)} days left")
    elif days < 10:
        pts += 3
    elif days <= 60:
        pts += W["timing_max"]
    else:
        pts += 6

    # --- what is not a Sinder deal
    if LICENSED.search(text) or (sec == "Healthcare & pharmaceuticals" and re.search(r"pharma|medicin|drug", text, re.I)):
        pts -= W["pen_licensed"]; flags.append("needs a local marketing licence: distributor route only")
    if ON_SITE.search(text) and addr < 0.9:
        pts -= W["pen_on_site"]; flags.append("delivered on site by local staff")
    elif ON_SITE.search(text):
        pts -= W["pen_on_site"] / 2; flags.append("service wording: check what is actually bought")
    if LOCAL_ROUTINE.search(text):
        pts -= W["pen_routine"]; flags.append("routine purchase through a local dealer")
    if MUNICIPAL.search(buyer) and (usd is None or usd < 1_000_000):
        pts -= W["pen_small_local"]; flags.append("small or unpriced municipal purchase")
    # the economics engine's own verdict lowers the score (Ignore x0.55, Watch x0.85). This is a weight, not a
    # guarantee that every Pursue outranks every Ignore; strict ordering uses fit_bucket (see apply)
    dec = r.get("decision") or ""
    if dec == "Ignore":
        pts *= 0.55; flags.append("engine: ignore")
    elif dec == "Watch":
        pts *= 0.85
    if usd is None:
        pts *= 0.8

    mv = prefs.get("min_value") or 0
    if mv and usd is not None and usd < mv:
        pts *= 0.3; flags.append("below your minimum deal size")
    if stage == "planned" and not (prefs.get("planned", 1) or 0):
        pts *= 0.3; flags.append("planned notices are off in your profile")
    # --- the owner's weights: a soft multiplier, so a 0 still hides and a 2 lifts without saturating
    w = (prefs.get("sector") or {}).get(sec, 1.0) * (prefs.get("region") or {}).get(region, 1.0)
    if w <= 0:
        return 0, "hidden by profile weight", ""
    # EV is already weighted by these preferences (brain.enrich); apply the weight to the rest of the score only
    ev_pts = _log_points(ev, 1_000, 3_000_000, W["ev_max"]) if ev and ev > 0 else 0.0
    pts = ev_pts + (pts - ev_pts) * w ** 0.5
    if usd is None:
        pts = min(pts, 72)  # an unpriced notice never outranks a priced deal of substance
    score = max(0, min(100, round(pts, 1)))
    # warnings first and never cut: what cost the rank must stay visible
    return score, "; ".join(why)[:400], "; ".join(flags)


def apply(tenders, prefs=None):
    sup = supplier_counts()
    for r in tenders:
        r.setdefault("base_score", r.get("score", ""))  # the engine's original score, kept across repeated runs
        s, why, flags = fit(r, prefs, sup)
        r["score"], r["fit_why"], r["fit_flags"] = s, why, flags
        r["fit_bucket"] = {"Pursue": 1, "Watch": 2, "Ignore": 3}.get(r.get("decision") or "", 2)  # explicit ordering bucket
    return sup
