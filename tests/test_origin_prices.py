"""Physical prices by origin: number formats, unit and currency conversion, and that nothing is invented."""
from leads import origin_prices as o

assert o.num("$316.519,00") == 316519.0 and o.num("206,00") == 206.0 and o.num("2,020,000") == 2020000.0 and o.num("292.56") == 292.56
assert o.num("N.A.") is None and o.num("") is None
rates = {"USD": 1.0, "ETB": 125.0, "INR": 84.0}
r = o.row("ecx", "Coffee - ECX Local Washed (LW)", "Coffee Arabica", 13000.0, "ETB", "feresula (17 kg)", 17, "2026-09-01", "ECX", "u", origin="ETH")
f = o.finish(r, rates, "test", "2026-11-08")
assert abs(float(f["price_usd"]) - 104.0) < 0.01 and abs(float(f["price_usd_t"]) - 104.0 / 17 * 1000) < 0.5, f
assert f["origin"] == "ETH" and f["date"] == "2026-09-01" and f["fetched"] == "2026-11-08" and f["id"].startswith("O:")
u = o.finish(o.row("uganda", "Coffee Robusta - Uganda Screen 18", "Coffee Robusta", 185.63, "USc", "lb", 0.453592, "2026-11-06", "UCDA", "u"), rates, "t", "x")
assert abs(float(u["price_usd"]) - 1.8563) < 1e-6 and abs(float(u["price_usd_t"]) - 4092.4) < 1, u
n = o.finish(o.row("x", "Thing", "Thing", 5.0, "XXX", "kg", 1, "2026-01-01", "s", "u"), rates, "t", "x")
assert n["price_usd"] == "", "an unknown currency gives no USD price rather than a guess"
w = o.finish(o.row("drewry", "Container freight - WCI", "Container freight", 4389.0, "USD", "40ft container", None, "2026-11-05", "Drewry", "u"), rates, "t", "x")
assert w["price_usd_t"] == "" and w["physical"] == "false"
# batch 2 parsers, on cut-down copies of the real pages
mp = "title: { text: 'MALAYSIA PRICES OF CRUDE PALM OIL-2026' } categories: [ 'Nov 04', 'Nov 05', ] series: [{ data: [ 4292.00, 4204.50, ] }]"
assert o.parse_mpob(mp) == (4204.5, "2026-11-05")
dt = ("Dry Date Range DAP MAP POTASH UREA Sep 28-Oct 2 2026 934 974 499 683 Oct 26-30 2026 941 987 510 669 "
      "Liquid Date Range 10-34-0 ANHYD UAN28 UAN32 Aug 31-Sep 4 2026 717 938 423 455 Todd Neeley")
got = o.parse_dtn(dt)
assert ("UREA", 669.0, "2026-10-30") in got and ("UAN32", 455.0, "2026-09-04") in got and len(got) == 8, got
nc = ("By Kilimo News November 5, 2026 The Nairobi Coffee Exchange sold 1,131,513 kg of coffee at Sale 5 on Tuesday, 3 November. "
      "That works out to an average of US$296 per 50kg bag. The day's highest price went to Tegu factory's AA, lot 6023. Josra Coffee bought it at US$387.")
assert o.parse_nce(nc) == {"avg": 296.0, "date": "2026-11-03", "sale": "5", "top": ("AA", 387.0)}
cb = "28-OCT-2026 813 713 2,839 4,365 1181.07 1027.76 1307.02 1237.84\n04-NOV-2026 824 727 2,905 4,456 1174.33 998.93 1266.82 1206.02\nDecember"
assert o.parse_colombo(cb) == ("2026-11-04", {"High grown": 1174.33, "Medium grown": 998.93, "Low grown": 1266.82, "All elevations": 1206.02})
ah = "Price (&euro;/tonne) Sep-2026 Aug-2026 Monthly change Sep-2025 Annual change Butter 4,170 4,024 3.6% 6,337 -34.2% SMP 3,110 2,907 7.0% 2,303"
assert o.parse_ahdb(ah) == ("2026-09-01", {"Butter": 4170.0, "SMP": 3110.0})
assert o.parse_energy_charts({"unix_seconds": [1794092400 + 3600 * i for i in range(24)], "price": [100.0] * 23 + [124.0]}) == (101.0, "2026-11-08")
assert o.parse_energy_charts({"unix_seconds": [1794092400], "price": [100.0]}) is None, "a partial day is not a daily price"
assert o.parse_giacaphe("Giá cà phê hôm nay ngày 07/11/2026 Chia sẻ Trung bình 84,600 đ/kg 300") == (84600.0, "2026-11-07")
print("origin prices: all passed")
