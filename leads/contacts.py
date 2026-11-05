"""Contact hygiene for the Supplier Universe: one clean e-mail list and phones in international form (+<country
code><number>), so the Deal Desk's WhatsApp, call and WeChat buttons work in one click. A local number ("040 123 45")
gets the company's country calling code; a number that cannot be made valid is dropped rather than shown wrong.
"""
import re

# ISO-3 -> international calling code
CC = {
    "AFG": "93", "ALB": "355", "DZA": "213", "AND": "376", "AGO": "244", "ARG": "54", "ARM": "374", "AUS": "61", "AUT": "43",
    "AZE": "994", "BHR": "973", "BGD": "880", "BLR": "375", "BEL": "32", "BLZ": "501", "BEN": "229", "BTN": "975", "BOL": "591",
    "BIH": "387", "BWA": "267", "BRA": "55", "BRN": "673", "BGR": "359", "BFA": "226", "BDI": "257", "KHM": "855", "CMR": "237",
    "CAN": "1", "CPV": "238", "CAF": "236", "TCD": "235", "CHL": "56", "CHN": "86", "COL": "57", "COM": "269", "COG": "242",
    "COD": "243", "CRI": "506", "CIV": "225", "HRV": "385", "CUB": "53", "CYP": "357", "CZE": "420", "DNK": "45", "DJI": "253",
    "DOM": "1", "ECU": "593", "EGY": "20", "SLV": "503", "GNQ": "240", "ERI": "291", "EST": "372", "SWZ": "268", "ETH": "251",
    "FJI": "679", "FIN": "358", "FRA": "33", "GAB": "241", "GMB": "220", "GEO": "995", "DEU": "49", "GHA": "233", "GRC": "30",
    "GTM": "502", "GIN": "224", "GNB": "245", "GUY": "592", "HTI": "509", "HND": "504", "HKG": "852", "HUN": "36", "ISL": "354",
    "IND": "91", "IDN": "62", "IRN": "98", "IRQ": "964", "IRL": "353", "ISR": "972", "ITA": "39", "JAM": "1", "JPN": "81",
    "JOR": "962", "KAZ": "7", "KEN": "254", "KOR": "82", "KWT": "965", "KGZ": "996", "LAO": "856", "LVA": "371", "LBN": "961",
    "LSO": "266", "LBR": "231", "LBY": "218", "LIE": "423", "LTU": "370", "LUX": "352", "MAC": "853", "MDG": "261", "MWI": "265",
    "MYS": "60", "MDV": "960", "MLI": "223", "MLT": "356", "MRT": "222", "MUS": "230", "MEX": "52", "MDA": "373", "MCO": "377",
    "MNG": "976", "MNE": "382", "MAR": "212", "MOZ": "258", "MMR": "95", "NAM": "264", "NPL": "977", "NLD": "31", "NZL": "64",
    "NIC": "505", "NER": "227", "NGA": "234", "MKD": "389", "NOR": "47", "OMN": "968", "PAK": "92", "PAN": "507", "PNG": "675",
    "PRY": "595", "PER": "51", "PHL": "63", "POL": "48", "PRT": "351", "QAT": "974", "ROU": "40", "RUS": "7", "RWA": "250",
    "SAU": "966", "SEN": "221", "SRB": "381", "SYC": "248", "SLE": "232", "SGP": "65", "SVK": "421", "SVN": "386", "SOM": "252",
    "ZAF": "27", "SSD": "211", "ESP": "34", "LKA": "94", "SDN": "249", "SUR": "597", "SWE": "46", "CHE": "41", "SYR": "963",
    "TWN": "886", "TJK": "992", "TZA": "255", "THA": "66", "TGO": "228", "TTO": "1", "TUN": "216", "TUR": "90", "TKM": "993",
    "UGA": "256", "UKR": "380", "ARE": "971", "GBR": "44", "USA": "1", "URY": "598", "UZB": "998", "VEN": "58", "VNM": "84",
    "YEM": "967", "ZMB": "260", "ZWE": "263", "PSE": "970", "XKX": "383", "TLS": "670", "SLB": "677", "VUT": "678", "WSM": "685",
    "TON": "676", "BHS": "1", "BRB": "1", "PRI": "1", "SMR": "378", "GRL": "299", "FRO": "298", "REU": "262", "NCL": "687",
}
_CODES = sorted(set(CC.values()), key=len, reverse=True)
EMAIL = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,24}")
JUNK_MAIL = re.compile(r"^(no-?reply|donotreply|do-not-reply|example|test|user|name|email|mail|info@example)|@(example|test|domain|email)\.|"
                       r"\.(png|jpe?g|gif|svg|webp)$|sentry|wixpress|@2x", re.I)


def clean_email(v):
    """Valid, distinct addresses (at most 3), lowercase, '; ' separated; placeholders and image names dropped."""
    from .validate import email_ok
    out = []
    for m in EMAIL.finditer(str(v or "")):
        e = m.group(0).strip(".'").lower()
        if not JUNK_MAIL.search(e) and email_ok(e)[0] and e not in out:
            out.append(e)
    return "; ".join(out[:3])


def one_phone(p, iso3):
    raw = str(p or "").strip()
    if not raw:
        return ""
    raw = re.split(r"\s*(?:ext\.?|x|#|доб\.?)\s*\d+$", raw, flags=re.I)[0]
    d = re.sub(r"\D", "", raw)
    cc = CC.get((iso3 or "").upper(), "")
    if raw.startswith("+"):
        pass
    elif d.startswith("00"):
        d = d[2:]
    elif cc and d.startswith(cc) and len(d) - len(cc) >= 7 and not (cc == "1" and len(d) == 10):
        pass  # already international without the plus
    elif cc:
        d = cc + (d[1:] if d.startswith("0") and cc not in ("39",) else d)  # Italy keeps its leading 0
    else:
        return ""
    if not 8 <= len(d) <= 15 or len(set(d[-7:])) == 1:
        return ""
    from .validate import phone_ok
    ok, _ = phone_ok("+" + d, iso3)  # the country's own numbering plan: length and prefixes
    if not ok and cc and not raw.startswith("+") and not str(p).strip().startswith("00") and d.startswith(cc):
        alt = cc + "0" + d[len(cc):]  # a few plans keep the trunk 0 (Italy, San Marino): retry before dropping
        if phone_ok("+" + alt, iso3)[0]:
            return "+" + alt
    return "+" + d if ok else ""


def clean_phone(v, iso3):
    """Phones in +<code><number> form (at most 2), '; ' separated; invalid ones dropped."""
    out = []
    for part in re.split(r"[;,/|]|\s{2,}|\bor\b", str(v or "")):
        p = one_phone(part, iso3)
        if p and p not in out:
            out.append(p)
    return "; ".join(out[:2])


GENERIC_BOX = re.compile(r"^(info|sales|export|exports|contact|office|admin|mail|enquir\w*|inquir\w*|hello|marketing|support|service|trade|commercial|business|import|purchase|procurement|tender\w*)\b", re.I)


def email_kind(emails, website=""):
    """For the first address: 'generic sales channel' (info@, sales@), 'named contact' (a person's mailbox) or
    'other'; and whether its domain matches the company's website domain ('aligned', 'different domain', 'free mail').
    Valid syntax is not deliverability; a different domain is a reason to check, not a verdict."""
    e = (emails or "").split(";")[0].strip().lower()
    if "@" not in e:
        return "", ""
    box, dom = e.split("@", 1)
    kind = "generic sales channel" if GENERIC_BOX.match(box) else "named contact" if re.match(r"^[a-z]+[._-][a-z]+$", box) else "other"
    if re.search(r"(gmail|yahoo|hotmail|outlook|live|icloud|aol|gmx|mail|yandex|qq|163|126|sina)\.", dom):
        align = "free mail"
    else:
        site = re.sub(r"^https?://(www\.)?", "", (website or "").lower()).split("/")[0]
        root = lambda d: ".".join(d.split(".")[-2:]) if not re.search(r"\.(co|com|org|net|gov|ac)\.[a-z]{2}$", d) else ".".join(d.split(".")[-3:])
        align = "aligned" if site and root(site) == root(dom) else "different domain" if site else ""
    return kind, align
