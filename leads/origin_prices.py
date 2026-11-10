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
  MPOB                  Malaysian crude palm oil (MYR/t), daily
  DTN                   US retail fertilizer: DAP, MAP, potash, urea, 10-34-0, anhydrous, UAN28/32 (USD per short ton), weekly
  Nairobi Coffee Exch.  Kenya auction average and top lot (USD per 50 kg bag), weekly, as reported by Kilimo News
  Forbes & Walker       Colombo tea auction averages by elevation (LKR/kg), weekly
  AHDB / EU MMO         EU wholesale butter, SMP, WMP, whey, cheese (EUR/t), monthly
  Energy-Charts         German/Luxembourg day-ahead power, daily base (EUR/MWh), daily
  giacaphe.com           Vietnam domestic robusta, Central Highlands average (VND/kg), daily
  EU Weekly Oil Bulletin  gasoline, diesel, heating oil, fuel oil before taxes, per EU country (EUR per 1000 l or t), weekly

Run: python -m leads.origin_prices   (writes data/leads/origin_prices.csv; commodity_norm merges it)."""
import csv
import html
import io
import json
import logging
import os
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
       ("pet/hist/EER_EPD2DXL0_PF4_Y35NY_DPGD.htm", "Diesel ULSD - New York Harbor spot", "Diesel", "USD", "gal", None, "New York Harbor", "271019"),
       ("pet/hist/EER_EPJK_PF4_RGC_DPGD.htm", "Jet fuel - US Gulf Coast spot", "Jet fuel", "USD", "gal", None, "US Gulf Coast", "271019"),
       ("pet/hist/EER_EPLLPA_PF4_Y44MB_DPGD.htm", "Propane - Mont Belvieu spot", "Propane", "USD", "gal", None, "Mont Belvieu, Texas", "271112")]


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
        toks = last.group(6).split()
        idx = [i for i, v in enumerate(toks) if re.match(r"\d+\.\d+$", v)]
        if not idx:
            continue
        vals = [toks[idx[-1]]]
        yy, mon, start = int(last.group(1)), MONTHS[last.group(2).lower()], int(last.group(3))
        from datetime import timedelta
        d = (date(yy, mon, start) + timedelta(days=idx[-1])).isoformat()  # the day of the last published value, not of a trailing "-"
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


# ---------------------------------------------------------------- batch 2 (Nov 2026)
def parse_mpob(h):
    m = re.search(r"CRUDE PALM OIL-(\d{4})", h)
    cats = re.findall(r"'([A-Z][a-z]{2}) (\d{2})'", h.split("categories", 1)[1]) if "categories" in h else []
    data = re.search(r"data:\s*\[([^\]]+)\]", h.split("series", 1)[1]) if "series" in h else None
    vals = [float(v) for v in re.findall(r"[\d.]+", data.group(1))] if data else []
    if not (m and cats and vals and len(cats) == len(vals)):
        return None
    mon, day = cats[-1]
    return vals[-1], date(int(m.group(1)), MONTHS[mon.lower()], int(day)).isoformat()


def mpob_cpo():
    url = "https://bepi.mpob.gov.my/admin2/chart_cpomsia_mini.php"
    got = parse_mpob(get(url).text)
    if not got:
        return []
    return [row("mpob", "Palm oil, crude (CPO) - Malaysia daily", "Palm oil", got[0], "MYR", "t", 1000, got[1],
                "Malaysian Palm Oil Board, daily CPO price", url, grade="Crude palm oil", origin="MYS", place="Malaysia, local delivered",
                hs6="151110", kind="spot", tier="T1 Official statistics", basis="MPOB daily average price of crude palm oil traded locally")]


DTN_FERT = {"DAP": ("Diammonium phosphate (DAP)", "310530"), "MAP": ("Monoammonium phosphate (MAP)", "310540"),
            "POTASH": ("Potash (MOP)", "310420"), "UREA": ("Urea", "310210"), "10-34-0": ("Ammonium polyphosphate 10-34-0", "310559"),
            "ANHYD": ("Anhydrous ammonia", "281410"), "UAN28": ("UAN 28% solution", "310280"), "UAN32": ("UAN 32% solution", "310280")}


def parse_dtn(t):
    out = []
    for blk in re.finditer(r"(?:Dry|Liquid) Date Range ((?:[A-Z0-9-]+ ){4})(.*?)(?=Liquid Date Range|Todd|\(c\)|$)", t):
        heads = blk.group(1).split()
        rows_ = re.findall(r"([A-Z][a-z]{2}) (\d{1,2})-(?:([A-Z][a-z]{2}) )?(\d{1,2}) (\d{4}) (\d+) (\d+) (\d+) (\d+)", blk.group(2))
        if not rows_:
            continue
        m1, _d1, m2, d2, yy, *vals = rows_[-1]
        d = date(int(yy), MONTHS[(m2 or m1).lower()], int(d2)).isoformat()
        out += [(h, float(v), d) for h, v in zip(heads, vals)]
    return out


def dtn_fertilizer():
    lst = get("https://www.dtnpf.com/agriculture/web/ag/crops").text
    arts = sorted(set(re.findall(r"/agriculture/web/ag/crops/article/(\d{4}/\d{2}/\d{2})/([a-z0-9-]*fertilizer[a-z0-9-]*)", lst)), reverse=True)
    out = []
    for day, slug in arts[:3]:
        url = f"https://www.dtnpf.com/agriculture/web/ag/crops/article/{day}/{slug}"
        got = parse_dtn(text_of(get(url).text))
        if got:
            for h, v, d in got:
                name, hs = DTN_FERT.get(h, (h, "3105"))
                out.append(row("dtn", f"Fertilizer {name} - US retail average", "Fertilizer", v, "USD", "short ton", 907.185, d,
                               "DTN retail fertilizer trends (weekly survey of US retailers)", url, grade=name, origin="USA",
                               place="USA, retail (national average)", hs6=hs, kind="spot", tier="T2 Independent benchmark",
                               basis="average retail bid price reported by about 300 US agricultural retailers for the week"))
            break
    return out


def parse_nce(t):
    a = re.search(r"average of US\$([\d,.]+) per 50 ?kg bag", t)
    dm = re.search(r"\bon (?:[A-Z][a-z]+day), (\d{1,2}) ([A-Z][a-z]+)", t)
    ym = re.search(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, (\d{4})", t)
    sale = re.search(r"Sale (\d+)", t)
    if not (a and dm and ym):
        return None
    d = date(int(ym.group(1)), MONTHS[dm.group(2)[:3].lower()], int(dm.group(1)))
    top = re.search(r"highest price went to [^.]*?(AA|AB|PB|C|E|TT|T)\b[^.]*\.[^.]*?at US\$([\d,.]+)", t)
    return {"avg": num(a.group(1)), "date": d.isoformat(), "sale": sale.group(1) if sale else "",
            "top": (top.group(1), num(top.group(2))) if top else None}


def kilimo_nce():
    lst = get("https://kilimonews.co.ke/?s=nairobi+coffee+exchange").text
    links = [u for u in dict.fromkeys(re.findall(r"https://kilimonews\.co\.ke/agricultural-products/[a-z0-9-]+/", lst))
             if "sale-" in u and "coffee" in u]
    for url in links[:3]:
        p = parse_nce(text_of(get(url).text))
        if not p:
            continue
        src = f"Nairobi Coffee Exchange auction results, sale {p['sale']} (as reported by Kilimo News)"
        out = [row("nce", "Coffee Arabica - Kenya NCE auction average", "Coffee Arabica", p["avg"], "USD", "50 kg bag", 50, p["date"], src, url,
                   grade="All grades, sale average (clean coffee)", origin="KEN", place="Nairobi Coffee Exchange", hs6="090111", kind="auction",
                   tier="T2 Primary physical (press report)", basis="volume-weighted average of the weekly auction")]
        if p["top"]:
            out.append(row("nce", f"Coffee Arabica - Kenya NCE top lot ({p['top'][0]})", "Coffee Arabica", p["top"][1], "USD", "50 kg bag", 50,
                           p["date"], src, url, grade=f"{p['top'][0]}, highest-priced lot of the sale", origin="KEN", place="Nairobi Coffee Exchange",
                           hs6="090111", kind="auction", tier="T2 Primary physical (press report)", basis="single top lot, not an average"))
        return out
    return []


def parse_colombo(t):
    last = None
    for m in re.finditer(r"^(\d{2})-([A-Z]{3})[A-Z]*-(\d{4}) [\d,]+ [\d,]+ [\d,]+ [\d,]+ ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)$", t, re.M):
        last = m
    if not last:
        return None
    dd, mon, yy, hi, med, lo, tot = last.groups()
    yy = min(int(yy), date.today().year)  # the sheet has a typo year (2027) on one July row
    return date(yy, MONTHS[mon.lower()], int(dd)).isoformat(), {"High grown": float(hi), "Medium grown": float(med), "Low grown": float(lo), "All elevations": float(tot)}


def forbes_colombo():
    page = get("https://www.forbestea.com/statistics-weekly-tea-auction-quantities-&-averages").text
    yr = date.today().year
    pdfs = re.findall(r"href=\"([^\"]*Weekly Tea Auction Quantities[^\"]*?(\d{4})[^\"]*\.pdf)\"", page)
    pdfs = sorted([(int(y), u) for u, y in pdfs if int(y) <= yr], reverse=True)
    if not pdfs:
        return []
    url = urljoin("https://www.forbestea.com/", pdfs[0][1].replace("&amp;", "&")).replace(" ", "%20")
    got = parse_colombo(pdf_text(get(url).content))
    if not got:
        return []
    d, vals = got
    return [row("forbes", f"Tea - Sri Lanka Colombo auction, {k.lower()}", "Tea", v, "LKR", "kg", 1, d,
                "Forbes & Walker Tea Brokers, weekly Colombo tea auction averages", url, grade=f"Ceylon tea, {k.lower()}", origin="LKA",
                place="Colombo Tea Auction", hs6="090240", kind="auction", tier="T2 Primary physical (broker)", basis="weekly auction average, all teas sold")
            for k, v in vals.items()]


def parse_ahdb(t):
    m = re.search(r"Price \(\S+/tonne\) ([A-Z][a-z]{2})-(\d{4})", t)
    if not m:
        return None
    d = date(int(m.group(2)), MONTHS[m.group(1).lower()], 1).isoformat()
    out = {}
    for name in ("Butter", "SMP", "WMP", "Whey", "Average cheese"):
        v = re.search(rf"{name}\*? ([\d,]+) [\d,]+ ", t[m.end():m.end() + 600])
        if v:
            out[name] = num(v.group(1))
    return d, out


def ahdb_dairy():
    url = "https://ahdb.org.uk/dairy/eu-wholesale-prices"
    got = parse_ahdb(text_of(get(url).text))
    if not got:
        return []
    d, vals = got
    meta = {"Butter": ("Butter", "040510"), "SMP": ("Skimmed milk powder (SMP)", "040210"), "WMP": ("Whole milk powder (WMP)", "040221"),
            "Whey": ("Whey powder", "040410"), "Average cheese": ("Cheese (avg Emmental, Gouda, Edam, Cheddar)", "040690")}
    return [row("ahdb", f"Dairy {meta[k][0]} - EU wholesale", "Dairy products", v, "EUR", "t", 1000, d,
                "AHDB from the EU Milk Market Observatory, EU (ex UK) wholesale prices", url, grade=meta[k][0], origin="EU", place="EU (ex UK), wholesale",
                hs6=meta[k][1], kind="assessment", tier="T1 Official statistics", basis="monthly average wholesale price (the month is the date)")
            for k, v in vals.items()]


def parse_energy_charts(j):
    from zoneinfo import ZoneInfo
    ts, pr = j.get("unix_seconds") or [], j.get("price") or []
    pts = [(datetime.fromtimestamp(t, ZoneInfo("Europe/Berlin")).date(), p) for t, p in zip(ts, pr) if p is not None]
    if not pts:
        return None
    by = {}
    for d, p in pts:
        by.setdefault(d, []).append(p)
    full = [d for d, v in by.items() if len(v) >= 23]
    if not full:
        return None
    d = max(full)
    return round(sum(by[d]) / len(by[d]), 2), d.isoformat()


def energy_charts():
    url = "https://api.energy-charts.info/price?bzn=DE-LU"
    got = parse_energy_charts(get(url).json())
    if not got:
        return []
    return [row("echarts", "Electricity - Germany/Luxembourg day-ahead (daily base)", "Electricity", got[0], "EUR", "MWh", None, got[1],
                "Energy-Charts (Fraunhofer ISE), day-ahead auction, data Bundesnetzagentur/SMARD (CC BY 4.0)", url, grade="Base load, daily average",
                origin="DEU", place="DE-LU bidding zone", hs6="271600", kind="spot", tier="T1 Official statistics",
                basis="simple average of the day's day-ahead prices")]


EU_ISO = {"AT": "AUT", "BE": "BEL", "BG": "BGR", "CY": "CYP", "CZ": "CZE", "DE": "DEU", "DK": "DNK", "EE": "EST", "ES": "ESP", "FI": "FIN",
          "FR": "FRA", "GR": "GRC", "HR": "HRV", "HU": "HUN", "IE": "IRL", "IT": "ITA", "LT": "LTU", "LU": "LUX", "LV": "LVA", "MT": "MLT",
          "NL": "NLD", "PL": "POL", "PT": "PRT", "RO": "ROU", "SE": "SWE", "SI": "SVN", "SK": "SVK", "EU": "EU"}
WOB = {"euro95": ("Gasoline Euro-super 95", "1000 l", None, "271012"), "diesel": ("Diesel (automotive gas oil)", "1000 l", None, "271019"),
       "heating_oil": ("Heating gas oil", "1000 l", None, "271019"), "fuel_oil_1": ("Fuel oil, sulphur up to 1%", "t", 1000, "271019")}


def parse_wob(content):
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb["Prices wo taxes"]
    head, latest = None, None
    for r in ws.iter_rows(max_row=8, values_only=True):
        if head is None:
            head = r
        elif isinstance(r[0], datetime):
            latest = r
            break
    if not (head and latest):
        return None
    out = []
    for i, h in enumerate(head):
        m = re.match(r"([A-Z]{2})_price_wo_tax_(euro95|diesel|heating_oil|fuel_oil_1)$", str(h or ""))
        if m and m.group(1) in EU_ISO and isinstance(latest[i], (int, float)):
            out.append((m.group(1), m.group(2), float(latest[i])))
    return latest[0].date().isoformat(), out


def eu_oil_bulletin():
    page = get("https://energy.ec.europa.eu/data-and-analysis/weekly-oil-bulletin_en").text
    m = re.search(r"href=\"([^\"]*Prices_History[^\"]*\.xlsx)\"", page)
    url = urljoin("https://energy.ec.europa.eu/", m.group(1) if m else
                  "/document/download/906e60ca-8b6a-44e7-8589-652854d2fd3f_en?filename=Weekly_Oil_Bulletin_Prices_History_maticni_4web.xlsx")
    got = parse_wob(get(url).content)
    if not got:
        return []
    d, vals = got
    out = []
    for cc, key, v in vals:
        name, unit, kg, hs = WOB[key]
        where = "EU-27 weighted average" if cc == "EU" else cc
        out.append(row("wob", f"{name} - {where}, before taxes", "Refined fuels", v, "EUR", unit, kg, d,
                       "European Commission, Weekly Oil Bulletin (consumer prices net of duties and taxes)", url, grade=name, origin=EU_ISO[cc],
                       place=f"{where}, consumer price net of taxes", hs6=hs, kind="spot", tier="T1 Official statistics",
                       basis="weekly national average consumer price, excluding duties and taxes"))
    return out


def parse_giacaphe(t):
    m = re.search(r"Giá cà phê hôm nay ngày (\d{2})/(\d{2})/(\d{4}).{0,40}?Trung bình ([\d,.]+) đ/kg", t)
    if not m:
        return None
    dd, mm, yy, v = m.groups()
    return num(v.replace(".", ",")), f"{yy}-{mm}-{dd}"


def parse_giacaphe_table(html):
    """The site prints each province price through a CSS class (span.cls::after { content:'85,000' }); this reads exactly
    the value a visitor sees: the four coffee provinces (recognised by their page address), averaged. The date is the one in
    the page title or the 'Cập nhật' line."""
    css = dict(re.findall(r"\.(\w+)::after\s*\{\s*content:\s*'([^']*)'", html))
    vals = []
    for slug, cls in re.findall(r"<a href=\"https://giacaphe\.com/gia-ca-phe-(dak-lak|lam-dong|gia-lai|dak-nong)/\"[^>]*>[^<]*</a>\s*</td>\s*<td><span class=['\"](\w+) \w+['\"]></span>", html):
        if cls in css:
            v = num(css[cls].replace(",", ""))
            if v and 20000 < v < 400000:   # VND per kg sanity range for green coffee
                vals.append(v)
    d = re.search(r"Cập nhật:\s*(\d{2})/(\d{2})/(\d{4})", html) or re.search(r"<title>[^<]*?(\d{2})/(\d{2})/(\d{4})", html)
    if len(vals) < 3 or not d:
        return None
    return sum(vals) / len(vals), f"{d.group(3)}-{d.group(2)}-{d.group(1)}"


def vietnam_coffee():
    url = "https://giacaphe.com/gia-ca-phe-noi-dia/"
    html = get(url).content.decode("utf-8", "replace")   # the site is UTF-8; the default guess garbles the Vietnamese letters
    got = parse_giacaphe(text_of(html)) or parse_giacaphe_table(html)
    if not got:
        return []
    return [row("vncoffee", "Coffee Robusta - Vietnam Central Highlands farm-gate average", "Coffee Robusta", got[0], "VND", "kg", 1, got[1],
                "giacaphe.com daily domestic coffee prices (Dak Lak, Lam Dong, Gia Lai, Dak Nong average)", url, grade="Robusta green coffee, domestic",
                origin="VNM", place="Vietnam Central Highlands, at the buying agent", hs6="090111", kind="spot", tier="T3 Trade press",
                basis="average of the provinces' daily buying prices, as published by a trade site")]


def exa_ethiopia_coffee():
    """Ethiopian coffee prices found by Exa deep search, kept only with a dated source page; runs only when EXA_API_KEY exists.
    Marked as automated research (T4), never as exchange data. Rows without a date, older than 30 days or without a citation are dropped."""
    key = os.environ.get("EXA_API_KEY", "")
    if not key:
        return []
    if OUT.exists() and any(r["adapter"] == "exa_eth" and r["fetched"] == date.today().isoformat() for r in csv.DictReader(open(OUT, encoding="utf-8"))):
        return []   # at most one paid search per day; the rows of today are kept as they are
    body = {"query": "Current Ethiopian coffee prices (ECX and export) by grade, with the date of each price",
            "additionalQueries": ["Ethiopia Commodity Exchange coffee price today birr per feresula", "Ethiopian coffee export price per kg ECTA", "Ethiopia washed Arabica FOB price"],
            "type": "deep", "systemPrompt": "Prefer dated market reports and official sources. Exclude undated pages. Never guess a price or a date.",
            "outputSchema": {"type": "object", "required": ["prices"], "properties": {"prices": {"type": "array", "items": {"type": "object",
                "required": ["grade", "price", "currency", "unit", "asOfDate"], "properties": {"grade": {"type": "string"}, "price": {"type": "string"},
                "currency": {"type": "string"}, "unit": {"type": "string"}, "asOfDate": {"type": "string", "description": "YYYY-MM-DD"}}}}}}}
    r = requests.post("https://api.exa.ai/search", json=body, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, timeout=180)
    r.raise_for_status()
    out = (r.json().get("output") or {})
    items = ((out.get("content") or {}).get("prices")) or []
    cites = {}
    for g in out.get("grounding") or []:
        cs = g.get("citations") or []
        if cs:
            cites[g.get("field", "")] = cs[0].get("url", "")
    rows = []
    for i, it in enumerate(items):
        try:
            d = date.fromisoformat(str(it.get("asOfDate", ""))[:10])
        except ValueError:
            continue
        price = num(str(it.get("price", "")).replace(",", ""))
        url = next((u for f, u in cites.items() if f.startswith(f"prices[{i}]")), "")
        ccy, unit = str(it.get("currency", "")).upper()[:3], str(it.get("unit", "")).lower()
        kg = 1 if "kg" in unit and "100" not in unit else 17 if "feresula" in unit else 100 if "quintal" in unit else None
        if price is None or not url or (date.today() - d).days > 30 or not kg or ccy not in ("USD", "ETB"):
            continue
        rows.append(row("exa_eth", f"Coffee - Ethiopia ({it.get('grade', '')})", "Coffee Arabica", price, ccy, unit, kg, d.isoformat(),
                        "Exa deep search over dated public pages (automated research, cited)", url, grade=str(it.get("grade", "")), origin="ETH", place="Ethiopia",
                        hs6="090111", kind="reference", tier="T4 Automated research", basis="found and cited by an automated search; verify against the cited page"))
    return rows


PINK = {  # World Bank Pink Sheet column -> (commodity label, hs6)
    "Cocoa": ("Cocoa beans", "180100"), "Coffee, Arabica": ("Coffee Arabica", "090111"), "Coffee, Robusta": ("Coffee Robusta", "090111"),
    "Tea, avg 3 auctions": ("Tea", "090240"), "Palm oil": ("Palm oil", "151110"), "Soybeans": ("Soybeans", "120190"), "Soybean oil": ("Soybean oil", "150710"),
    "Maize": ("Maize", "100590"), "Rice, Thai 5%": ("Rice 5% broken (Thai)", "100630"), "Rice, Viet Namese 5%": ("Rice 5% broken (Vietnam)", "100630"),
    "Wheat, US HRW": ("Wheat (US HRW)", "100199"), "Sugar, world": ("Sugar (world)", "170199"), "Cotton, A Index": ("Cotton (A Index)", "520100"),
    "Rubber, RSS3": ("Natural rubber RSS3", "400121"), "DAP": ("DAP fertilizer", "310530"), "Urea": ("Urea fertilizer", "310210"),
    "Potassium chloride": ("Potash (KCl)", "310420"), "Phosphate rock": ("Phosphate rock", "251010"), "Aluminum": ("Aluminium", "760110"),
    "Copper": ("Copper", "740311"), "Nickel": ("Nickel", "750210"), "Zinc": ("Zinc", "790111"), "Tin": ("Tin", "800110"), "Lead": ("Lead", "780110"),
    "Iron ore, cfr spot": ("Iron ore (62% Fe, CFR China)", "260111"), "Coal, Australian": ("Thermal coal (Australia)", "270112"),
}


def worldbank_pink():
    """World Bank Pink Sheet, monthly nominal USD prices (official, T1): the latest month of each listed commodity.
    The file's address changes every month, so it is found on the World Bank page first."""
    import pandas as pd
    page = get("https://www.worldbank.org/en/research/commodity-markets").text
    m = re.search(r'href="(https://thedocs\.worldbank\.org/[^"]*CMO-Historical-Data-Monthly\.xlsx)"', page)
    if not m:
        return []
    df = pd.read_excel(io.BytesIO(get(m.group(1)).content), sheet_name="Monthly Prices", header=None)
    names = [str(c).replace("*", "").strip() for c in df.iloc[4].tolist()]
    units = [str(c).strip() for c in df.iloc[5].tolist()]
    body = df.iloc[6:]
    body = body[body[0].astype(str).str.match(r"^\d{4}M\d{2}$")]
    out = []
    for i, nm in enumerate(names):
        if nm not in PINK:
            continue
        col = pd.to_numeric(body[i], errors="coerce").dropna()
        if col.empty:
            continue
        period = str(body.loc[col.index[-1], 0])
        label, hs = PINK[nm]
        kg = 1 if "$/kg" in units[i] else 1000 if "$/mt" in units[i] else None
        if kg is None:
            continue
        out.append(row("wbpink", f"{label} - World Bank Pink Sheet monthly", label, float(col.iloc[-1]), "USD", "kg" if kg == 1 else "t", kg,
                       f"{period[:4]}-{period[5:7]}-01", "World Bank Commodity Price Data (Pink Sheet), monthly nominal USD",
                       "https://www.worldbank.org/en/research/commodity-markets", grade=nm, origin="", place="international reference price", hs6=hs,
                       kind="assessment", tier="T1 Official statistics", basis="monthly average international reference price (the month is the date)"))
    return out


def royal_ethiopia():
    """Ethiopian coffees on a US green-coffee importer's public spot offer list (Royal Coffee, a Shopify storefront whose
    robots.txt allows product and collection pages): each lot with its region and grade (Sidama, Yirgacheffe, Guji ...),
    the price per pack and the pack weight, so USD/kg is exact. It is a landed US warehouse offer (freight, import cost
    and the importer's margin included), not an origin FOB price: shown as an importer offer, never as exchange data.
    The Ethiopian exchange and authority sites do not answer from outside the country."""
    out, lots = [], {}
    for page in range(1, 6):
        r = get(f"https://royalcoffee.com/collections/all-coffees/products.json?limit=250&page={page}")
        prods = (r.json() or {}).get("products") or []
        if not prods:
            break
        for p in prods:
            tags = p.get("tags") if isinstance(p.get("tags"), list) else str(p.get("tags") or "").split(",")
            title = re.sub(r"\s+", " ", str(p.get("title") or "")).strip()
            if not re.search(r"ethiopia", f"{title} {' '.join(tags)}", re.I) or re.search(r"roasted|sample|gift|merch", title, re.I):
                continue
            best = None
            for v in p.get("variants") or []:
                price, grams = num(str(v.get("price") or "")), v.get("grams") or 0
                if not price or grams < 2000 or v.get("available") is False:   # trade packs only (a 10 kg box or a 60 kg bag)
                    continue
                per_kg = price / (grams / 1000)
                if 2 < per_kg < 60 and (best is None or grams > best[1]):
                    best = (per_kg, grams, str(v.get("title") or ""))
            if not best:
                continue
            # one row per region and grade ("Ethiopia Sidama 4 Natural"): its lots differ only by lot number, bag and arrival
            name = re.sub(r"\s+", " ", title.split(" - ")[0]).strip().title().replace("Organic", "organic")
            g = lots.setdefault(name, {"prices": [], "handle": p.get("handle", ""), "date": str(p.get("updated_at") or p.get("published_at") or "")[:10], "spot": 0})
            g["prices"].append(best[0]); g["spot"] += 1 if "SPOT" in title.upper() else 0
            g["date"] = max(g["date"], str(p.get("updated_at") or "")[:10])
    for name, g in lots.items():
        ps = sorted(g["prices"]); mid = ps[len(ps) // 2]
        out.append(row("royal_eth", f"Coffee - {name[:80]}", "Coffee Arabica", round(mid, 3), "USD", "kg", 1, g["date"],
                       "Royal Coffee (US importer) public spot offer list", f"https://royalcoffee.com/products/{g['handle']}",
                       grade=f"{name[:70]}: {len(ps)} lots, {ps[0]:.2f}-{ps[-1]:.2f} USD/kg, {g['spot']} in stock (trade packs)", origin="ETH",
                       place="US importer warehouse", hs6="090111", kind="offer", tier="T3 Importer offer list",
                       basis="median of the importer's published offers for this grade, landed in its warehouse: freight, import cost and margin included; not an FOB origin price"))
    return sorted(out, key=lambda x: x["commodity"])[:60]


# ---------------------------------------------------------------- official origin layers (all commodities)
# One list of traded commodities with their customs code; three official layers price each of them at the origin:
#   comtrade_fob   what the origin's own customs recorded on export: value / weight = FOB at the origin (UN Comtrade, monthly)
#   comext_cif     what EU customs recorded on import from that origin: CIF at the EU border (Eurostat Comext, monthly)
#   wfp_local      what the commodity costs on markets inside the origin country (WFP market monitoring, monthly)
# A unit value is an average over every grade shipped that month, so it is the level of the market, not a quote for
# one grade; each row states the tonnes behind it, and thin flows (under 25 t) are left out.
TRADED = [("Coffee Arabica", "Coffee, green", "090111"), ("Rice", "Rice, milled", "100630"), ("Sesame seed", "Sesame seed", "120740"), ("Cocoa beans", "Cocoa beans", "180100"),
          ("Tea", "Black tea, bulk", "090240"), ("Sugar", "Raw cane sugar", "170114"), ("Sugar", "Refined sugar", "170199"), ("Wheat", "Wheat", "100199"), ("Maize", "Maize", "100590"),
          ("Soybeans", "Soybeans", "120190"), ("Palm oil", "Crude palm oil", "151110"), ("Sunflower oil", "Crude sunflower oil", "151211"), ("Cashew", "Cashew in shell", "080131"),
          ("Cashew", "Cashew kernels", "080132"), ("Pepper", "Black pepper", "090411"), ("Spices", "Cardamom", "090831"), ("Spices", "Cloves", "090710"), ("Spices", "Vanilla", "090510"),
          ("Spices", "Ginger", "091011"), ("Cotton", "Cotton lint", "520100"), ("Natural rubber", "Natural rubber TSNR", "400122"), ("Urea", "Urea", "310210"), ("Fertilizer", "DAP", "310530"),
          ("Fertilizer", "Potash (KCl)", "310420"), ("Sulphur", "Sulphur", "250300"), ("Cement", "Portland cement", "252329"), ("Steel", "Rebar", "721420"), ("Copper", "Copper cathodes", "740311"),
          ("Aluminium", "Aluminium, unwrought", "760110"), ("Fish", "Frozen skipjack tuna", "030343"), ("Fish", "Frozen shrimp", "030617"), ("Meat", "Frozen boneless beef", "020230"),
          ("Meat", "Frozen chicken cuts", "020714"), ("Dairy products", "Whole milk powder", "040221"), ("Pulses", "Lentils", "071340"), ("Pulses", "Chickpeas", "071320"),
          ("Nuts", "Almonds, shelled", "080212"), ("Nuts", "Groundnuts, shelled", "120242"), ("Fruit", "Dates", "080410"), ("Fruit", "Avocados", "080440"), ("Gum arabic", "Gum arabic", "130120"),
          ("Flowers", "Cut roses", "060311"), ("Honey", "Natural honey", "040900"), ("Cocoa products", "Cocoa butter", "180400")]
ORIGIN_REPORTERS = {"BRA": 76, "COL": 170, "VNM": 704, "IDN": 360, "IND": 356, "THA": 764, "PAK": 586, "KEN": 404, "UGA": 800, "TZA": 834, "ETH": 231, "RWA": 646, "CIV": 384,
                    "GHA": 288, "NGA": 566, "ECU": 218, "PER": 604, "GTM": 320, "HND": 340, "MEX": 484, "ARG": 32, "URY": 858, "PRY": 600, "ZAF": 710, "EGY": 818, "MAR": 504,
                    "TUR": 792, "UKR": 804, "KAZ": 398, "MYS": 458, "PHL": 608, "LKA": 144, "MMR": 104, "KHM": 116, "AUS": 36, "NZL": 554, "CAN": 124, "CHL": 152, "SDN": 729,
                    "BFA": 854, "MLI": 466, "SEN": 686, "CMR": 120, "MOZ": 508, "MDG": 450, "ZMB": 894, "BEN": 204}


def _last_months(n, lag=2):
    y, m = date.today().year, date.today().month
    out = []
    for i in range(lag, lag + n):
        mm, yy = m - i, y
        while mm <= 0:
            mm += 12; yy -= 1
        out.append((yy, mm))
    return out


def comtrade_fob():
    """FOB at the origin from the origin's own export declarations (UN Comtrade public preview, monthly; no key).
    One request per origin for the last months and every listed code; the API allows about one request a second."""
    import time as _t
    label = {hs: (c, n) for c, n, hs in TRADED}
    codes = list(label)
    chunks = [codes[i:i + 22] for i in range(0, len(codes), 22)]   # the preview takes one period and about 22 codes a call
    months = [f"{y}{m:02d}" for y, m in _last_months(3, lag=3)]
    out, skipped = [], 0
    t0 = _t.time()

    def call(rep, period, chunk):
        for attempt in range(3):
            r = requests.get("https://comtradeapi.un.org/public/v1/preview/C/M/HS", params={"reporterCode": rep, "cmdCode": ",".join(chunk), "flowCode": "X", "period": period,
                             "partnerCode": 0, "customsCode": "C00", "motCode": 0}, headers=UA, timeout=60)
            if r.status_code == 429:
                _t.sleep(3 + attempt * 3); continue
            _t.sleep(1.3)
            return r.json().get("data", []) if r.status_code == 200 else []
        return []

    # a run reaches about 20 origins inside its time: the origins read longest ago go first, and main() keeps the
    # rows of the ones not reached this time
    seen_at = {}
    if OUT.exists():
        for r_ in csv.DictReader(open(OUT, encoding="utf-8")):
            if r_.get("adapter") == "ct_fob":
                seen_at[r_.get("origin", "")] = max(seen_at.get(r_.get("origin", ""), ""), r_.get("fetched", ""))
    for iso, rep in sorted(ORIGIN_REPORTERS.items(), key=lambda x: seen_at.get(x[0], "")):
        if _t.time() - t0 > 600:
            log.info("comtrade fob: time budget reached at %s", iso); break
        data = []
        try:
            for period in months:   # the latest month the origin has reported
                got = [d for ch in chunks for d in call(rep, period, ch)]
                if got:
                    data = got; break
        except Exception as e:  # noqa: BLE001
            log.warning("comtrade fob %s: %s", iso, str(e)[:100])
        agg = {}
        for d in data:
            if d.get("partnerCode") not in (0, None) or d.get("partner2Code") not in (0, None):
                continue
            kg = d.get("netWgt") or (d.get("qty") if d.get("qtyUnitCode") == 8 else 0) or 0
            v = d.get("primaryValue") or d.get("fobvalue") or 0
            if kg <= 0 or v <= 0:
                skipped += 1; continue
            a = agg.setdefault(str(d.get("cmdCode")), {"v": 0, "kg": 0, "p": []})
            a["v"] += v; a["kg"] += kg; a["p"].append(str(d.get("period")))
        for hs, a in agg.items():
            uv = a["v"] / a["kg"]
            if hs not in label or a["kg"] < 25000 or not (0.02 < uv < 500):
                continue
            last = max(a["p"])
            out.append(row("ct_fob", f"{label[hs][1]} - FOB {iso} (origin customs, exports)", label[hs][0], round(uv, 4), "USD", "kg", 1, f"{last[:4]}-{last[4:6]}-01",
                           "UN Comtrade: the origin country's own export declarations", "https://comtradeplus.un.org/", grade=f"{label[hs][1]}, all grades: {a['kg'] / 1000:,.0f} t in {len(set(a['p']))} months",
                           origin=iso, place=f"{iso}, FOB", incoterm="FOB", hs6=hs, kind="index", tier="T1 Official statistics",
                           basis="export value divided by net weight over the months stated: the average of every grade shipped, not a quote for one grade"))
    log.info("comtrade fob: %d rows, %d records without weight", len(out), skipped)
    return out


def _jsonstat(j):
    """Eurostat JSON-stat -> list of ({dimension: category id}, value)."""
    ids, size = j.get("id") or [], j.get("size") or []
    cats = [sorted(j["dimension"][d]["category"]["index"].items(), key=lambda x: x[1]) for d in ids]
    out = []
    for k, v in (j.get("value") or {}).items():
        n, pos = int(k), []
        for sz in reversed(size):
            pos.append(n % sz); n //= sz
        pos.reverse()
        out.append(({d: cats[i][pos[i]][0] for i, d in enumerate(ids)}, v))
    return out


def comext_cif():
    """CIF at the EU border by origin, from EU customs (Eurostat Comext, monthly, no key): the price the EU actually
    paid each origin, which bounds the origin's FOB from above by the sea freight."""
    try:
        import pycountry
        iso3 = {c.alpha_2: c.alpha_3 for c in pycountry.countries}
    except Exception:  # noqa: BLE001
        iso3 = {}
    out = []
    times = "&".join(f"time={y}-{m:02d}" for y, m in _last_months(3, lag=3))   # Comext publishes about ten weeks after the month
    for commodity, name, hs in TRADED:
        try:
            j = get("https://ec.europa.eu/eurostat/api/comext/dissemination/statistics/1.0/data/ds-045409?freq=M&reporter=EU27_2020&flow=1"
                    f"&product={hs}&indicators=VALUE_IN_EUROS&indicators=QUANTITY_IN_100KG&{times}&format=JSON").json()
        except Exception as e:  # noqa: BLE001
            log.warning("comext %s: %s", hs, str(e)[:100]); continue
        agg, months = {}, set()
        for dims, v in _jsonstat(j):
            p = dims.get("partner", "")
            if len(p) != 2 or not v:
                continue
            a = agg.setdefault(p, {"eur": 0, "kg": 0})
            if "VALUE" in dims.get("indicators", ""):
                a["eur"] += v
            elif "QUANTITY" in dims.get("indicators", ""):
                a["kg"] += v * 100
            months.add(dims.get("time", ""))
        last = max(months) if months else ""
        ranked = sorted(((p, a) for p, a in agg.items() if a["kg"] >= 25000 and a["eur"] > 0 and p in iso3 and iso3[p] not in EU27), key=lambda x: -x[1]["kg"])[:10]
        for p, a in ranked:
            uv = a["eur"] / a["kg"]
            if not (0.02 < uv < 500):
                continue
            out.append(row("eu_cif", f"{name} - EU import price from {iso3[p]} (CIF EU border)", commodity, round(uv, 4), "EUR", "kg", 1, f"{last[:7]}-01" if last else "",
                           "Eurostat Comext: EU customs import declarations by origin", "https://ec.europa.eu/eurostat/comext/newxtweb/", grade=f"{name}, all grades: {a['kg'] / 1000:,.0f} t in {len(months)} months",
                           origin=iso3[p], place="EU border", incoterm="CIF", hs6=hs, kind="index", tier="T1 Official statistics",
                           basis="import value divided by weight over the months stated: freight and insurance to the EU included; the average of every grade shipped"))
    return out


EU27 = {"AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "IRL", "ITA", "LVA", "LTU", "LUX", "MLT", "NLD", "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE"}
WFP_NAMES = {"coffee": "Coffee Arabica", "sesame": "Sesame seed", "rice": "Rice", "maize": "Maize", "wheat": "Wheat", "sugar": "Sugar", "lentils": "Pulses", "chickpeas": "Pulses",
             "groundnuts": "Nuts", "cashew": "Cashew", "cocoa": "Cocoa beans", "tea": "Tea", "soybeans": "Soybeans", "sorghum": "Sorghum", "beans": "Pulses", "cotton": "Cotton",
             "oil (palm)": "Palm oil", "oil (sunflower)": "Sunflower oil", "niger seed": "Oilseeds", "lin seed": "Oilseeds", "honey": "Honey", "cowpeas": "Pulses", "millet": "Millet"}
WFP_COUNTRIES = {"ETH": "ethiopia", "KEN": "kenya", "UGA": "uganda", "TZA": "united-republic-of-tanzania", "RWA": "rwanda", "SDN": "sudan", "NGA": "nigeria", "GHA": "ghana",
                 "CIV": "cote-d-ivoire", "BFA": "burkina-faso", "MLI": "mali", "SEN": "senegal", "MOZ": "mozambique", "ZMB": "zambia", "MWI": "malawi", "CMR": "cameroon",
                 "IND": "india", "PAK": "pakistan", "MMR": "myanmar", "KHM": "cambodia", "IDN": "indonesia", "PHL": "philippines", "LKA": "sri-lanka", "COL": "colombia",
                 "GTM": "guatemala", "HND": "honduras", "EGY": "egypt", "TUR": "turkiye", "UKR": "ukraine", "KAZ": "kazakhstan"}


def wfp_local():
    """Prices on markets inside the origin country (WFP market monitoring, published on HDX; monthly, in USD): the median
    of the country's monitored markets over the last months. Wholesale where WFP records it, else retail (stated). This
    is the domestic level a local buyer pays, below the export price by the cost of cleaning, grading and getting to port."""
    import statistics
    out = []
    for iso, slug in WFP_COUNTRIES.items():
        try:
            pk = get(f"https://data.humdata.org/api/3/action/package_show?id=wfp-food-prices-for-{slug}").json()["result"]
            url = next(x["url"] for x in pk["resources"] if "food_prices" in x["url"] or "Food Prices" in x.get("name", ""))
            rows_ = list(csv.DictReader(io.StringIO(get(url).content.decode("utf-8", "replace"))))
        except Exception as e:  # noqa: BLE001
            log.warning("wfp %s: %s", iso, str(e)[:100]); continue
        dated = [x for x in rows_ if re.match(r"\d{4}-\d{2}", x.get("date", ""))]
        if not dated:
            continue
        last = max(x["date"] for x in dated)
        y, m = int(last[:4]), int(last[5:7])
        cut = f"{y if m > 3 else y - 1}-{(m - 3) if m > 3 else m + 9:02d}"
        g = {}
        for x in dated:
            if x["date"][:7] <= cut:
                continue
            base = re.sub(r"\s*\(.*", "", x.get("commodity", "")).strip().lower()
            key_ = x.get("commodity", "").strip().lower() if x.get("commodity", "").strip().lower() in WFP_NAMES else base
            if key_ not in WFP_NAMES:
                continue
            um = re.match(r"\s*([\d.]*)\s*(kg|g|l|mt)\b", x.get("unit", "").lower())
            usd = num(x.get("usdprice") or "")
            if not um or not usd:
                continue
            kg = (float(um.group(1)) if um.group(1) else 1) * {"kg": 1, "g": 0.001, "l": 1, "mt": 1000}[um.group(2)]
            if kg <= 0:
                continue
            g.setdefault((x.get("commodity", "").strip(), x.get("pricetype", "").strip() or "Retail", key_), []).append((usd / kg, x.get("market", ""), x["date"]))
        best = {}
        for (com, ptype, key_), vals in g.items():   # wholesale outranks retail for the same commodity
            if com not in best or (ptype.lower() == "wholesale" and best[com][0].lower() != "wholesale"):
                best[com] = (ptype, key_, vals)
        for com, (ptype, key_, vals) in best.items():
            prices = [v[0] for v in vals]
            if len(prices) < 3:
                continue
            med = statistics.median(prices)
            if not (0.01 < med < 500):
                continue
            out.append(row("wfp", f"{com} - {iso} local markets ({ptype.lower()})", WFP_NAMES[key_], round(med, 4), "USD", "kg", 1, max(v[2] for v in vals)[:10],
                           "WFP market price monitoring (HDX)", f"https://data.humdata.org/dataset/wfp-food-prices-for-{slug}",
                           grade=f"{com}, {ptype.lower()}: median of {len(prices)} quotes on {len({v[1] for v in vals})} markets, range {min(prices):.2f}-{max(prices):.2f} USD/kg",
                           origin=iso, place=f"{iso}, domestic markets", hs6="", kind="spot", tier="T2 UN market monitoring",
                           basis=f"domestic {ptype.lower()} price inside the origin country, not an export price"))
    return out


def eem_ethiopia():
    """Ethiopian coffee at the origin (leads/eth_market.py): FOB lots offered by exporters, by area, grade and process;
    the average export price of the official export record (all exporters, and it also writes the exporter ranking
    the supplier index reads); roasted coffee export prices by grade."""
    from .eth_market import fetch, BASE
    d = fetch()
    out = []
    for lot in d["lots"]:
        out.append(row("eem", f"Coffee - Ethiopia {lot['lot']} (exporter offer, {lot['seller'][:30]})", "Coffee Arabica", lot["usd_t"], "USD", "t", 1000, lot["date"],
                       "Ethiopian Export Market marketplace: exporter's own listing", BASE + "/marketplace",
                       grade=f"{lot['origin_area']} Grade {lot['grade']} {lot['process']}: {lot['qty_t']:g} t offered, minimum {lot['min_t']:g} t, seller {lot['seller']}",
                       origin="ETH", place="Ethiopia (Djibouti port)", incoterm=lot["incoterm"].split(" ")[0], hs6="090111", kind="offer", tier="T4 Marketplace listing",
                       basis="an exporter's asking price on a marketplace (its own claim, not a concluded trade): confirm the lot and the exporter before relying on it"))
    ex = d["exporters"]
    if ex:
        v, t = sum(e["value_usd"] for e in ex), sum(e["tons"] for e in ex)
        ends = f"{int(d['year']) + 8}-07-07" if str(d["year"]).isdigit() else ""   # the Ethiopian year ends in early July
        out.append(row("eem", f"Coffee - Ethiopia average export price, {d['year']} E.C. (official export record)", "Coffee Arabica", round(v / (t * 1000), 4), "USD", "kg", 1, ends,
                       "Ethiopian Coffee and Tea Authority export record, as published by Ethiopian Export Market", BASE + "/insight",
                       grade=f"all grades: {t:,.0f} t worth ${v / 1e6:,.0f}M by the {len(ex)} listed exporters, range {min(e['value_usd'] / e['tons'] / 1000 for e in ex):.2f}-{max(e['value_usd'] / e['tons'] / 1000 for e in ex):.2f} USD/kg by exporter",
                       origin="ETH", place="Ethiopia, export", incoterm="FOB", hs6="090111", kind="index", tier="T1 Official statistics",
                       basis="export value divided by tonnes over the whole Ethiopian year: the average of every grade, and a year old by now"))
    for g, usd_t in d["roasted"]:
        if usd_t:
            out.append(row("eem", f"Roasted coffee - Ethiopia Grade {g} (export price)", "Coffee roasted", usd_t, "USD", "t", 1000, d["roasted_date"],
                           "Ethiopian Coffee and Tea Authority, as published by Ethiopian Export Market", BASE + "/insight", grade=f"Roasted, Grade {g}", origin="ETH",
                           place="Ethiopia, export", hs6="090121", kind="assessment", tier="T2 Regulator price list", basis="roasted coffee export price by grade, issued weekly"))
    return out


CMB_MAP = [  # category slug word -> (our commodity, hs6); anything else is kept under its own name
    ("sesame", "Sesame seed", "120740"), ("cashew", "Cashew", "080132"), ("almond", "Nuts", "080212"), ("pistachio", "Nuts", "080252"), ("walnut", "Nuts", "080232"),
    ("hazelnut", "Nuts", "080222"), ("peanut", "Nuts", "120242"), ("groundnut", "Nuts", "120242"), ("chickpea", "Pulses", "071320"), ("lentil", "Pulses", "071340"),
    ("beans", "Pulses", "071333"), ("peas", "Pulses", "071310"), ("coffee", "Coffee Arabica", "090111"), ("cocoa", "Cocoa beans", "180100"), ("pepper", "Pepper", "090411"),
    ("cardamom", "Spices", "090831"), ("cumin", "Spices", "090931"), ("turmeric", "Spices", "091030"), ("ginger", "Spices", "091011"), ("cinnamon", "Spices", "090611"),
    ("clove", "Spices", "090710"), ("chilli", "Spices", "090421"), ("coriander", "Spices", "090921"), ("fennel", "Spices", "090961"), ("nutmeg", "Spices", "090811"),
    ("vanilla", "Spices", "090510"), ("rice", "Rice", "100630"), ("wheat", "Wheat", "100199"), ("maize", "Maize", "100590"), ("corn", "Maize", "100590"), ("barley", "Barley", "100390"),
    ("sunflower", "Sunflower seed", "120600"), ("linseed", "Oilseeds", "120400"), ("flax", "Oilseeds", "120400"), ("rapeseed", "Oilseeds", "120510"), ("poppy", "Oilseeds", "120791"),
    ("pumpkin", "Oilseeds", "120799"), ("chia", "Oilseeds", "120799"), ("quinoa", "Grains", "100850"), ("millet", "Millet", "100829"), ("buckwheat", "Grains", "100810"),
    ("raisin", "Dried fruit", "080620"), ("dates", "Fruit", "080410"), ("apricot", "Dried fruit", "081310"), ("fig", "Dried fruit", "080420"), ("prune", "Dried fruit", "081320"),
    ("coconut", "Coconut", "080111"), ("sugar", "Sugar", "170199"), ("butter", "Dairy products", "040510"), ("avocado", "Fruit", "080440"), ("banana", "Fruit", "080390"),
    ("honey", "Honey", "040900"), ("garlic", "Vegetables", "070320"), ("onion", "Vegetables", "071220"), ("mustard", "Oilseeds", "120750"), ("soy", "Soybeans", "120190")]


def _flag_iso3(flag):
    """A flag emoji is two regional-indicator letters: decoded to ISO2, then ISO3."""
    cps = [ord(c) - 0x1F1E6 for c in flag if 0x1F1E6 <= ord(c) <= 0x1F1FF]
    if len(cps) != 2:
        return ""
    a2 = "".join(chr(65 + c) for c in cps)
    try:
        import pycountry
        c = pycountry.countries.get(alpha_2=a2)
        return c.alpha_3 if c else ""
    except Exception:  # noqa: BLE001
        return ""


def cmb_quotes():
    """Current quotations by origin, specification and delivery basis from the CMB commodity information service
    (commodity-board.com; its robots.txt allows the category pages): one table per product, dated, in EUR/kg, each row
    with the origin country, the place and the incoterm ("New Delhi · FOB", "Łódź · FCA"). Broker quotations: an asking
    level for a stated specification, not a concluded trade. A FOB row is a price at the origin; an FCA/DDP row in
    Europe is a landed price and is labelled so."""
    import time as _t
    home = get("https://commodity-board.com/category/oil-seeds/sesame").text
    cats = sorted(set(re.findall(r'href="(/category/[a-z0-9\-]+-market-news-prices-global-supply-demand-outlook)"', home)))
    out, groups, t0 = [], {}, _t.time()
    for path in cats:
        if _t.time() - t0 > 420:
            log.info("cmb: time budget reached, %d of %d categories", cats.index(path), len(cats)); break
        slug = path.split("/")[-1].replace("-market-news-prices-global-supply-demand-outlook", "")
        try:
            h = get("https://commodity-board.com" + path).text
        except Exception as e:  # noqa: BLE001
            log.warning("cmb %s: %s", slug, str(e)[:80]); continue
        _t.sleep(1.2)
        as_of = re.search(r"As of\s*(?:<!-- -->)?\s*<time[^>]*>([^<]+)</time>|As of ([A-Z][a-z]{2} \d{1,2}, \d{4})", h)
        d = ""
        if as_of:
            try:
                d = datetime.strptime((as_of.group(1) or as_of.group(2)).strip(), "%b %d, %Y").date().isoformat()
            except ValueError:
                d = ""
        unit = re.search(r">(EUR|USD)(?:<!-- -->)?/(kg|t|mt)<", h)
        ccy, per = (unit.group(1), unit.group(2)) if unit else ("EUR", "kg")
        commodity, hs = next(((c, x) for w, c, x in CMB_MAP if w in slug), (slug.replace("-", " ").title(), ""))
        for m in re.finditer(r'<tr[^>]*>\s*<td[^>]*>\s*<a[^>]*>([^<]+)</a>\s*(?:<div[^>]*>([^<]*)</div>)?\s*</td>\s*<td[^>]*>\s*<span[^>]*>([^<]*)</span>\s*(?:<!-- -->)?\s*([^<·]+)·\s*([A-Z]{3})\s*</td>'
                             r'\s*<td[^>]*>\s*[€$]?\s*([\d.,]+)\s*</td>', h):
            name, spec, flag, place, inco, price = (html.unescape(m.group(1)).strip(), html.unescape(m.group(2) or "").strip(), m.group(3), html.unescape(m.group(4)).strip(), m.group(5), num(m.group(6).replace(",", "")))
            iso = _flag_iso3(flag)
            if not price or not d:
                continue
            groups.setdefault((name, spec, iso, inco, place, commodity, hs, ccy, per, d, path), []).append(price)
    for (name, spec, iso, inco, place, commodity, hs, ccy, per, d, path), prices in groups.items():   # several lots of one specification: one row, median and range
        prices.sort()
        mid = prices[len(prices) // 2]
        at_origin = inco in ("FOB", "FAS", "EXW")
        rng = f", {len(prices)} quotations {prices[0]:g}-{prices[-1]:g} {ccy}/{per}" if len(prices) > 1 else ""
        out.append(row("cmb", f"{name}{' ' + spec if spec else ''} - {iso or 'origin n/a'} ({inco} {place})"[:110], commodity, mid, ccy, per, 1 if per == "kg" else 1000, d,
                       "CMB commodity information service (broker quotations)", "https://commodity-board.com" + path, grade=f"{name}{', ' + spec if spec else ''}{rng}", origin=iso,
                       place=place, incoterm=inco, hs6=hs, kind="offer", tier="T3 Broker quotation",
                       basis=("quotation at the origin" if at_origin else "quotation delivered in the buyer's region (freight and handling included), not an origin price") + ": an asking level for the stated specification, not a concluded trade"))
    return out


ADAPTERS = [fnc_colombia, uganda_coffee, ecx_2merkato, cepea, cai_cotton, tea_board, spices_cardamom, cac_rosario, eia, steelbenchmarker, drewry_wci,
            mpob_cpo, dtn_fertilizer, kilimo_nce, forbes_colombo, ahdb_dairy, energy_charts, eu_oil_bulletin, vietnam_coffee, exa_ethiopia_coffee, worldbank_pink, royal_ethiopia, comtrade_fob, comext_cif, wfp_local, eem_ethiopia, cmb_quotes]
KEYS = {"fnc_colombia": "fnc", "uganda_coffee": "uganda", "ecx_2merkato": "ecx", "cepea": "cepea", "cai_cotton": "cai", "tea_board": "teaboard",
        "spices_cardamom": "spices", "cac_rosario": "cac", "eia": "eia", "steelbenchmarker": "steelbench", "drewry_wci": "drewry", "mpob_cpo": "mpob",
        "dtn_fertilizer": "dtn", "kilimo_nce": "nce", "forbes_colombo": "forbes", "ahdb_dairy": "ahdb", "energy_charts": "echarts", "eu_oil_bulletin": "wob", "vietnam_coffee": "vncoffee", "exa_ethiopia_coffee": "exa_eth", "worldbank_pink": "wbpink", "royal_ethiopia": "royal_eth", "comtrade_fob": "ct_fob", "comext_cif": "eu_cif", "wfp_local": "wfp", "eem_ethiopia": "eem", "cmb_quotes": "cmb"}


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


# monthly sources are dated by their month start and published about a month late
ROTATING = {"ct_fob"}
MAX_AGE = {"eem": 500, "ahdb": 70, "wbpink": 70, "ct_fob": 150, "eu_cif": 120, "wfp": 120}


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
        if got and KEYS.get(name) in ROTATING:   # a rotating source: the origins not reached this run keep their last rows
            fresh = {g["origin"] for g in got}
            got += [o_ for o_ in prev.get(KEYS[name], []) if o_.get("origin") not in fresh]
        if got:
            rows += got
            report[name] = len(got)
        else:  # keep the last good rows of this source, still dated as published
            old = prev.get(KEYS.get(name), [])
            rows += old
            report[name] = f"0 (kept {len(old)} previous)"
        _ = key
    # source health: per source, how many fresh rows, the newest price date and its age; a source with no fresh rows or a
    # date older than 14 days is "stale" (a broken parser or a publisher that stopped), so it shows up instead of hiding
    health = {}
    for a in ADAPTERS:
        key = KEYS.get(a.__name__, a.__name__)
        mine = [r for r in rows if r["adapter"] == key]
        newest = max((r["date"] for r in mine if r.get("date")), default="")
        try:
            age = (date.fromisoformat(today) - date.fromisoformat(newest)).days if newest else None
        except ValueError:
            age = None
        fresh = isinstance(report.get(a.__name__), int)
        if key == "exa_eth" and not os.environ.get("EXA_API_KEY"):
            health[key] = {"rows": 0, "fetched_now": False, "newest_date": "", "age_days": None, "status": "off (no EXA_API_KEY)"}
            continue
        health[key] = {"rows": len(mine), "fetched_now": fresh, "newest_date": newest, "age_days": age,
                       "status": "ok" if fresh and (age is None or age <= MAX_AGE.get(key, 14)) else "stale"}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    (OUT.parent / "origin_prices_health.json").write_text(json.dumps({"at": today, "sources": health}, indent=1), encoding="utf-8")
    stale = [k for k, v in health.items() if v["status"] == "stale"]
    if stale:
        print("STALE price sources:", ", ".join(stale))
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print("origin prices:", json.dumps(report), f"total {len(rows)}")
    return rows


def complete():
    """True when the saved file already holds rows from every source (a new source triggers a refresh)."""
    if not OUT.exists():
        return False
    have = {r["adapter"] for r in csv.DictReader(open(OUT, encoding="utf-8"))}
    # sources that may legitimately return nothing on a given day never force a refresh
    need = set(KEYS.values()) - {"exa_eth", "ct_fob", "eu_cif", "wfp", "royal_eth", "eem", "cmb"}
    return need <= have


if __name__ == "__main__":
    import sys
    if "--complete" in sys.argv:
        sys.exit(0 if complete() else 1)
    logging.basicConfig(level=logging.INFO)
    main()
