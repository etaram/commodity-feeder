"""Logic checks for field values, shared by every module: a value either passes its own rule or is dropped or flagged.

  phone      the country's numbering plan (length and prefixes) from Google's libphonenumber metadata, when installed;
             otherwise the length rule of ITU E.164 (8 to 15 digits with the country code)
  email      syntax, a real top-level domain shape, no placeholder or image names
  lei        ISO 17442: 20 characters, check digits mod 97 == 1
  vat (EU)   the member state's format (VIES then decides validity)
  date       a real calendar date in a plausible window for its role (published, deadline, award)
  hs code    2 to 10 digits, chapter 01 to 97
  url        http(s) with a host that has a domain
All functions are pure."""
import re
from datetime import date, timedelta

try:
    import phonenumbers
except Exception:  # noqa: BLE001
    phonenumbers = None

ISO3_TO_2 = {}


def _iso2(iso3):
    if not ISO3_TO_2:
        try:
            import pycountry
            for c in pycountry.countries:
                ISO3_TO_2[c.alpha_3] = c.alpha_2
        except Exception:  # noqa: BLE001
            pass
        ISO3_TO_2.setdefault("XKX", "XK")
    return ISO3_TO_2.get((iso3 or "").upper(), "")


def phone_ok(e164, iso3=""):
    """(ok, reason). e164 like '+97231234567'. With libphonenumber: the number must be valid for its own country's plan."""
    d = re.sub(r"\D", "", e164 or "")
    if not 8 <= len(d) <= 15:
        return False, f"{len(d)} digits: an international number has 8 to 15"
    if len(set(d[-7:])) == 1:
        return False, "placeholder digits"
    if phonenumbers is None:
        return True, ""
    try:
        n = phonenumbers.parse("+" + d, None)
    except phonenumbers.NumberParseException:
        return False, "not a phone number"
    # length and prefix must fit the country's plan for some number type (fixed line, mobile, toll free...)
    if not phonenumbers.is_valid_number(n):
        region = phonenumbers.region_code_for_country_code(n.country_code) or "?"
        why = "wrong length" if not phonenumbers.is_possible_number(n) else "a prefix that is not in use"
        return False, f"{why} for {region} numbers"
    return True, ""


def phone_country(e164):
    """ISO2 region of a valid number, or ''."""
    if phonenumbers is None:
        return ""
    try:
        return phonenumbers.region_code_for_number(phonenumbers.parse("+" + re.sub(r"\D", "", e164), None)) or ""
    except Exception:  # noqa: BLE001
        return ""


EMAIL = re.compile(r"^[a-z0-9._%+'-]+@([a-z0-9-]+\.)+[a-z]{2,24}$")


def email_ok(e):
    e = (e or "").strip().lower()
    if not EMAIL.match(e):
        return False, "not an e-mail address"
    box, dom = e.split("@", 1)
    if ".." in e or box.startswith(".") or box.endswith(".") or dom.startswith("-") or any(p.startswith("-") or p.endswith("-") for p in dom.split(".")):
        return False, "malformed address"
    if re.search(r"\.(png|jpe?g|gif|svg|webp|js|css)$", dom):
        return False, "an image or file name, not an address"
    if re.match(r"^(x+|test|example|name|email|your\.?name|user)$", box) or re.search(r"@(example|test|domain|email)\.", e):
        return False, "placeholder address"
    return True, ""


def lei_ok(v):
    v = (v or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{18}[0-9]{2}", v):
        return False
    n = int("".join(str(int(c, 36)) for c in v))
    return n % 97 == 1


EU_VAT = {"AT": r"U\d{8}", "BE": r"[01]\d{9}", "BG": r"\d{9,10}", "CY": r"\d{8}[A-Z]", "CZ": r"\d{8,10}", "DE": r"\d{9}", "DK": r"\d{8}",
          "EE": r"\d{9}", "EL": r"\d{9}", "ES": r"[A-Z0-9]\d{7}[A-Z0-9]", "FI": r"\d{8}", "FR": r"[A-HJ-NP-Z0-9]{2}\d{9}", "HR": r"\d{11}",
          "HU": r"\d{8}", "IE": r"\d{7}[A-W][A-I]?|\d[A-Z+*]\d{5}[A-W]", "IT": r"\d{11}", "LT": r"\d{9}|\d{12}", "LU": r"\d{8}", "LV": r"\d{11}",
          "MT": r"\d{8}", "NL": r"\d{9}B\d{2}", "PL": r"\d{10}", "PT": r"\d{9}", "RO": r"\d{2,10}", "SE": r"\d{12}", "SI": r"\d{8}", "SK": r"\d{10}"}


def vat_format_ok(cc, num):
    rx = EU_VAT.get(cc)
    return bool(rx and re.fullmatch(rx, num or ""))


def date_ok(v, role, today=None):
    """(ok, reason) for an ISO date in its role: 'published' (not in the future), 'deadline' (within 3 years ahead),
    'award' (not in the future, after 1990)."""
    today = today or date.today()
    try:
        d = date.fromisoformat((v or "")[:10])
    except ValueError:
        return False, "not a calendar date"
    if d.year < 1990:
        return False, f"year {d.year} is implausible"
    if role in ("published", "award") and d > today + timedelta(days=2):
        return False, f"{role} date {d} is in the future"
    if role == "deadline" and d > today + timedelta(days=3 * 365):
        return False, f"deadline {d} is more than 3 years ahead"
    return True, ""


def hs_ok(v):
    d = re.sub(r"\D", "", v or "")
    return 2 <= len(d) <= 10 and 1 <= int(d[:2]) <= 97


def url_ok(u):
    return bool(re.match(r"^https?://([a-z0-9-]+\.)+[a-z]{2,}(:\d+)?(/|$|\?)", (u or "").strip(), re.I))
