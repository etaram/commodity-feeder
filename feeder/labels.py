"""Human-readable description of exactly what a benchmark price measures."""
import re


def product_from_feed(p: dict, layer_a_name: dict) -> str:
    k, s, hs = p["source_key"], p["source"], p["hs6"]
    if k == "comext":
        return f"EU imports from non-EU origins, HS {hs} - average unit value (customs value / net weight)"
    if k == "comtrade":
        return f"HS {hs} - median import unit value of China, Japan, Korea, India, Brazil"
    if k == "census":
        return f"US imports, HS {hs} - average unit value"
    if k == "derived":
        base = re.sub(r"\s*\[benchmark for this HS code\]", "", s)
        return f"{base} - converted to this HS code's unit"
    if k == "eu_agri":
        m = re.search(r"Portal - (.+?)( \(ex-packaging station\))? \(\d+ reports", s)
        item = m.group(1) if m else s
        return f"{item} - EU market price, average of euro-area Member States" + (" (ex-packaging station)" if "ex-packaging" in s else "")
    if k == "cn_spot":
        m = re.search(r"- (.+?) \[", s)
        return f"{m.group(1) if m else s} - China domestic spot, ex-VAT"
    if k == "scrapmonster":
        return s.split(" - ", 1)[-1] + " (IREM assessment)"
    if k == "smi":
        return s.split(" - ", 1)[-1] + " - dealer reference price, USD/kg"
    if k == "dtn":
        return s.split(" - ", 1)[-1] + " - US retail average, weekly survey"
    if k == "ssb":
        return "Norwegian farmed Atlantic salmon, " + ("fresh/chilled" if "fresh" in s else "frozen") + " - export price"
    if k == "westmetall":
        return s.replace(" via Westmetall", "")
    if k == "yahoo":
        return f"{layer_a_name.get(int(p['row']), '')} - front-month settlement/last".strip(" -")
    if k == "em_global":
        return s.replace(" via Eastmoney", "")
    return s


