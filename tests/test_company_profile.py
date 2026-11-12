"""Company profile extraction (leads/company_profile.py): synthetic pages only, no network, no real company data."""
import unittest

from leads import company_profile as cp

TEAM = """<html><body><h1>Our Team</h1>
<div class="card"><h3>Anna Kowalska</h3><p>Chief Executive Officer</p><a href="https://www.linkedin.com/in/anna-k-123">in</a></div>
<div class="card"><h3>Pedro Alvarez</h3><p>Export Manager</p></div>
<div class="card"><h3>Quality Control</h3><p>Managing Director</p></div>
<p>Sales Director: Wei Zhang</p>
<p>Read more about our Products</p>
</body></html>"""

ABOUT = """<html><head><script type="application/ld+json">{"@type":"Organization","name":"Example Mills","foundingDate":"1987-03-01",
"founder":{"@type":"Person","name":"Maria Rossi","jobTitle":"Founder"}}</script></head><body>
<p>Established in 1987, Example Mills employs more than 350 employees and has an annual turnover of USD 45 million.</p>
<p>Our plant covers an area of 60,000 square meters with a production capacity of 120,000 tons per year.</p>
<p>WeChat ID: examplemills88</p><img src="/img/wechat-qr.png" alt="WeChat QR code">
<img src="/img/logo.png" alt="logo">
<p>WhatsApp: +90 532 111 2233</p>
<a href="https://wa.me/905321112244">chat</a>
</body></html>"""


class Profile(unittest.TestCase):
    def setUp(self):
        self.pages = [("https://example-mills.test/", ABOUT), ("https://example-mills.test/about/team", TEAM)]

    def test_people_strict(self):
        ppl = cp.people_on(self.pages)
        names = {p["name"]: p for p in ppl}
        self.assertIn("Anna Kowalska", names)
        self.assertEqual(names["Anna Kowalska"]["role"], "chief executive")
        self.assertEqual(names["Anna Kowalska"].get("linkedin"), "https://www.linkedin.com/in/anna-k-123")
        self.assertEqual(names["Pedro Alvarez"]["role"], "sales / export")
        self.assertIn("Wei Zhang", names)
        self.assertEqual(names["Maria Rossi"]["basis"], "schema.org Person on the site")
        self.assertNotIn("Quality Control", names)  # a department heading is not a person

    def test_profile(self):
        p = cp.profile_on(self.pages, {"founded": "1987-03-01"})
        self.assertEqual(p["founded"]["value"], 1987)
        self.assertEqual(p["employees"]["value"], 350)
        self.assertEqual(p["revenue"]["currency"], "USD")
        self.assertEqual(p["revenue"]["usd_approx"], 45_000_000)
        self.assertIn("120,000 tons per year", p["capacity"]["phrase"])
        self.assertIn("60,000 square meters", p["plant_area"]["phrase"])
        self.assertEqual(p["size"]["band"], "mid")

    def test_wechat_and_whatsapp(self):
        w = cp.wechat_on(self.pages)
        self.assertEqual(w["ids"], ["examplemills88"])
        self.assertEqual(w["qr_images"], ["https://example-mills.test/img/wechat-qr.png"])
        wa = cp.whatsapp_on(self.pages, ["+905321112244"], "TUR")
        self.assertEqual([x["link"] for x in wa], ["https://wa.me/905321112244", "https://wa.me/905321112233"])

    def test_summary_only_gathered(self):
        check = {"roles": [{"role": "manufacturer"}], "description": "We mill flour. And more.", "products": ["Wheat flour"], "certificates": [], "export_countries": []}
        prof = cp.profile_on(self.pages, {})
        s = cp.summary("Example Mills", "Türkiye", check, prof)
        self.assertTrue(s.startswith("Example Mills is a manufacturer in Türkiye, founded in 1987"))
        self.assertIn("Wheat flour", s)
        self.assertNotIn("Certificates", s)

    def test_size_not_stated(self):
        self.assertEqual(cp.size_band({})["band"], "not stated")
        self.assertEqual(cp.size_band({}, "2400")["band"], "large")

    def test_press_filter(self):
        items = [{"title": "Example Mills opens new plant in Turkey", "outlet": "Daily", "outlet_url": "https://daily.test", "url": "u1", "date": "2026-01-01"},
                 {"title": "Example Mills of Ohio fined", "outlet": "Ohio Paper", "outlet_url": "https://ohio.test", "url": "u2", "date": "2026-01-02"},
                 {"title": "Mills report", "outlet": "x", "outlet_url": "", "url": "u3", "date": ""}]
        got = cp.press_filter(items, "Example Mills Ltd", ["Turkey", "Türkiye"])
        self.assertEqual([g["url"] for g in got], ["u1"])
        self.assertIsNone(cp.press_name("ABC Ltd"))

    def test_snippet_people(self):
        res = [{"url": "https://tr.linkedin.com/in/someone-1", "title": "Ali Demir - Export Manager - Example Mills | LinkedIn", "snippet": "Export Manager at Example Mills"},
               {"url": "https://www.linkedin.com/in/other", "title": "Jane Roe - CEO - Other Co | LinkedIn", "snippet": "CEO at Other Co"}]
        got = cp.snippet_people(res, "Example Mills Ltd")
        self.assertEqual([(g["name"], g["role"]) for g in got], [("Ali Demir", "sales / export")])

    def test_rss(self):
        xml = """<rss><channel><item><title>Example Mills expands - Daily</title><link>https://n.test/a</link>
        <pubDate>Mon, 02 Nov 2026 10:00:00 GMT</pubDate><source url="https://daily.test">Daily</source></item></channel></rss>"""
        got = cp.parse_rss(xml)
        self.assertEqual(got[0]["title"], "Example Mills expands")
        self.assertEqual(got[0]["date"], "2026-11-02")


if __name__ == "__main__":
    unittest.main()


class Merge(unittest.TestCase):
    def test_refine_fields_and_sheet_cells(self):
        from leads import company_check as ck
        from leads.refine import enrich_fields
        page = ABOUT
        res = ck.analyse("Example Mills", "", [("https://example-mills.test/", page), ("https://example-mills.test/team", TEAM)], "TUR")
        res["people"].append({"name": "Ali Demir", "title": "Export Manager", "role": "sales / export", "confidence": "search snippet", "source": "s"})
        filled = {}
        enrich_fields(res, "https://example-mills.test/", lambda f, v, s, b: filled.__setitem__(f, v) if v else None)
        self.assertIn("wa.me/905321112244", filled["whatsapp_links"])
        self.assertEqual(filled["founded"], "1987")
        self.assertEqual(filled["size_band"], "mid")
        self.assertIn("Anna Kowalska", filled["people_site"])
        self.assertNotIn("people_search", filled)  # off until measured
        cells = ck.profile_cells(res)
        self.assertEqual(len(cells), 10)
        self.assertNotIn("Ali Demir", cells[2])


class Precision(unittest.TestCase):
    """Cases found in the hand-checked sample (12 Nov 2026), rebuilt with invented names."""

    def test_people_noise(self):
        team = "<h3>Press Releases</h3><p>Chairman</p><h3>Karl Muster Hans Beispiel</h3><p>CEO</p><h3>中文</h3><p>President</p><h3>Lena Roth</h3><p>Non-Executive Director</p>"
        self.assertEqual(cp.people_on([("https://x.test/team", team)]), [])
        cust = "<h3>Paul Kunde</h3><p>General Manager of Other Co</p>"
        self.assertEqual(cp.people_on([("https://x.test/about-us/our-customers/", cust)]), [])

    def test_whatsapp_national_link(self):
        wa = cp.whatsapp_on([], ["+912345678"], "PRT")
        self.assertEqual([x["number"] for x in wa], ["+351912345678"])

    def test_founded_strict(self):
        page = "<p>Our milestones</p><p>1926</p><p>Product line since 2019.</p><p>Created</p><p>2018</p>"
        self.assertNotIn("founded", cp.profile_on([("https://x.test/about", page)]))
        self.assertEqual(cp.profile_on([("https://x.test/", "<p>Founded in March 1951 in Lyon.</p>")])["founded"]["value"], 1951)

    def test_press_case_and_junk(self):
        items = [{"title": "Spike in bird flu at Australian agricultural show", "outlet": "x", "outlet_url": "", "url": "a", "date": ""},
                 {"title": "Example Agricultural Company (EAC.AX) Stock Price, News, Quote & History", "outlet": "y", "outlet_url": "", "url": "b", "date": ""},
                 {"title": "Example Agricultural Company posts record profit", "outlet": "z", "outlet_url": "", "url": "c", "date": ""}]
        self.assertEqual([g["url"] for g in cp.press_filter(items, "Example Agricultural Company", ["Australia"])], ["c"])
