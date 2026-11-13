import datetime as dt

from leads import procure_pages as pp

T = dt.date(2026, 11, 13)
HOME = """<a href="/about">About</a><a href="/procurement/tenders">Current Tenders</a><a href="/careers/vendor-jobs">Jobs</a>
<a href="https://other.com/tenders">x</a><a href="/suppliers">Supplier registration</a>"""
PAGE = """<table>
<tr><td><a href="/t/1">Supply of 400 kV transformers for Plant A</a></td><td>Closing date: 15/12/2026</td></tr>
<tr><td><a href="/t/2">Catering services for the head office</a></td><td>Deadline 2026-10-01</td></tr>
<tr><td><a href="/t/3">Pump spare parts framework agreement</a></td><td>Awarded - closing 20/12/2026</td></tr>
<tr><td><a href="/t/4">Annual report 2026 published for shareholders</a></td><td>12 December 2026</td></tr>
</table><ul><li><a href="/t/5">RFQ: steel pipes DN200, 3 km</a> Submission deadline: Jan 8, 2027</li></ul>"""


def test_links_and_notices():
    ls = pp.procure_links("https://acme.com/", HOME)
    assert ls[0] == "https://acme.com/procurement/tenders" and "https://acme.com/suppliers" in ls
    assert not any("careers" in u or "other.com" in u for u in ls)
    ns = pp.notices("https://acme.com/procurement/tenders", PAGE, T)
    titles = [n["title"] for n in ns]
    assert titles == ["Supply of 400 kV transformers for Plant A", "RFQ: steel pipes DN200, 3 km"]
    assert ns[0]["deadline"] == "2026-12-15" and ns[0]["link"] == "https://acme.com/t/1"
    assert ns[1]["deadline"] == "2027-01-08"
