"""USDA AMS Market News public reports (no API key): PDF reports at ams.usda.gov/mnreports/.

Reports
  AMS_1604  Global Dairy Trade auction recap (USD/t, average of all contracts)      -> T1 (auction)
  AMS_3510  National Animal By-Product Feedstuff (weekly)                          -> T2
  AMS_3668  National Grain & Oilseed Processor Feedstuff (monthly)                -> T2
  AMS_2461  National Weekly Boxed Beef Cutout (LM_XB459)                           -> T2
  AMS_2498  National Daily Pork FOB Plant (LM_PK602)                               -> T2
  AMS_2843  Daily National Shell Egg Index                                          -> T2
  FVWTRDS   National Shipping Point Trends, fruit & vegetables (weekly)            -> T2
Every price keeps the report wording (product, region/origin, package) in `source` and the conversion
in `calc`. Rows are addressed by HS code, never by sheet row number.
"""
from __future__ import annotations

import datetime as dt
import io
import re

from ..common import Price, session, log, polite_sleep, load_master

BASE = "https://www.ams.usda.gov/mnreports/"
LB_PER_T = 2204.62262
KG_PER_LB = 0.45359237
KG_PER_SHORT_TON = 907.18474


def _hs_rows():
    m = {}
    for r in load_master():
        if r["layer"] == "SEARCH":
            m.setdefault(r["hs6"], r["row"])
    return m


def _pdf_text(name: str) -> str:
    import pdfplumber
    r = session().get(BASE + name, timeout=90)
    r.raise_for_status()
    with pdfplumber.open(io.BytesIO(r.content)) as pdf:
        return "\n".join((p.extract_text() or "") for p in pdf.pages)


def _date(text: str, fmt_hint=None) -> dt.date | None:
    m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December) (\d{1,2}), (\d{4})", text)
    if m:
        return dt.datetime.strptime(" ".join(m.groups()), "%B %d %Y").date()
    return None


def _num(s: str) -> float:
    return float(s.replace(",", "").replace("$", ""))


# ------------------------------------------------------------------ GDT (AMS_1604)
GDT = {"Anhydrous Milk Fat": "040590", "Butter": "040510", "Buttermilk Powder": "040390",
       "Cheese - Cheddar": "040690", "Lactose": "170211", "Mozzarella": "040610",
       "Skim Milk Powder": "040210", "Whole Milk Powder": "040221"}


def gdt(hs: dict) -> list[Price]:
    t = _pdf_text("ams_1604.pdf")
    block = t.split("U.S. Dollars per Pound")[0]
    ev = re.search(r"Event (\d+) Recap - ([A-Za-z]+ \d{1,2}, \d{4})", block)
    d = dt.datetime.strptime(ev.group(2), "%B %d, %Y").date() if ev else _date(block)
    out = []
    for item, code in GDT.items():
        m = re.search(rf"^{re.escape(item)} (.+)$", block, re.M)
        if not m or code not in hs:
            continue
        prices = re.findall(r"\$([\d,]+)", m.group(1))
        if not prices:
            continue
        avg = _num(prices[-1])  # last $ value = "All Contracts" average
        out.append(Price(row=hs[code], unit_usd="USD/t", price_type=f"GDT auction, average of all contracts (event {ev.group(1) if ev else ''})",
                         price_usd=avg, orig_price=avg, orig_ccy="USD", price_date=d.isoformat(),
                         source=f"Global Dairy Trade event {ev.group(1) if ev else ''} via USDA Dairy Market News (AMS_1604) - {item}",
                         link=BASE + "ams_1604.pdf", calc=f"{avg:,.0f} USD/t (average of all contract periods) as published",
                         source_key="usda_gdt"))
    return out


# ------------------------------------------------------------------ feedstuff tables (AMS_3510 weekly, AMS_3668 monthly)
FEED_3510 = {"Choice White Grease": "150120", "Yellow Grease": "151800", "Meat and Bone Meal Ruminant 46-50%": "230110"}
FEED_3668 = {"Yellow Corn Hominy Feed": "230210", "Soybean Hulls": "230250", "Corn Gluten Feed Pellets 21%": "230310",
             "Corn Distillers Dried Grain 10%": "230330", "Cottonseed Meal 41%": "230610", "Linseed Meal": "230620",
             "Sunflower Meal": "230630", "Canola Meal 36%": "230641", "Safflower Meal 25%": "230690",
             "Cottonseed (Whole) Fuzzy": "120729", "Soybean Meal 46.5-48%": "230400", "Soybean Oil": "150710"}


def _feed_tables(text: str):
    """Yield (commodity, unit, first_region_line) from AMS feedstuff tables."""
    lines = text.splitlines()
    for i, l in enumerate(lines[:-2]):
        if lines[i + 1].startswith("Region Sale Type"):
            unit = "c/lb" if "¢/Lb" in lines[i + 1] or "(¢" in lines[i + 1] else "usd/st"
            rows = []
            for k in range(i + 2, min(i + 12, len(lines))):
                if lines[k + 1:k + 2] and lines[k + 1].startswith("Region Sale Type"):
                    break
                if re.search(r"\b(Trade|Ask|Bid|Offer)\b", lines[k]):
                    rows.append(lines[k])
                else:
                    break
            if rows:
                yield l.strip(), unit, rows


def _row_price(line: str):
    m = re.search(r"\b(?:Trade|Ask|Bid|Offer)\s+([\d,]+\.\d+)(?:-([\d,]+\.\d+))?", line)
    if not m:
        return None, None
    lo = _num(m.group(1)); hi = _num(m.group(2)) if m.group(2) else lo
    region = line[:m.start()].strip()
    return (lo + hi) / 2, f"{region}: {m.group(1)}" + (f"-{m.group(2)}" if m.group(2) else "")


def feedstuff(hs: dict, name: str, mapping: dict, ptype: str) -> list[Price]:
    t = _pdf_text(name)
    rep = re.search(r"Report for (\d+/\d+/\d{4}) - (\d+/\d+/\d{4})", t)
    end = dt.datetime.strptime(rep.group(2), "%m/%d/%Y").date() if rep else _date(t)
    out = []
    for comm, unit, rows in _feed_tables(t):
        code = mapping.get(comm)
        if not code or code not in hs:
            continue
        pref = [r for r in rows if r.startswith(("Central US", "Illinois"))] or rows
        mid, desc = _row_price(pref[0])
        if mid is None:
            continue
        if unit == "c/lb":
            usd = mid / 100 * LB_PER_T; calc = f"{desc} mid {mid:.2f} US cents/lb / 100 x 2,204.62 lb/t = {usd:,.2f} USD/t"
        else:
            usd = mid * 1000 / KG_PER_SHORT_TON; calc = f"{desc} mid {mid:,.2f} USD/short ton / 0.907185 = {usd:,.2f} USD/t"
        out.append(Price(row=hs[code], unit_usd="USD/t", price_type=ptype, price_usd=usd, orig_price=round(mid, 2),
                         orig_ccy="USD", price_date=end.isoformat(),
                         source=f"USDA AMS {name.split('.')[0].upper()} - {comm}, {desc.split(':')[0]}",
                         link=BASE + name, calc=calc, source_key="usda"))
    return out


# ------------------------------------------------------------------ boxed beef (AMS_2461) and pork (AMS_2498)
def beef(hs: dict) -> list[Price]:
    t = _pdf_text("ams_2461.pdf")
    m = re.search(r"Weekly Average ([\d.]+) ([\d.]+)", t)
    d = _date(t)
    if not m or "020130" not in hs:
        return []
    c = float(m.group(1)); usd = c / 100 / KG_PER_LB
    return [Price(row=hs["020130"], unit_usd="USD/kg", price_type="Boxed beef cutout, Choice, weekly average (negotiated)",
                  price_usd=usd, orig_price=c, orig_ccy="USD", price_date=d.isoformat(),
                  source="USDA AMS LM_XB459 National Weekly Boxed Beef Cutout - Choice 600-900 lb", link=BASE + "ams_2461.pdf",
                  calc=f"{c} USD/cwt / 100 lb / 0.45359 kg/lb = {usd:.4f} USD/kg", source_key="usda")]


def pork(hs: dict) -> list[Price]:
    t = _pdf_text("ams_2498.pdf")
    m = re.search(r"Date Loads Carcass Loin Butt Pic Rib Ham Belly\n(\d+/\d+/\d{4}) ([\d.,]+) ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)", t)
    if not m:
        return []
    d = dt.datetime.strptime(m.group(1), "%m/%d/%Y").date()
    vals = {"Carcass": float(m.group(3)), "Ham": float(m.group(8))}
    out = []
    for lab, code in (("Carcass", "020319"), ("Ham", "020312")):
        if code not in hs:
            continue
        c = vals[lab]; usd = c / 100 / KG_PER_LB
        out.append(Price(row=hs[code], unit_usd="USD/kg", price_type="Pork cutout value, daily (negotiated, FOB plant)",
                         price_usd=usd, orig_price=c, orig_ccy="USD", price_date=d.isoformat(),
                         source=f"USDA AMS LM_PK602 National Daily Pork FOB Plant - {lab} cutout value (215 lb carcass)",
                         link=BASE + "ams_2498.pdf", calc=f"{c} USD/cwt / 100 lb / 0.45359 kg/lb = {usd:.4f} USD/kg",
                         source_key="usda"))
    return out


def eggs(hs: dict) -> list[Price]:
    t = _pdf_text("ams_2843.pdf")
    m = re.search(r"White Large [\d,]+ ([\d.]+) - ([\d.]+) ([\d.]+)", t)
    d = _date(t) or dt.date.today()
    rp = re.search(r"Report for: (\d+/\d+/\d{4})", t)
    if rp:
        d = dt.datetime.strptime(rp.group(1), "%m/%d/%Y").date()
    if not m or "040721" not in hs:
        return []
    c = float(m.group(3)); usd = c / 100 / 0.680389   # large eggs: minimum 24 oz (0.6804 kg) per dozen
    return [Price(row=hs["040721"], unit_usd="USD/kg", price_type="National shell egg index, white large, loose, FOB (5-day weighted avg)",
                  price_usd=usd, orig_price=c, orig_ccy="USc/dozen", price_date=d.isoformat(),
                  source="USDA AMS Daily National Shell Egg Index (AMS_2843) - White Large", link=BASE + "ams_2843.pdf",
                  calc=f"{c} US cents/dozen / 100 / 0.6804 kg per dozen (24 oz large) = {usd:.4f} USD/kg", source_key="usda")]


# ------------------------------------------------------------------ fruit & vegetables (FVWTRDS)
FV = {"TOMATOES": "070200", "ONIONS, DRY": "070310", "BROCCOLI": "070410", "BRUSSELS SPROUTS": "070420",
      "CABBAGE": "070490", "LETTUCE, ICEBERG": "070511", "LETTUCE, ROMAINE": "070519", "CARROTS": "070610",
      "CUCUMBERS": "070700", "PEAS, SNOW": "070810", "BEANS, ROUND GREEN TYPE": "070820", "ASPARAGUS": "070920",
      "EGGPLANT": "070930", "CELERY": "070940", "PEPPERS, BELL TYPE": "070960", "SPINACH": "070970",
      "SQUASH, ZUCCHINI": "070993", "CORN, SWEET": "070999", "POTATOES": "070190", "YUCA (CASSAVA)": "071410",
      "SWEET POTATOES": "071420", "YAMS (NAMES)": "071430", "TARO": "071440", "MALANGA/ YAUTIA": "071450",
      "COCONUTS": "080119", "PLANTAINS": "080310", "BANANAS": "080390", "PINEAPPLES": "080430", "AVOCADOS": "080440",
      "MANGOES": "080450", "ORANGES": "080510", "TANGERINES": "080521", "LEMONS": "080550", "GRAPES": "080610",
      "WATERMELONS": "080711", "CANTALOUPES": "080719", "PAPAYA": "080720", "APPLES": "080810", "PEARS": "080830",
      "STRAWBERRIES": "081010", "RASPBERRIES": "081020", "BLUEBERRIES": "081040", "DRAGON FRUIT (PITAYA)": "081090",
      "GINGER ROOT": "091011"}
PKG = re.compile(
    r"(?:(?P<n>\d+)[ -](?P<each>\d+(?:\.\d+)?)[- ](?P<eu>ounce|oz|pound|lb)\b[^;.]*?"         # e.g. 12 6-ounce cups, 8 1-pound containers
    r"|(?P<w>\d+(?:\.\d+)?)[- ]?(?P<u>pound|lb|kg|kilogram)s?\b[^;.]*?)"                 # e.g. 25 pound cartons, 15 kg cartons
    r"(?:\bmostly )?(?<![\d.])(?P<lo>\d+\.\d\d)(?:\s*-\s*(?P<hi>\d+\.\d\d))?")


def _kg(m) -> float | None:
    if m.group("n"):
        each = float(m.group("each")); n = int(m.group("n"))
        per = 16 if m.group("eu") in ("ounce", "oz") else 1
        if n < each:                      # "35-40 pound cartons" is a weight range, not 35 packs of 40 lb
            return (n + each) / 2 / per * KG_PER_LB
        return n * each / per * KG_PER_LB
    w = float(m.group("w"))
    return w if m.group("u") in ("kg", "kilogram") else w * KG_PER_LB


def fruit_veg(hs: dict) -> list[Price]:
    t = _pdf_text("fvwtrds.pdf")
    md = re.search(r"Prices are for \w+, ([A-Za-z]+ \d{1,2}, \d{4})", t)
    d = dt.datetime.strptime(md.group(1), "%B %d, %Y").date() if md else _date(t)
    t = re.sub(r"(?m)^(NATIONAL SHIPPING POINT TRENDS|Agricultural Marketing Service|Specialty Crops Market News.*|Email us.*|Page \d+ FVWTRDS|Source: USDA.*|Washington, DC.*|Phone \(.*|https://\S+)$", "", t)
    out = []
    for sec in re.split(r"(?m)^---", t)[1:]:
        first = sec.split("\n", 1)[0].strip()
        title = first if first in FV else None
        if not title or FV[title] not in hs:
            continue
        body = re.sub(r"-\n", "-", sec[len(title):])
        body = re.sub(r"\s*\n\s*", " ", body)
        # one segment per origin: "<ORIGIN IN CAPS> [2026 CROP] Shipments|Crossings|Imports ..."
        raw = re.split(r"(?=\b[A-Z][A-Z0-9 ,.&/()'-]{6,}?(?: \d{4} CROP)? (?:Shipments|Crossings|Imports)\b)", body)
        segs, carry = [], ""
        for x in raw:                      # re-join origin names that the split cut ("NEW " + "YORK ...")
            if len(x.strip()) < 30 and not PKG.search(x):
                carry += x; continue
            segs.append(carry + x); carry = ""
        for seg in segs:
            seg = seg.strip()
            if not seg:
                continue
            pm = PKG.search(seg.split("ORGANIC")[0])
            if not pm:
                continue
            kg = _kg(pm)
            if not kg or kg < 1.5:          # consumer packs quoted without the case count are not wholesale units
                continue
            lo = float(pm.group("lo")); hi = float(pm.group("hi") or lo); mid = (lo + hi) / 2
            usd = mid / kg
            origin = re.split(r" (?:\d{4} CROP )?(?:Shipments|Crossings|Imports)\b", seg)[0][:80].strip()
            pkg_txt = re.sub(r"\s+", " ", pm.group(0))[:100]
            out.append(Price(row=hs[FV[title]], unit_usd="USD/kg", price_type="Shipping point / port of entry FOB, weekly (USDA)",
                             price_usd=usd, orig_price=round(mid, 2), orig_ccy="USD", price_date=d.isoformat(),
                             source=f"USDA AMS National Shipping Point Trends - {title.title()}, {origin.title()}",
                             link=BASE + "fvwtrds.pdf",
                             calc=f"{pkg_txt} -> mid {mid:.2f} USD per package / {kg:.3f} kg = {usd:.4f} USD/kg",
                             source_key="usda"))
            break
    return out


def fetch() -> list[Price]:
    hs = _hs_rows()
    out: list[Price] = []
    jobs = [("gdt", lambda: gdt(hs)),
            ("by-products", lambda: feedstuff(hs, "ams_3510.pdf", FEED_3510, "Animal by-product feedstuff, weekly (USDA)")),
            ("feedstuff", lambda: feedstuff(hs, "ams_3668.pdf", FEED_3668, "Processor feedstuff, monthly range midpoint (USDA)")),
            ("beef", lambda: beef(hs)), ("pork", lambda: pork(hs)), ("eggs", lambda: eggs(hs)),
            ("fruit_veg", lambda: fruit_veg(hs))]
    for name, fn in jobs:
        try:
            got = fn(); out += got
            log.info("usda %s: %d prices", name, len(got))
        except Exception as e:  # noqa: BLE001
            log.warning("usda %s failed: %s", name, e)
        polite_sleep(1)
    return out
