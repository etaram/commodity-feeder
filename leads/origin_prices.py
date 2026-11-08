"""Physical prices by origin and grade, from the official or primary bodies that publish them for free.

Each adapter reads one public page or file and returns prices exactly as published (currency, unit, grade, place),
converted to USD at the day's rate and, when the unit has a known mass, to USD per tonne. Nothing is estimated:
a price that is not on the page is not produced, and every row keeps its source, link, date and basis.
A source that fails keeps its last good rows (dated as published), so a broken page shows as stale, not missing.

  FNC Colombia          parchment coffee FR94 reference price (COP per 125 kg cargo), daily
  Uganda coffee dept.   Robusta screens, Bugisu/Wugar/Drugar arabicas (US cents/lb FOT), daily
  ECX via 2merkato      Ethiopian export and local coffee (ETB per feresula 17 kg), sesame (ETB per quintal), as published
  CEPEA/ESALQ           Brazil arabica and robusta (USD per 60 kg bag), soybean Paranaguá (USD per 60 kg), daily
  CAI                   Indian cotton spot by growth and ICS grade (INR per candy 355.62 kg), daily
  Tea Board India       auction averages by centre, CTC leaf and dust, total tea (INR/kg), weekly
  Spices Board          small cardamom e-auctions (INR/kg), daily
  CAC Rosario (BCR)     Argentine board prices: wheat, maize, sunflower, soy, sorghum (ARS and USD per t), daily
  EIA                   Henry Hub gas, WTI, Brent, NY Harbor ULSD, Gulf Coast jet, Mont Belvieu propane, daily
  SteelBenchmarker      US, China, W. Europe, world export steel and US scrap (USD/t), twice a month
  Drewry WCI            container freight Shanghai to 8 ports and composite (USD per 40 ft), weekly

Run: python -m leads.origin_prices   (writes data/leads/origin_prices.csv; commodity_norm merges it)."""
import csv
import io
import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin

import requests

log = logging.getLogger("origin_prices")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/leads/origin_prices.csv"
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderDealDesk/1.0; +https://desk.sinder.pro)", "Accept-Language": "en,*;q=0.5"}
FIELDS = ["id", "hs6", "commodity", "price_usd", "unit", "price_type", "date", "source", "quality", "link",
          "product", "grade", "origin", "delivery_location", "incoterm", "unit_canonical", "price_usd_t", "conversion",
          "price_type_norm", "physical", "timestamp", "source_tier", "basis_note",
          "price_native", "currency", "unit_native", "adapter", "fetched"]
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def get(url, **kw):
    r = requests.get(url, headers=UA, timeout=60, **kw)
    r.raise_for_status()
    return r


def text_of(html):
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t.replace("&nbsp;", " ").replace("&amp;", "&"))


def num(s):
    s = str(s or "").strip().replace(" ", "")
    if not s or not re.search(r"\d", s):
        return None
    if re.search(r"\d\.\d{3},\d", s) or re.search(r"^\$?\s*\d{1,3}(\.\d{3})+(,\d+)?$", s.strip("$ ")):  # 316.519,00 (es/pt)
        s = s.replace(".", "").replace(",", ".")
    elif re.search(r"^\d+,\d{1,2}$", s.strip("$ ")):  # 206,00
        s = s.replace(",", ".")
    s = re.sub(r"[^\d.\-]", "", s.replace(",", ""))
    try:
        return float(s)
    except ValueError:
        return None


def pdf_text(content):
    import pdfplumber
    with pdfplumber.open(io.BytesIO(content)) as p:
        return "\n".join((pg.extract_text() or "") for pg in p.pages[:4])


def row(adapter, commodity, product, price, ccy, unit, kg, d, source, link, *, grade="", origin="", place="", incoterm="", hs6="",
        kind="spot", tier="T2 Official / primary physical", basis=""):
    return {"adapter": adapter, "commodity": commodity, "product": product, "price_native": price, "currency": ccy, "unit_native": unit,
            "kg": kg, "date": d, "source": source, "link": link, "grade": grade, "origin": origin, "delivery_location": place,
            "incoterm": incoterm, "hs6": hs6, "kind": kind, "tier": tier, "basis": basis}


# ---------------------------------------------------------------- coffee
def fnc_colombia():
    home = get("https://federaciondecafeteros.org/").text
    m = re.search(r"https?://[^\"']*precio_cafe\.pdf", home)
    url = m.group(0) if m else "https://federaciondecafeteros.org/wp-content/uploads/2026/03/precio_cafe.pdf"
    t = pdf_text(get(url).content)
    dm = re.search(r"([A-Za-zé]+)\s+(\d{1,2})\s*/\s*(\d{4})", t)
    es = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
    d = date(int(dm.group(3)), es[dm.group(1).lower()], int(dm.group(2))).isoformat() if dm and dm.group(1).lower() in es else ""
    p = re.search(r"carga de 125 Kg de pergamino seco FR 94\s+([\d,\.]+)\s*COP", t)
    out = []
    if p:
        out.append(row("fnc", "Coffee, parchment FR94 - FNC domestic reference", "Coffee Arabica", num(p.group(1)), "COP", "125 kg cargo", 125, d,
                       "Federación Nacional de Cafeteros de Colombia, daily reference price", url, grade="Parchment (pergamino seco), yield factor 94",
                       origin="COL", place="Colombia, FNC purchase points", hs6="090111", kind="reference",
                       basis="FNC guaranteed purchase price to growers; derived from ICE C close, COP rate and the Colombian differential"))
    return out


def uganda_coffee():
    home = get("https://ugandacoffee.go.ug/").text
    links = re.findall(r"href=\"([^\"]*Daily%20Coffee%20Market%20Report[^\"]*\.pdf)\"", home)
    if not links:
        return []
    url = urljoin("https://ugandacoffee.go.ug/", links[0])
    t = pdf_text(get(url).content)
    dm = re.search(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\s*(\d{4})\s+DAILY", t)
    d = date(int(dm.group(3)), MONTHS[dm.group(1)[:3].lower()], int(dm.group(2))).isoformat() if dm else ""
    out = []
    grades = [("SCREEN 18", "Robusta", "Screen 18"), ("SCREEN 15", "Robusta", "Screen 15"), ("SCREEN 12", "Robusta", "Screen 12"),
              ("BUGISU AA", "Arabica", "Bugisu AA"), ("BUGISU A", "Arabica", "Bugisu A"), ("BUGISU PB", "Arabica", "Bugisu PB"),
              ("BUGISU B", "Arabica", "Bugisu B"), ("WUGAR", "Arabica", "Wugar (washed Uganda arabica)"), ("DRUGAR", "Arabica", "Drugar (dry Uganda arabica)")]
    for key, kind, g in grades:
        m = re.search(rf"{key}\s+([\d.]+)\s+[\d,]+", t)
        if m:
            out.append(row("uganda", f"Coffee {kind} - Uganda {g}", f"Coffee {kind}", num(m.group(1)), "USc", "lb", 0.453592, d,
                           "Uganda Coffee Development (MAAIF), daily coffee market report: indicative FOT prices", url, grade=g, origin="UGA",
                           place="Kampala, free on truck", incoterm="FOT", hs6="090111", kind="reference"))
    return out


def ecx_2merkato():
    base = "https://www.2merkato.com/news/capital-market-and-commodity-exchange/"
    lst = get(base).text
    arts = re.findall(r"href=\"(/news/capital-market-and-commodity-exchange/\d+-ethiopia-commodity-exchange-ecx-daily-trade-data[^\"]*)\"", lst)
    if not arts:
        return []
    url = urljoin("https://www.2merkato.com/", arts[0])
    html = get(url).text
    dm = re.search(r"daily-trade-data-[^\d]*(\d{1,2})-([a-z]+)-(\d{4})", arts[0])
    d = date(int(dm.group(3)), MONTHS[dm.group(2)[:3]], int(dm.group(1))).isoformat() if dm else ""
    from bs4 import BeautifulSoup
    s = BeautifulSoup(html, "lxml")
    out, section = [], ""
    for tr in s.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if len(cells) < 3:
            continue
        if cells[1].lower() == "symbol":
            section = cells[0]
            continue
        p = num(cells[2])
        if p is None:
            continue
        sesame = "sesame" in section.lower()
        # ECX quotes coffee in birr per feresula (17 kg) and sesame in birr per quintal (100 kg)
        out.append(row("ecx", f"{'Sesame' if sesame else 'Coffee'} - ECX {cells[0]} ({cells[1]})", "Sesame seed" if sesame else "Coffee Arabica", p, "ETB",
                       "quintal (100 kg)" if sesame else "feresula (17 kg)", 100 if sesame else 17, d, "Ethiopia Commodity Exchange daily trade data, as published by 2merkato.com", url,
                       grade=f"{section}: {cells[0]} ({cells[1]})", origin="ETH", place="ECX, Addis Ababa", hs6="120740" if sesame else "090111",
                       kind="spot", tier="T3 Exchange data via a publisher", basis="ECX average traded price; the export-grade floor prices of ECTA are not public"))
    return out


def cepea():
    out = []
    pages = [("https://www.cepea.org.br/en/indicator/coffee.aspx", [("Coffee Arabica", "Arabica type 6, São Paulo (CEPEA/ESALQ index)", "090111"),
                                                                     ("Coffee Robusta", "Robusta type 6, Espírito Santo (CEPEA/ESALQ index)", "090111")]),
             ("https://www.cepea.org.br/en/indicator/soybean.aspx", [("Soybeans", "Paranaguá port (CEPEA/ESALQ index)", "120190"),
                                                                     ("Soybeans", "Paraná state (CEPEA/DERAL index)", "120190")])]
    from bs4 import BeautifulSoup
    for url, labels in pages:
        s = BeautifulSoup(get(url).text, "lxml")
        for t, (prod, g, hs) in zip(s.find_all("table"), labels):
            rows = [[c.get_text(" ", strip=True) for c in r.find_all("td")] for r in t.find_all("tr")]
            rows = [r for r in rows if len(r) >= 2 and re.match(r"\d{2}/\d{2}/\d{4}", r[0])]
            if not rows:
                continue
            mm, dd, yy = rows[0][0].split("/")
            out.append(row("cepea", f"{prod} - Brazil {g}", prod, num(rows[0][1]), "USD", "60 kg bag", 60, f"{yy}-{mm}-{dd}",
                           "CEPEA/ESALQ (University of São Paulo) daily indicator", url, grade=g, origin="BRA", place=g.split("(")[0].strip(),
                           hs6=hs, kind="index", tier="T2 Academic physical index"))
    return out


# ---------------------------------------------------------------- India
CANDY_KG = 355.62


def cai_cotton():
    home = get("https://caionline.in/").text
    links = re.findall(r"https?://caionline\.in/uploads/cards/doc/[^\"']*CAI_Upcountry_Spot_Rates\.pdf", home)
    if not links:
        return []
    url = links[0].replace(" ", "%20")
    t = pdf_text(get(url).content)
    dm = re.search(r"(\d{1,2})(?:st|nd|rd|th)\s+([A-Za-z]+)\s+(\d{4})", t)
    d = date(int(dm.group(3)), MONTHS[dm.group(2)[:3].lower()], int(dm.group(1))).isoformat() if dm else ""
    out = []
    for m in re.finditer(r"^\d+\s+(.+?)\s+(ICS-\d{3})\s+\w+\s+(\d{2})mm\s+([\d.]+\s*–\s*[\d.]+).*?\s(\d{5})\s+(\d{5})\s+\(", t, re.M):
        growth, grade, staple, mic, quintal, candy = m.groups()
        out.append(row("cai", f"Cotton, raw - India {growth.strip()} {grade} {staple}mm", "Cotton", num(candy), "INR", "candy (355.62 kg)", CANDY_KG, d,
                       "Cotton Association of India, upcountry spot rates", url, grade=f"{grade}, {staple} mm, micronaire {mic}", origin="IND",
                       place=f"India upcountry ({growth.strip()})", hs6="520100", kind="spot"))
    return out


def tea_board():
    from bs4 import BeautifulSoup
    url = f"https://www.teaboard.gov.in/WEEKLYPRICES/{date.today().year}"
    s = BeautifulSoup(get(url).text, "lxml")
    out = []
    for t, kind in zip(s.find_all("table")[:2], ["CTC leaf and all dust", "Total tea"]):
        rows = [[c.get_text(" ", strip=True) for c in r.find_all(["td", "th"])] for r in t.find_all("tr")]
        head, data = rows[0], [r for r in rows[1:] if r and re.match(r"\d{2}/\d{2}/\d{4}", r[0])]
        for r in data[:3]:  # newest week with a sale at each centre
            dd, mm, yy = r[0].split("/")
            for centre, v in zip(head[1:], r[1:]):
                p = num(v.split("(")[0])
                if p and not any(o["delivery_location"] == f"{centre} auction" and o["grade"] == kind for o in out):
                    out.append(row("teaboard", f"Tea - India {kind}, {centre} auction", "Tea", p, "INR", "kg", 1, f"{yy}-{mm}-{dd}",
                                   "Tea Board India, weekly average auction prices", url, grade=kind, origin="IND", place=f"{centre} auction",
                                   hs6="090240", kind="auction"))
    return out


def spices_cardamom():
    from bs4 import BeautifulSoup
    url = "https://www.indianspices.com/marketing/price/domestic/daily-price.html"
    s = BeautifulSoup(get(url).text, "lxml")
    rows = []
    for tr in s.find_all("tr"):
        c = [x.get_text(" ", strip=True) for x in tr.find_all("td")]
        if len(c) >= 9 and re.match(r"\d{2}-[A-Za-z]{3}-\d{4}", c[1]):
            rows.append(c)
    if not rows:
        return []
    day = rows[0][1]
    same = [r for r in rows if r[1] == day]
    qty = sum(num(r[5]) or 0 for r in same)
    avg = sum((num(r[5]) or 0) * (num(r[8]) or 0) for r in same) / qty if qty else None
    d = datetime.strptime(day, "%d-%b-%Y").date().isoformat()
    return [row("spices", "Cardamom, small - India e-auction (volume-weighted average)", "Cardamom", round(avg, 2), "INR", "kg", 1, d,
                "Spices Board India, daily small cardamom e-auctions", url, grade=f"Small cardamom, {len(same)} auctions, {qty:,.0f} kg sold",
                origin="IND", place="Kerala / Tamil Nadu e-auction", hs6="090831", kind="auction")] if avg else []


# ---------------------------------------------------------------- Argentina
def cac_rosario():
    url = "https://www.cac.bcr.com.ar/es/precios-de-pizarra"
    html = get(url).text
    dm = re.search(r"Precios Pizarra del d[ií]a (\d{2})/(\d{2})/(\d{4})", html)
    d = f"{dm.group(3)}-{dm.group(2)}-{dm.group(1)}" if dm else ""
    names = {"trigo": ("Wheat", "100199"), "maiz": ("Maize", "100590"), "girasol": ("Sunflower seed", "120600"), "soja": ("Soybeans", "120190"), "sorgo": ("Sorghum", "100790")}
    out = []
    for m in re.finditer(r"board board-([a-z]+)\s*\"[\s\S]*?<div class=\"price\">\s*([^<]+)</div>([\s\S]*?)</div>\s*</div>\s*</div>", html):
        key, ars, rest = m.group(1), m.group(2), m.group(3)
        if key not in names:
            continue
        usd = re.search(r"US\$</strong>\s*([\d.,]+)", rest)
        prod, hs = names[key]
        p_usd, p_ars = (num(usd.group(1)) if usd else None), num(ars)
        if p_usd:
            out.append(row("cac", f"{prod} - Rosario board price (pizarra)", prod, p_usd, "USD", "t", 1000, d,
                           "Cámara Arbitral de Cereales, Bolsa de Comercio de Rosario: precio pizarra", url, grade="Board price, delivered Rosario",
                           origin="ARG", place="Rosario, Argentina", hs6=hs, kind="spot", basis=f"ARS {p_ars:,.0f}/t on the board" if p_ars else ""))
        elif p_ars:
            out.append(row("cac", f"{prod} - Rosario board price (pizarra)", prod, p_ars, "ARS", "t", 1000, d,
                           "Cámara Arbitral de Cereales, Bolsa de Comercio de Rosario: precio pizarra", url, grade="Board price, delivered Rosario",
                           origin="ARG", place="Rosario, Argentina", hs6=hs, kind="spot"))
    return out


# ---------------------------------------------------------------- energy, steel, freight
EIA = [("ng/hist/rngwhhdD.htm", "Natural gas - Henry Hub spot", "Natural gas", "USD", "MMBtu", None, "Henry Hub, Louisiana", "271121"),
       ("pet/hist/RWTCD.htm", "Crude oil WTI - Cushing spot", "Crude oil", "USD", "bbl", None, "Cushing, Oklahoma", "270900"),
       ("pet/hist/RBRTED.htm", "Crude oil Brent - Europe spot", "Crude oil", "USD", "bbl", None, "North Sea (FOB)", "270900"),
       ("pet/hist/EER_EPD2DXL0_PF4_Y35NY_DPG.htm", "Diesel ULSD - New York Harbor spot", "Diesel", "USD", "gal", None, "New York Harbor", "271019"),
       ("pet/hist/EER_EPJK_PF4_RGC_DPG.htm", "Jet fuel - US Gulf Coast spot", "Jet fuel", "USD", "gal", None, "US Gulf Coast", "271019"),
       ("pet/hist/EER_EPLLPA_PF4_Y44MB_DPG.htm", "Propane - Mont Belvieu spot", "Propane", "USD", "gal", None, "Mont Belvieu, Texas", "271112")]


def eia():
    out = []
    for path, name, prod, ccy, unit, kg, place, hs in EIA:
        url = "https://www.eia.gov/dnav/" + path
        try:
            t = text_of(get(url).text)
        except Exception as e:  # noqa: BLE001
            log.warning("eia %s: %s", path, e)
            continue
        # weekly rows "2026 Nov- 2 to Nov- 6 2.54 2.63": the last number of the last row is the latest day
        rows = list(re.finditer(r"(\d{4}) ([A-Z][a-z]{2})-\s?(\d{1,2}) to ([A-Z][a-z]{2})-\s?(\d{1,2})((?: \d+\.\d+| NA| -(?= ))+)", t))
        if not rows:
            continue
        last = rows[-1]
        vals = [v for v in last.group(6).split() if re.match(r"\d+\.\d+$", v)]
        if not vals:
            continue
        yy, mon, start = int(last.group(1)), MONTHS[last.group(2).lower()], int(last.group(3))
        from datetime import timedelta
        d = (date(yy, mon, start) + timedelta(days=len(last.group(6).split()) - 1)).isoformat()
        out.append(row("eia", name, prod, float(vals[-1]), ccy, unit, kg, d, "US Energy Information Administration, daily spot prices", url,
                       origin="USA", place=place, hs6=hs, kind="spot", tier="T1 Official statistics"))
    return out


def steelbenchmarker():
    url = "https://steelbenchmarker.com/history.pdf"
    import pdfplumber
    with pdfplumber.open(io.BytesIO(get(url).content)) as p:
        t = "\n".join((pg.extract_text() or "") for pg in p.pages[1:3])
    dm = re.search(r"^([A-Z][a-z]+) (\d{1,2}), (\d{4})$", t, re.M)
    d = date(int(dm.group(3)), MONTHS[dm.group(1)[:3].lower()], int(dm.group(2))).isoformat() if dm else ""
    out, region = [], ""
    places = {"USA": ("USA", "USA east of the Mississippi, FOB mill", "FOB"), "Mainland China": ("CHN", "China, ex-works", "EXW"),
              "Western Europe": ("EUR", "Western Europe, ex-works", "EXW"), "World Export Market": ("", "World export, FOB port of export", "FOB")}
    for line in t.splitlines():
        rm = re.match(r"Region: (USA|Mainland China|Western Europe|World Export Market)", line)
        if rm:
            region = rm.group(1)
            continue
        pm = re.match(r"(Hot-rolled band|Cold-rolled coil|Standard plate|Rebar|#1 Heavy melting scrap|Shredded scrap|#1 Busheling scrap)\*?:\s*([\d,]+)", line)
        if pm and region:
            o, place, inc = places[region]
            scrap = "scrap" in pm.group(1).lower()
            out.append(row("steelbench", f"Steel {pm.group(1)} - {place}", "Steel scrap" if scrap else "Steel", num(pm.group(2)), "USD", "t", 1000, d,
                           "SteelBenchmarker, semi-monthly price report", url, grade=pm.group(1), origin=o, place=place + (" (delivered mill)" if scrap else ""),
                           incoterm="" if scrap else inc, hs6="720400" if scrap else "720800", kind="assessment", tier="T2 Independent benchmark"))
    return out


def drewry_wci():
    url = "https://www.drewry.co.uk/supply-chain-advisors/supply-chain-expertise/world-container-index-assessed-by-drewry"
    t = text_of(get(url).text)
    dm = re.search(r"assessment for [A-Za-z]+, (\d{1,2}) ([A-Za-z]{3})[a-z]* (\d{4})", t)
    d = date(int(dm.group(3)), MONTHS[dm.group(2).lower()], int(dm.group(1))).isoformat() if dm else ""
    out = []
    c = re.search(r"World Container Index \(WCI\)[^.]*?(?:to|at) \$([\d,]+) per 40ft", t)
    if c:
        out.append(row("drewry", "Container freight - Drewry WCI composite", "Container freight", num(c.group(1)), "USD", "40ft container", None, d,
                       "Drewry World Container Index", url, grade="Composite of 8 east-west routes", place="Global", kind="index", tier="T2 Independent benchmark"))
    for m in re.finditer(r"Shanghai to ([A-Z][a-zA-Z ]+?) (?:fell|rose|increased|decreased|declined|dropped|climbed|were unchanged|was unchanged|remained[a-z ]*)[^$]{0,40}\$([\d,]+) per 40ft", t):
        out.append(row("drewry", f"Container freight - Shanghai to {m.group(1)}", "Container freight", num(m.group(2)), "USD", "40ft container", None, d,
                       "Drewry World Container Index", url, grade=f"Spot rate Shanghai - {m.group(1)}", origin="CHN", place=f"Shanghai to {m.group(1)}",
                       kind="index", tier="T2 Independent benchmark"))
    return out


ADAPTERS = [fnc_colombia, uganda_coffee, ecx_2merkato, cepea, cai_cotton, tea_board, spices_cardamom, cac_rosario, eia, steelbenchmarker, drewry_wci]


# ---------------------------------------------------------------- build
def fx():
    for url in ("https://open.er-api.com/v6/latest/USD", "https://api.frankfurter.app/latest?from=USD"):
        try:
            j = get(url).json()
            rates = j.get("rates") or {}
            if rates:
                rates["USD"] = 1.0
                return rates, url.split("/")[2]
        except Exception as e:  # noqa: BLE001
            log.warning("fx %s: %s", url, e)
    return {"USD": 1.0}, ""


def to_usd(r, rates):
    p, ccy = r["price_native"], r["currency"]
    if p is None:
        return None
    if ccy == "USc":
        return p / 100
    rate = rates.get(ccy)
    return p / rate if rate else None


def finish(r, rates, fxsrc, today):
    usd = to_usd(r, rates)
    unit = r["unit_native"]
    per_t = usd / r["kg"] * 1000 if usd is not None and r.get("kg") else None
    ccy = "US cents" if r["currency"] == "USc" else r["currency"]
    conv = (f"{r['price_native']:,.2f} {ccy}/{unit}" + (f" / FX {fxsrc}" if r["currency"] not in ("USD", "USc") else "")
            + (f" / {r['kg']:g} kg x 1000" if per_t is not None else ""))
    kind = r["kind"]
    norm_kind = {"reference": "assessment", "auction": "spot", "index": "index"}.get(kind, kind)
    rid = "O:" + re.sub(r"[^A-Za-z0-9]+", "-", f"{r['adapter']}-{r['commodity']}")[:80]
    return {"id": rid, "hs6": r["hs6"], "commodity": r["commodity"], "price_usd": f"{usd:.6g}" if usd is not None else "",
            "unit": f"USD/{unit}", "price_type": f"{kind} ({r['source']})", "date": r["date"], "source": r["source"], "quality": r["tier"],
            "link": r["link"], "product": r["product"], "grade": r["grade"], "origin": r["origin"], "delivery_location": r["delivery_location"],
            "incoterm": r["incoterm"], "unit_canonical": f"USD/{unit}", "price_usd_t": f"{per_t:.6g}" if per_t is not None else "", "conversion": conv,
            "price_type_norm": norm_kind, "physical": "false" if "freight" in r["product"].lower() else "true",
            "timestamp": r["date"], "source_tier": r["tier"].split()[0], "basis_note": r["basis"] or f"{kind} price as published",
            "price_native": r["price_native"], "currency": ccy, "unit_native": unit, "adapter": r["adapter"], "fetched": today}


def main():
    today = date.today().isoformat()
    prev = {}
    if OUT.exists():
        for r in csv.DictReader(open(OUT, encoding="utf-8")):
            prev.setdefault(r["adapter"], []).append(r)
    rates, fxsrc = fx()
    rows, report = [], {}
    for a in ADAPTERS:
        name = a.__name__
        try:
            got = [finish(r, rates, fxsrc, today) for r in a() if r.get("price_native") is not None]
            got = [g for g in got if g["price_usd"]]
        except Exception as e:  # noqa: BLE001
            log.warning("origin prices %s failed: %s", name, str(e)[:200])
            got = []
        key = got[0]["adapter"] if got else None
        if got:
            rows += got
            report[name] = len(got)
        else:  # keep the last good rows of this source, still dated as published
            old = [r for k, v in prev.items() for r in v if k == {"fnc_colombia": "fnc", "uganda_coffee": "uganda", "ecx_2merkato": "ecx", "cepea": "cepea",
                   "cai_cotton": "cai", "tea_board": "teaboard", "spices_cardamom": "spices", "cac_rosario": "cac", "eia": "eia",
                   "steelbenchmarker": "steelbench", "drewry_wci": "drewry"}.get(name)]
            rows += old
            report[name] = f"0 (kept {len(old)} previous)"
        _ = key
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print("origin prices:", json.dumps(report), f"total {len(rows)}")
    return rows


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
