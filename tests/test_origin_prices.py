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
print("origin prices: all passed")
