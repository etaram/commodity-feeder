"""Landed-cost arithmetic and comparability checks for commodity prices (upgrade brief section 11).

landed_cost(...)  every component of a delivered cost, the total of the components supplied, and a 'missing' list of
                  the inputs not supplied. Nothing missing is ever filled with a guess: a missing freight or duty stays
                  missing and the total is marked partial.
basis_gap(a, b)   the incoterm, delivery location and date differences that landed_cost must bridge first
comparable(a, b)  whether two normalised records (rows of commodity_prices_norm.csv or dicts shaped like them) can be
                  compared at all: same product and grade, both physical or both futures, same unit after conversion.
                  Returns (ok, reasons). A futures benchmark is never comparable with a physical offer.

No arbitrage claims anywhere: these functions state what is comparable and what a delivered cost is made of; they
do not say that a spread exists. Pure Python, no network, no model calls.
"""
import math
import re

from .commodity_norm import canon_unit, to_tonne

INCOTERMS = {"EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP"}
# what the seller's price already includes, by incoterm (main carriage and import duty)
INCLUDES_FREIGHT = {"CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP"}
INCLUDES_DUTY = {"DDP"}


def _num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def landed_cost(price, unit, incoterm, origin, destination, freight_usd_per_t=None, handling=None, duty_pct=None,
                financing_days=None, rate_pct=None, loss_pct=None):
    """Delivered cost per metric tonne, component by component.

    price, unit     the quoted price and its unit (USD/t, USD/kg, USD/lb, USD/short ton, USD/bu with the product in
                    the unit text is not supported here: pass USD/t or a mass unit)
    incoterm        the quoted basis (EXW, FOB, CIF, ...); blank is reported as missing
    origin, destination  ISO3 or place names, kept in the result; blank is reported as missing
    freight_usd_per_t    main carriage per tonne (omit when the incoterm already includes it)
    handling        port / terminal / inland handling per tonne, USD
    duty_pct        import duty at the destination, percent of the CIF value
    financing_days, rate_pct  working-capital cost: days of capital tied up and the annual rate, percent
    loss_pct        physical loss in transit and handling, percent of the quantity

    Returns {components..., total_usd_per_t, complete: bool, missing: [...], notes: [...]}. The total is the sum
    of the components supplied; when anything is missing it is a partial total and 'complete' is False.
    """
    missing, notes = [], []
    p = _num(price)
    base_t, conv = (None, "")
    if p is None:
        missing.append("price")
    else:
        base_t, conv = to_tonne(p, unit)
        if base_t is None:
            missing.append(f"unit conversion to USD/t for {canon_unit(unit) or 'blank unit'}")
    ic = (incoterm or "").strip().upper()
    if ic not in INCOTERMS:
        missing.append("incoterm")
        ic = ""
    if not origin:
        missing.append("origin")
    if not destination:
        missing.append("destination")

    freight = _num(freight_usd_per_t)
    if ic in INCLUDES_FREIGHT:
        if freight:
            notes.append(f"{ic} price already includes main carriage; freight input ignored")
        freight = 0.0
    elif freight is None:
        missing.append("freight_usd_per_t")
    hand = _num(handling)
    if hand is None:
        missing.append("handling")
    duty = _num(duty_pct)
    if ic in INCLUDES_DUTY:
        duty = 0.0
        notes.append("DDP price already includes import duty")
    elif duty is None:
        missing.append("duty_pct")
    days, rate = _num(financing_days), _num(rate_pct)
    if days is None or rate is None:
        missing.append("financing (financing_days and rate_pct)")
    loss = _num(loss_pct)
    if loss is None:
        missing.append("loss_pct")

    goods = base_t if base_t is not None else 0.0
    freight_c = freight or 0.0
    hand_c = hand or 0.0
    cif_value = goods + freight_c
    duty_c = cif_value * (duty / 100.0) if duty is not None else 0.0
    pre_fin = goods + freight_c + hand_c + duty_c
    fin_c = pre_fin * (rate / 100.0) * (days / 365.0) if days is not None and rate is not None else 0.0
    subtotal = pre_fin + fin_c
    # a loss of x% of the quantity raises the cost of each delivered tonne by 1 / (1 - x)
    loss_c = subtotal / (1 - loss / 100.0) - subtotal if loss is not None and 0 <= loss < 100 else 0.0
    if loss is not None and not (0 <= loss < 100):
        notes.append("loss_pct outside 0..100 ignored")
        missing.append("loss_pct")
    total = subtotal + loss_c
    return {
        "price_input": p, "unit_input": canon_unit(unit), "conversion": conv, "incoterm": ic, "origin": origin or "", "destination": destination or "",
        "goods_usd_per_t": round(goods, 4), "freight_usd_per_t": round(freight_c, 4), "handling_usd_per_t": round(hand_c, 4),
        "duty_usd_per_t": round(duty_c, 4), "financing_usd_per_t": round(fin_c, 4), "loss_usd_per_t": round(loss_c, 4),
        "total_usd_per_t": round(total, 4) if base_t is not None else None,
        "complete": not missing, "missing": missing, "notes": notes,
    }


def _key(s):
    return re.sub(r"[^a-z0-9%]+", " ", str(s or "").lower()).strip()


def comparable(a, b):
    """(ok, reasons) for two normalised records. ok only when product and grade match, both are physical or both are
    futures (an index is comparable only with an index), and the price unit is the same after conversion to USD/t."""
    reasons = []
    pa, pb = _key(a.get("product")), _key(b.get("product"))
    if not pa or not pb:
        reasons.append("product missing on one side")
    elif pa != pb:
        reasons.append(f"different products: '{a.get('product')}' vs '{b.get('product')}'")
    ga, gb = _key(a.get("grade")), _key(b.get("grade"))
    if ga != gb:
        reasons.append(f"different grades: '{a.get('grade') or 'not stated'}' vs '{b.get('grade') or 'not stated'}'")
    ta, tb = a.get("price_type_norm", "unknown"), b.get("price_type_norm", "unknown")
    if ta == "unknown" or tb == "unknown":
        reasons.append("price type unknown on one side")
    elif ta == "futures" or tb == "futures":
        if not (ta == "futures" and tb == "futures"):
            reasons.append(f"a futures benchmark is not a physical price ({ta} vs {tb}); it has no delivery location, incoterm or lot")
    elif ta == "index" or tb == "index":
        if not (ta == "index" and tb == "index"):
            reasons.append(f"a statistical index (trade unit value) is not an executable price ({ta} vs {tb})")
    ua, ub = canon_unit(a.get("unit_canonical") or a.get("unit")), canon_unit(b.get("unit_canonical") or b.get("unit"))
    ca, _ = to_tonne(_num(a.get("price_usd")), ua, a.get("product", ""))
    cb, _ = to_tonne(_num(b.get("price_usd")), ub, b.get("product", ""))
    if ua != ub and (ca is None or cb is None):
        reasons.append(f"units differ and cannot both be converted to USD/t: {ua} vs {ub}")
    return (not reasons), reasons


def basis_gap(a, b):
    """What separates two comparable records before their prices can be set side by side: a different incoterm or
    delivery location means freight, handling, duties, financing, losses, volume and working capital must be added
    (landed_cost) first. Returns a list of texts; empty when the basis is the same."""
    gaps = []
    ia, ib = (a.get("incoterm") or "").upper(), (b.get("incoterm") or "").upper()
    da, db = a.get("delivery_location", ""), b.get("delivery_location", "")
    if ia != ib:
        gaps.append(f"incoterm {ia or 'not stated'} vs {ib or 'not stated'}")
    if da != db:
        gaps.append(f"delivery location {da or 'not stated'} vs {db or 'not stated'}")
    if (a.get("timestamp") or "") != (b.get("timestamp") or ""):
        gaps.append(f"dates {a.get('timestamp') or 'not stated'} vs {b.get('timestamp') or 'not stated'}")
    if gaps:
        gaps.append("add freight, handling, duties, financing, losses, volume and working capital (landed_cost) before comparing")
    return gaps
