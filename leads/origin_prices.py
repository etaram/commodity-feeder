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
    the value a visitor sees: the four coffee provinces, averaged. The date comes from 'Cập nhật: dd/mm/yyyy'."""
    css = dict(re.findall(r"\.(\w+)::after\s*\{\s*content:'([^']*)'", html))
    vals = []
    for name, cls in re.findall(r'<tr><td><a [^>]*>([^<]+)</a></td>\s*<td><span class="(\w+) \w+"></span></td>', html):
        if name.strip() in ("Đắk Lắk", "Lâm Đồng", "Gia Lai", "Đắk Nông") and cls in css:
            v = num(css[cls].replace(",", ""))
            if v and 20000 < v < 400000:   # VND per kg sanity range for green coffee
                vals.append(v)
    d = re.search(r"Cập nhật:\s*(\d{2})/(\d{2})/(\d{4})", html)
    if len(vals) < 3 or not d:
        return None
    return sum(vals) / len(vals), f"{d.group(3)}-{d.group(2)}-{d.group(1)}"


def vietnam_coffee():
    url = "https://giacaphe.com/gia-ca-phe-noi-dia/"
    html = get(url).text
    got = parse_giacaphe(text_of(html)) or parse_giacaphe_table(html)
    if not got:
        return []
    return [row("vncoffee", "Coffee Robusta - Vietnam Central Highlands farm-gate average", "Coffee Robusta", got[0], "VND", "kg", 1, got[1],
                "giacaphe.com daily domestic coffee prices (Dak Lak, Lam Dong, Gia Lai, Dak Nong average)", url, grade="Robusta green coffee, domestic",
                origin="VNM", place="Vietnam Central Highlands, at the buying agent", hs6="090111", kind="spot", tier="T3 Trade press",
                basis="average of the provinces' daily buying prices, as published by a trade site")]


ADAPTERS = [fnc_colombia, uganda_coffee, ecx_2merkato, cepea, cai_cotton, tea_board, spices_cardamom, cac_rosario, eia, steelbenchmarker, drewry_wci,
            mpob_cpo, dtn_fertilizer, kilimo_nce, forbes_colombo, ahdb_dairy, energy_charts, eu_oil_bulletin, vietnam_coffee]
KEYS = {"fnc_colombia": "fnc", "uganda_coffee": "uganda", "ecx_2merkato": "ecx", "cepea": "cepea", "cai_cotton": "cai", "tea_board": "teaboard",
        "spices_cardamom": "spices", "cac_rosario": "cac", "eia": "eia", "steelbenchmarker": "steelbench", "drewry_wci": "drewry", "mpob_cpo": "mpob",
        "dtn_fertilizer": "dtn", "kilimo_nce": "nce", "forbes_colombo": "forbes", "ahdb_dairy": "ahdb", "energy_charts": "echarts", "eu_oil_bulletin": "wob", "vietnam_coffee": "vncoffee"}


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
        health[key] = {"rows": len(mine), "fetched_now": fresh, "newest_date": newest, "age_days": age,
                       "status": "ok" if fresh and (age is None or age <= 14) else "stale"}
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
    return set(KEYS.values()) <= have


if __name__ == "__main__":
    import sys
    if "--complete" in sys.argv:
        sys.exit(0 if complete() else 1)
    logging.basicConfig(level=logging.INFO)
    main()
