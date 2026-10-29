"""Trade-agreement edge for the deal calculation.

For each tender: which tariff market the goods enter (Israel, EU, USA, GCC, India, EAC, ECOWAS), its MFN import duty
for the commodity group (Assumptions tab, maintained daily by the assumptions agent), and which sourcing origins
enter that market duty-free or preferentially under a trade agreement in force (data/leads/fta.csv).

The edge: a supplier from a non-preferential origin (typically China) pays the full duty; sourcing the same goods
from a preferential origin removes it. We credit half of that duty as extra margin (the rest is assumed to be
competed away), capped at 4 points, and only for goods (not works or services).
"""
import csv
import json

from .common import LEADS, PRIVATE, log

EU27 = set("AUT BEL BGR HRV CYP CZE DNK EST FIN FRA DEU GRC HUN IRL ITA LVA LTU LUX MLT NLD POL PRT ROU SVK SVN ESP SWE".split())
GCC = set("SAU ARE QAT KWT BHR OMN".split())
EAC = set("KEN TZA UGA RWA BDI SSD COD SOM".split())
ECOWAS = set("NGA GHA SEN CIV BEN TGO BFA MLI NER GIN GMB GNB LBR SLE CPV".split())
# Assumptions duty columns B..H
MARKETS = ["ISR", "EU", "USA", "GCC", "IND", "EAC", "ECOWAS"]
# where Sinder realistically sources goods from; China first because it has no agreement with most markets
ORIGINS = ["EU", "KOR", "VNM", "IND", "USA", "GBR", "JPN", "ARE", "TUR", "MEX", "CAN", "BRA", "UKR", "THA", "IDN", "CHN"]


def market_of(iso3):
    c = (iso3 or "").upper()
    if c in EU27:
        return "EU"
    if c in GCC:
        return "GCC"
    if c in EAC:
        return "EAC"
    if c in ECOWAS:
        return "ECOWAS"
    return c if c in MARKETS else ""


def _bloc(code):
    return "EU" if code in EU27 or code == "EU" else code


def load_agreements():
    rows = list(csv.DictReader(open(LEADS / "fta.csv", encoding="utf-8")))
    out = []
    for r in rows:
        if r["status"] != "in force":
            continue
        members = {_bloc(m) for m in r["members"].split()}
        out.append((r["agreement"], members))
    return out


def preferential_origins(country, market, agreements):
    """Origins with an agreement in force that covers THIS destination country (a bilateral with one GCC member does
    not cover the others; EU agreements cover every EU member; members of a customs union trade duty-free)."""
    c = (country or "").upper()
    targets = {c} | ({"EU"} if market == "EU" else set())
    found = {}
    for name, members in agreements:
        if not members & targets:
            continue
        for o in ORIGINS:
            if o in members and o not in targets:
                found.setdefault(o, name)
    return found


def load_duties():
    """Assumptions!A33:K51 -> {group: {market: rate}}; generic estimate (K) fills empty cells."""
    cache = PRIVATE / "duties.json"
    try:
        from .push import LEADS_SHEET, Sheets
        rows = Sheets().values(LEADS_SHEET, "Assumptions!A33:K51")

        def pct(x):
            x = str(x or "").replace("%", "").replace(",", ".").strip()
            try:
                v = float(x)
            except ValueError:
                return None
            return v / 100 if v > 1 else v
        duties = {}
        for r in rows:
            if not r or not r[0]:
                continue
            r = list(r) + [""] * (11 - len(r))
            generic = pct(r[10])
            duties[r[0]] = {m: (pct(r[1 + i]) if pct(r[1 + i]) is not None else generic) for i, m in enumerate(MARKETS)}
            duties[r[0]]["_generic"] = generic
        PRIVATE.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(duties))
        return duties
    except Exception as e:  # noqa: BLE001
        log.warning("duties from sheet: %s", e)
        return json.loads(cache.read_text()) if cache.exists() else {}


class Edge:
    def __init__(self):
        self.agreements = load_agreements()
        self.duties = load_duties()
        self._cache = {}

    def of(self, country, group, goods=True):
        """Returns (margin_uplift, note, duty, origins) for a tender."""
        mk = market_of(country)
        if not goods or not mk:
            return 0.0, "", None, []
        d = (self.duties.get(group) or {}).get(mk)
        if d is None:
            d = (self.duties.get(group) or {}).get("_generic")
        if not d:
            return 0.0, "", d, []
        key = (country or "").upper()
        if key not in self._cache:
            self._cache[key] = preferential_origins(country, mk, self.agreements)
        pref = self._cache[key]
        if not pref:
            return 0.0, f"{mk} duty {d:.0%}, no preferential origin in our sourcing set", d, []
        origins = list(pref)[:4]
        up = min(0.04, d * 0.5)
        names = ", ".join(origins)
        return up, f"FTA edge: source from {names} duty-free into {mk} (MFN {d:.0%} for others, +{up:.1%} margin)", d, origins
