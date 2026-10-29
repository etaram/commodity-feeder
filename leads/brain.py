"""The brain: turns open notices into ranked, explained pursuit decisions.

Everything here uses public data only (award history, notice fields). Private inputs (your supplier coverage,
relationships, profile weights) are applied in the Google Sheet on top of these columns.

Per tender it adds:
  est_bidders         expected number of competing bids (buyer history > country+sector > sector > default)
  foreign_win_rate    share of awards in the buyer's country and sector won by suppliers from another country
  buyer_awards_12m    awards by this buyer in the last 12 months; buyer_median_award_usd; incumbent
  p_win_market        win probability for a capable outside supplier before supplier coverage (sheet adds that)
  margin_pct          default gross margin for the sector (Assumptions tab can override)
  ev_usd              expected value = value x margin x p_win - pursuit cost
  decision            Pursue / Watch / Ignore, and why (one line)
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


def enrich(tenders, awards):
    st = Stats(awards)
    for r in tenders:
        sec, country = r["sector"], r["country"]
        bidders, bsrc = st.est_bidders(r.get("buyer"), country, sec)
        fr, n_aw = st.foreign_rate(country, sec)
        if fr is None:
            fr = _access_prior(r.get("access"))
            fsrc = "access rules"
        else:
            fsrc = f"{n_aw} awards"
        x = st.buyer.get((_norm(r.get("buyer")), _c(country)))
        inc = ""
        if x and x["wins"]:
            inc = "; ".join(w for w, _ in sorted(x["wins"].items(), key=lambda y: -y[1])[:2])[:120]
        # Probability that a capable outside supplier wins: fair share among bidders, scaled by how open the market
        # has been to foreign winners (0.3 = neutral), capped.
        home = _c(country) == "ISR"  # Sinder is an Israeli company: home market, no foreign-bidder discount
        if home:
            openness, trad = 1.3, 1.0
            fsrc = "home market"
        else:
            openness = min(1.6, max(0.15, fr / 0.3))
            trad = TRADABLE.get(sec) or (0.5 if (r.get("nature") or "").startswith("serv") else 1.0)
            if fsrc != "access rules":
                trad = trad ** 0.5  # the measured foreign rate already reflects part of it
        p = min(0.6, (1.0 / (bidders + 1.0)) * openness * trad)
        margin = MARGIN.get(sec, 0.08)
        usd = r.get("est_value_usd")
        fw = bool(FRAMEWORK.search(f"{r.get('title', '')} {r.get('title_en', '')} {r.get('notice_type', '')}"))
        cost = PURSUIT_COST.get(r.get("stage") or "tender", 3000)
        est_src = ""
        if usd in ("", None):
            ev_usd, est_src = st.est_value(r.get("buyer"), country, sec)
        else:
            ev_usd = usd
        if ev_usd not in ("", None):
            # framework values are ceilings shared by several suppliers; estimated values get a 50% haircut
            v = min(ev_usd, 100_000_000) * (0.3 if fw else 1.0) * (0.5 if est_src else 1.0)
            ev = round(v * margin * p - cost)
        else:
            ev = ""
        days = r.get("days_left")
        why = []
        if usd in ("", None):
            why.append(f"value not stated (estimated from {est_src})" if est_src else "value not stated")
        if isinstance(days, int) and days < 7 and r.get("stage") != "planned":
            why.append(f"only {days} days left")
        why.append(f"{bidders:g} bidders expected ({bsrc})")
        why.append("Israel: home market for Sinder" if home else f"foreign win rate {fr:.0%} ({fsrc})")
        if fw:
            why.append("framework: value is a ceiling")
        if trad < 1:
            why.append("local-service sector")
        if inc:
            why.append(f"incumbent: {inc[:60]}")
        if isinstance(days, int) and days < 5 and r.get("stage") != "planned":
            decision = "Ignore"
        elif ev != "" and ev >= (8_000 if home else 25_000) and p >= 0.05:
            decision = "Pursue"
        elif (ev != "" and ev >= 2_000) or (ev == "" and r["score"] >= 60 and p >= 0.08) or r.get("stage") == "planned":
            decision = "Watch"
        else:
            decision = "Ignore"
        r.update({
            "est_bidders": round(bidders, 1), "foreign_win_rate": round(fr, 3),
            "buyer_awards_12m": x["n"] if x else 0,
            "buyer_median_award_usd": round(median(x["usd"])) if x and x["usd"] else "",
            "incumbent": inc, "p_win_market": round(p, 3), "margin_pct": margin, "ev_usd": ev,
            "decision": decision, "why": "; ".join(why)[:240],
        })
    return st
