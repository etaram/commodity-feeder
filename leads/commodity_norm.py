"""Normalise commodity price rows before any comparison (upgrade brief section 11).

Input : data/leads/commodity_prices.csv (id, hs6, commodity, price_usd, unit, price_type, date, source, quality, link)
Output: data/leads/commodity_prices_norm.csv - one row per input row, raw fields kept, plus:
  product            canonical product name (the commodity text with the exchange / contract suffix removed)
  grade              only when the name or source states one (Brent, WTI, HRW, Thai 5% broken, RSS3, Choice, ...)
  origin             ISO3 or region, only when the name or source states it (Peru Imports, Mexico Crossings, ...)
  delivery_location  only when stated (Henry Hub, TTF, FOB plant, EU extra-EU import, China domestic, ...)
  incoterm           FOB / CIF / CFR / EXW / DAP / FAS only when the text says so
  unit_canonical     USD/t, USD/kg, USD/lb, USD/bu, USD/bbl, USD/MMBtu, ... (spelling normalised, no conversion)
  price_usd_t        price per metric tonne when a known mass factor exists (kg, lb, short ton, long ton, cwt,
                     troy oz, bushel of wheat / maize / soybeans / oats); blank for volume and energy units
  conversion         the factor applied, as text, so the arithmetic can be checked
  price_type_norm    futures | spot | index | assessment | offer | unknown
  physical           true for a price of physical goods (spot, assessment, offer); false for futures and index
  timestamp          the price date (ISO)
  source_tier        T1..T4 from the quality field
  basis_note         the raw price_type text, kept so the user sees what the price is

Nothing is guessed: a field the row does not state stays blank. No model calls.
Run: python -m leads.commodity_norm
"""
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/leads/commodity_prices.csv"
OUT = ROOT / "data/leads/commodity_prices_norm.csv"

# mass of one unit in kg (metric tonne = 1000 kg)
KG = {"kg": 1.0, "lb": 0.453592, "short ton": 907.185, "long ton": 1016.05, "cwt": 45.3592, "t": 1000.0, "mt": 1000.0,
      "oz": 0.0311035}  # oz in commodity quotes is the troy ounce (precious metals); 31.1035 g
BUSHEL_KG = {"wheat": 27.2155, "maize": 25.4012, "corn": 25.4012, "soybean": 27.2155, "soybeans": 27.2155, "oats": 14.5150}
UNIT_SPELL = {"usd/t": "USD/t", "usd/mt": "USD/t", "usd/tonne": "USD/t", "usd/kg": "USD/kg", "usd/lb": "USD/lb", "usd/bu": "USD/bu",
              "usd/bbl": "USD/bbl", "usd/mmbtu": "USD/MMBtu", "usd/mwh": "USD/MWh", "usd/gal": "USD/gal", "usd/oz": "USD/oz",
              "usd/cwt": "USD/cwt", "usd/short ton": "USD/short ton", "usd/long ton": "USD/long ton", "usd/m3": "USD/m3",
              "usd/1000 bf": "USD/1000 bf"}

# price type from the price_type text (first match wins), then from the quality tier
PRICE_TYPE_RULES = [
    (r"\bfutures?\b|front month", "futures"),
    (r"trade unit value|export price|import price|unit value", "index"),
    (r"cash settlement|official (cash|settlement)", "spot"),
    (r"\bspot\b.*assessment|assessment|reference price|retail average|survey", "assessment"),
    (r"\bspot\b|market price|shipping point|port of entry|cutout|auction|feedstuff|ex-vat", "spot"),
    (r"\boffer\b|quotation|quote", "offer"),
]
PHYSICAL = {"spot": True, "assessment": True, "offer": True, "futures": False, "index": False}

# grades: stated tokens only (word-bounded). For the exchange rows (L...) the commodity text is a product name and
# carries the grade (Brent, HRW, No.11); for the HS rows (H...) the commodity text is the HS description, so the grade
# comes only from the series description the source names after " - " (Young bull carcass R3, Li2O 6% min, ...).
GRADES = [
    r"Brent", r"WTI", r"Henry Hub", r"TTF", r"RBOB", r"ULSD", r"U3O8", r"Mont Belvieu", r"\bHRW\b", r"\bSRW\b", r"No\.\s?11", r"No\.\s?2",
    r"Class III", r"Arabica", r"Robusta", r"FCOJ", r"RSS3", r"TSR\s?20", r"\bAPI\s?2\b", r"\bAPI\s?4\b", r"Thai 5%( broken)?", r"\bChoice\b",
    r"\bSelect\b", r"\bPrime\b", r"\b304\b", r"\b316\b", r"\bQ235\b", r"Extra virgin", r"\bVirgin\b", r"Lampante", r"\bRefined\b", r"Crude palm",
    r"\bgranular\b", r"\bprilled\b", r"\bR3\b", r"S\+E", r"\bclass [A-C]\b", r"\bDurum\b", r"\bMilling\b", r"\bFeed\b", r"Skim Milk Powder",
    r"Whole Milk Powder", r"Cheddar", r"Mozzarella", r"Anhydrous Milk Fat", r"Buttermilk Powder", r"Bottle-grade", r"Cold-rolled", r"Hot-rolled",
    r"\bcathodes?\b", r"\bAZ91D\b", r"\bTA2\b", r"\bW-4\b", r"\b5-5-3\b", r"\bUAN32\b", r"\b10-34-0\b", r"\bSS\b",
    r"(?:[A-Z][A-Za-z0-9()+]*\s)?\d+(?:\.\d+)?%\s*(?:min|max)\b", r"\b\d+-\d+%\b", r"\b\d{3}-\d{3} lb\b",
]
GRADE_RX = re.compile("|".join(f"(?:{g})" for g in GRADES), re.I)

# delivery locations stated in names or sources; the first match wins
DELIVERY = [
    (r"\b(CIF|FOB|EXW|CFR|FAS|DAP|DDP) (China|India|US|USA|Europe|Rotterdam|Gulf|ARA|Brazil|Australia|Malaysia|Indonesia)\b", None),
    (r"\b(Ex-VAT Delivered|Delivered|Port) (China|India|US|Europe)\b", None),
    (r"Henry Hub", "Henry Hub (US)"), (r"\bTTF\b", "TTF (Netherlands)"), (r"Mont Belvieu", "Mont Belvieu (US)"),
    (r"FOB plant", "FOB plant (US)"), (r"Ports Of Entry South Florida", "US port of entry (South Florida)"),
    (r"Crossings Through", "US border crossing"), (r"shipping point|port of entry", "US shipping point"),
    (r"extra-EU imports", "EU (extra-EU import, statistical)"), (r"imports CN/JP/KR/IN/BR", "CN/JP/KR/IN/BR (import, statistical)"),
    (r"ex-packaging station", "EU ex-packaging station"), (r"euro-area Member States", "EU (euro-area, weekly average)"),
    (r"China domestic", "China (domestic)"), (r"LME .*cash.settlement|LME official", "LME warehouse (cash)"),
    (r"\bCIF ARA\b", "CIF ARA"), (r"\bFOB Gulf\b", "FOB Gulf"), (r"Rotterdam", "Rotterdam"), (r"US retail", "US retail"),
    (r"Central US", "Central US"), (r"CA-Central Coast", "US (CA Central Coast)"), (r"Pacific Northwest", "US (Pacific Northwest)"),
    (r"Twin Falls-Burley|Idaho", "US (Idaho)"), (r"Florida West And Georgia", "US (Florida / Georgia)"),
]
INCOTERM_RX = re.compile(r"\b(FOB|CIF|CFR|EXW|DAP|FAS|DDP|CPT)\b")

# origins stated in the text: country words to ISO3, regions kept as names
ORIGIN_COUNTRY = {"peru": "PER", "peruvian": "PER", "mexico": "MEX", "mexican": "MEX", "brazil": "BRA", "brazilian": "BRA", "norway": "NOR",
                  "norwegian": "NOR", "australia": "AUS", "australian": "AUS", "thailand": "THA", "thai": "THA", "india": "IND", "indian": "IND",
                  "indonesia": "IDN", "indonesian": "IDN", "malaysia": "MYS", "malaysian": "MYS", "argentina": "ARG", "argentine": "ARG",
                  "ukraine": "UKR", "ukrainian": "UKR", "russia": "RUS", "russian": "RUS", "canada": "CAN", "canadian": "CAN", "chile": "CHL",
                  "chilean": "CHL", "south africa": "ZAF", "south african": "ZAF", "turkey": "TUR", "turkish": "TUR", "egypt": "EGY", "egyptian": "EGY",
                  "vietnam": "VNM", "vietnamese": "VNM", "colombia": "COL", "colombian": "COL", "mozambique": "MOZ", "mozambican": "MOZ",
                  "china": "CHN", "chinese": "CHN", "us": "USA", "u\\.s\\.": "USA"}
ORIGIN_REGION = ["Central America", "Caribbean", "South America", "West Africa", "Black Sea", "Baltic"]
_ORG = "|".join(re.escape(k) for k in list(ORIGIN_COUNTRY) + [r.lower() for r in ORIGIN_REGION])
# "Peru Imports", "Mexico Crossings", "Thai 5%", "Mozambican TiO2", "Australian Zr": the origin word is stated as such
ORIGIN_RX = re.compile(r"\b(" + _ORG + r")\b(?=\s+(imports?|crossings?|origin|export|\d+%|[A-Z][a-z]*\d|[A-Z][a-z]+ \(|Zr\b|HRW|SRW))", re.I)
ORIGIN_SOURCE = [(r"Statistics Norway", "NOR")]
# the exchange / contract suffix in names like "Crude oil Brent - ICE futures"
SUFFIX_RX = re.compile(r"\s+-\s+[A-Z][A-Za-z/ ]*?(futures|cash|settlement|auction|spot)\b.*$", re.I)
NEG_RX = re.compile(r"\b(other than|excluding|not|except)\b[^,;]*", re.I)


def canon_unit(unit):
    u = (unit or "").strip()
    return UNIT_SPELL.get(u.lower(), u)


def to_tonne(price, unit, product=""):
    """(price per tonne, factor text) when the unit is a mass unit with a known factor; (None, '') otherwise.
    Barrels, gallons, MMBtu, MWh, m3 and board feet are never converted: the density is not stated."""
    u = canon_unit(unit)
    m = re.match(r"^USD/(.+)$", u)
    if not m or price is None:
        return None, ""
    base = m.group(1).strip().lower()
    if base == "t":
        return price, "USD/t as given"
    if base == "bu":
        key = next((k for k in BUSHEL_KG if re.search(rf"\b{k}\b", product, re.I)), None)
        if not key:
            return None, ""
        kg = BUSHEL_KG[key]
        return price / kg * 1000.0, f"1 bu {key} = {kg} kg"
    if base in KG:
        kg = KG[base]
        return price / kg * 1000.0, f"1 {base} = {kg} kg" + (" (troy oz)" if base == "oz" else "")
    return None, ""


def price_type_of(price_type, quality):
    text = f"{price_type or ''}".lower()
    for rx, kind in PRICE_TYPE_RULES:
        if re.search(rx, text, re.I):
            return kind
    q = (quality or "").lower()
    if q.startswith("t1") and "exchange" in q:
        return "futures" if "future" in text else "unknown"
    if q.startswith("t4") and "trade statistics" in q:
        return "index"
    return "unknown"


def series_desc(source):
    """The series description a source names after the first ' - ' (blank when the source has none)."""
    src = source or ""
    return src.split(" - ", 1)[1].strip() if " - " in src else ""


def grade_of(row_id, name, source):
    texts = [series_desc(source)]
    if (row_id or "").startswith("L") or " - " in (name or ""):
        texts.insert(0, NEG_RX.sub("", name or ""))
    hits = []
    for text in texts:
        for m in GRADE_RX.finditer(text):
            g = re.sub(r"\s+", " ", m.group(0).strip())
            if g.lower() not in [h.lower() for h in hits]:
                hits.append(g)
    return "; ".join(hits[:3])


def origin_of(name, source, row_id=""):
    # the HS description of an H row is not a statement of origin ("Norway lobsters" is a species)
    texts = [series_desc(source)] if (row_id or "").startswith("H") else [name or "", series_desc(source)]
    for text in texts:
        m = ORIGIN_RX.search(text)
        if m:
            key = m.group(1).lower()
            return ORIGIN_COUNTRY.get(key) or next(r for r in ORIGIN_REGION if r.lower() == key)
    for rx, iso in ORIGIN_SOURCE:
        if re.search(rx, source or "", re.I):
            return iso
    return ""


def delivery_of(name, price_type, source):
    text = " | ".join([name or "", price_type or "", source or ""])
    for rx, loc in DELIVERY:
        m = re.search(rx, text, re.I)
        if m:
            return loc if loc else m.group(0)
    return ""


def incoterm_of(name, price_type, source):
    m = INCOTERM_RX.search(" ".join([name or "", price_type or "", source or ""]))
    return m.group(1).upper() if m else ""


def product_of(name):
    p = SUFFIX_RX.sub("", name or "").strip()
    p = re.sub(r"\s+", " ", p)
    return p[:160]


def tier_of(quality):
    m = re.match(r"^(T[1-4])\b", (quality or "").strip())
    return m.group(1) if m else ""


def num(v):
    try:
        x = float(str(v).replace(",", ""))
        return x if x == x and x not in (float("inf"), float("-inf")) else None
    except Exception:
        return None


FIELDS = ["id", "hs6", "commodity", "price_usd", "unit", "price_type", "date", "source", "quality", "link",
          "product", "grade", "origin", "delivery_location", "incoterm", "unit_canonical", "price_usd_t", "conversion",
          "price_type_norm", "physical", "timestamp", "source_tier", "basis_note"]


def normalise(row):
    """One raw row -> normalised dict (raw fields kept). Pure; no network, no model."""
    name, src, pt, q = row.get("commodity", ""), row.get("source", ""), row.get("price_type", ""), row.get("quality", "")
    price = num(row.get("price_usd"))
    kind = price_type_of(pt, q)
    per_t, conv = to_tonne(price, row.get("unit", ""), name)
    out = {k: row.get(k, "") for k in FIELDS[:10]}
    out.update({
        "product": product_of(name), "grade": grade_of(row.get("id", ""), name, src), "origin": origin_of(name, src, row.get("id", "")),
        "delivery_location": delivery_of(name, pt, src), "incoterm": incoterm_of(name, pt, src),
        "unit_canonical": canon_unit(row.get("unit", "")),
        "price_usd_t": f"{per_t:.6g}" if per_t is not None else "", "conversion": conv,
        "price_type_norm": kind, "physical": "" if kind == "unknown" else ("true" if PHYSICAL[kind] else "false"),
        "timestamp": (row.get("date") or "")[:10], "source_tier": tier_of(q), "basis_note": pt,
    })
    return out


def load_norm(path=OUT):
    """Normalised rows keyed by id (reads the CSV this module writes; empty when absent)."""
    if not Path(path).exists():
        return {}
    return {r["id"]: r for r in csv.DictReader(open(path, encoding="utf-8"))}


def main():
    rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
    out = [normalise(r) for r in rows]
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out)
    known = sum(1 for o in out if o["price_type_norm"] != "unknown")
    phys = sum(1 for o in out if o["physical"] == "true")
    fut = sum(1 for o in out if o["price_type_norm"] == "futures")
    conv = sum(1 for o in out if o["conversion"] and not o["conversion"].endswith("as given"))
    kinds = {}
    for o in out:
        kinds[o["price_type_norm"]] = kinds.get(o["price_type_norm"], 0) + 1
    print(f"commodity_norm: {len(out)} rows, {known} with a known price type {kinds}, physical {phys}, futures {fut}, "
          f"unit conversions to USD/t {conv}, grade stated {sum(1 for o in out if o['grade'])}, origin stated {sum(1 for o in out if o['origin'])}, "
          f"delivery stated {sum(1 for o in out if o['delivery_location'])}, incoterm stated {sum(1 for o in out if o['incoterm'])}")
    return out


if __name__ == "__main__":
    main()
