"""Small local civil works (ward roads, drains, repairs) dominate some national e-procurement feeds, mainly India's
CPPP. They are real open tenders but rarely a supply opportunity for an importer, so they are labelled (not removed):
nature = works, notice_type gets ' | local civil works', and the panel can filter them out."""
import re

WORKS = re.compile(
    r"\b(ward\s*no|ward[- ]\d|nali|naali|naale|nala|puliya|cc\s*road|c\.c\.\s*road|paver|interlocking|boundary\s*wall|"
    r"repair|repairing|renovation|maintenance|maintanance|nirman|nirmaan|construction\s+of|laying|patch|pot\s*hole|"
    r"drain|culvert|sewage|sewer|painting|white\s*wash|flooring|roof|toilet|yatri\s*shed|road\s+to|addition\s+alteration|"
    r"improvement\s+(works?|to)|restoration\s+of|bt\s*road|special\s+repairs?|jungle\s+clearance|earth\s*work|gali|khadanja|marammat|sadak)\b", re.I)
SUPPLY = re.compile(r"\b(supply|procurement\s+of|purchase|rate\s+contract|equipment|machinery|chemicals?|pipes?\s+supply)\b", re.I)


def is_local_works(title):
    t = title or ""
    return bool(WORKS.search(t)) and not SUPPLY.search(t)


def label(r):
    """Adds the label in place for Indian notices; returns True when the row was labelled."""
    if (r.get("country") or "")[:3] != "IND" or not is_local_works(r.get("title")):
        return False
    r["nature"] = r.get("nature") or "works"
    if "local civil works" not in (r.get("notice_type") or ""):
        r["notice_type"] = ((r.get("notice_type") or "").strip() + " | local civil works").lstrip(" |")
    return True
