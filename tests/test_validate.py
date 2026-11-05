"""Pure checks for leads/validate.py and the contact cleaning that uses it."""
from datetime import date

from leads.contacts import clean_email, clean_phone
from leads.validate import date_ok, email_ok, hs_ok, lei_ok, phone_ok, url_ok, vat_format_ok


def test_phones():
    assert clean_phone("03-6123456", "ISR") == "+97236123456"          # local Tel Aviv landline gets +972
    assert clean_phone("+972 54 123", "ISR") == ""                      # too short for Israel
    assert clean_phone("+44 20 7946 0958", "GBR") == "+442079460958"
    assert clean_phone("06 12345678", "ITA") == "+390612345678"         # Italy keeps the trunk 0
    assert clean_phone("+254 722 123456", "KEN") == "+254722123456"
    assert clean_phone("+254 20 32", "KEN") == ""
    assert clean_phone("12345", "USA") == ""
    assert not phone_ok("+11111111111")[0]


def test_other_fields():
    assert email_ok("info@acme.com")[0] and not email_ok("a..b@x.com")[0] and not email_ok("logo@2x.png")[0]
    assert clean_email("a..b@x.com; info@acme.com; john@acme") == "info@acme.com"
    assert lei_ok("529900D044PDQM82UY84") and not lei_ok("529900D044PDQM82UY85")
    assert vat_format_ok("DE", "811152011") and not vat_format_ok("DE", "81115201")
    t = date(2026, 11, 5)
    assert date_ok("2026-12-01", "deadline", t)[0] and not date_ok("2031-01-01", "deadline", t)[0]
    assert not date_ok("2026-12-01", "published", t)[0] and not date_ok("2026-02-30", "deadline", t)[0]
    assert hs_ok("8481.80") and not hs_ok("99") and not hs_ok("1")
    assert url_ok("https://www.acme.com/x") and not url_ok("not stated") and not url_ok("http://localhost")


if __name__ == "__main__":
    test_phones(); test_other_fields()
    print("validate: all checks passed")
