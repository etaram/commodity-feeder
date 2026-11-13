"""Award winners researched by the team (Grok, tab 'Winners' of the supervision sheet, exported to
data/leads/team_winners.csv): large projects already awarded, the prime winner, the official source of the award.
Only public facts are kept in the repository (project, country, buyer, award value as published, award date, winner,
source link). What the winner will need is inferred by leads.winners from the project title, like every other lead.
Each row keeps the team's own official source link; a row without an http source is not loaded."""
import csv
import datetime as dt
import re

from .common import LEADS

FILE = LEADS / "team_winners.csv"
CUR = {"USD": "USD", "US$": "USD", "$": "USD", "SAR": "SAR", "AED": "AED", "QAR": "QAR", "OMR": "OMR", "KWD": "KWD", "BHD": "BHD",
       "EUR": "EUR", "€": "EUR", "INR": "INR", "RS": "INR", "₹": "INR", "BRL": "BRL", "R$": "BRL", "COP": "COP", "CAD": "CAD",
       "C$": "CAD", "MXN": "MXN", "ARS": "ARS", "CLP": "CLP", "PEN": "PEN", "GBP": "GBP", "£": "GBP", "ILS": "ILS", "NIS": "ILS",
       "PLN": "PLN", "ZAR": "ZAR", "KES": "KES", "NGN": "NGN", "EGP": "EGP", "CNY": "CNY", "JPY": "JPY", "AUD": "AUD"}
MULT = {"thousand": 1e3, "k": 1e3, "million": 1e6, "mn": 1e6, "m": 1e6, "crore": 1e7, "cr": 1e7, "billion": 1e9, "bn": 1e9, "b": 1e9, "lakh": 1e5}


def parse_value(s):
    """('SAR', 547300000.0) from 'SAR 547.3 million (excl. VAT)'; ('', 0) when no clear amount."""
    s = s or ""
    m = re.search(r"(US\$|C\$|R\$|[A-Z]{3}|[€£₹$]|Rs\.?)\s*([\d][\d,]*(?:\.\d+)?)\s*(thousand|million|billion|crore|lakh|mn|bn|cr|[kmb])?\b", s, re.I)
    if not m:
        return "", 0.0
    cur = CUR.get(m.group(1).upper().rstrip("."), "")
    try:
        v = float(m.group(2).replace(",", "")) * MULT.get((m.group(3) or "").lower(), 1)
    except ValueError:
        return "", 0.0
    return cur, v


def parse_date(s):
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s or "")
    if m:
        try:
            return str(dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            pass
    m = re.search(r"\b(20\d\d)\b", s or "")
    return f"{m.group(1)}-01-01" if m else ""


def rows():
    """Award-like rows in the shape leads.winners reads (title, winners, buyer, country, value, currency, link...)."""
    if not FILE.exists():
        return []
    out = []
    for r in csv.DictReader(FILE.open(encoding="utf-8")):
        if not (r.get("source_url") or "").startswith("http") or not r.get("winner") or not r.get("project"):
            continue
        cur, val = parse_value(r.get("award_value"))
        d = parse_date(r.get("award_date")) or (r.get("date_added") or "")[:10]
        out.append({"title": r["project"], "winners": [r["winner"].strip()[:160]],
                    "buyer": r.get("buyer", ""), "country": (r.get("country") or "")[:3], "value": val, "currency": cur,
                    "published": d, "source": "Team research (Grok), official source", "link": r["source_url"],
                    "sector": r.get("sector", ""), "id": "TW-" + re.sub(r"[^A-Za-z0-9]+", "-", r["project"])[:50], "team": True})
    return out
