"""Sandbox workflows: white maize color, RO vs automotive filters, contacts, RFQ drafts only for supported fits."""
from leads import workflow_demo as w

rows = [
    {"supplier": "Grain SA", "country": "ZAF", "products": "white maize grade 1, non-GMO", "email": "sales@grainsa.co.za", "phone": "", "website": "https://grainsa.co.za", "quality": "50", "type": "goods supplier"},
    {"supplier": "Yellow Co", "country": "ARG", "products": "yellow maize, soybeans", "email": "info@yellowco.com.ar", "website": "", "quality": "60"},
    {"supplier": "Mill Ltd", "country": "KEN", "products": "maize flour, maize meal", "email": "x", "website": "", "quality": "70"},
    {"supplier": "Corn Trade", "country": "UKR", "products": "corn, wheat, barley", "email": "", "phone": "", "website": "", "quality": "40"},
    {"supplier": "AquaRO", "country": "ISR", "products": "industrial reverse osmosis plants, desalination", "email": "sales@aquaro.co.il", "website": "https://aquaro.co.il", "quality": "50"},
    {"supplier": "Filtro", "country": "TUR", "products": "oil filters, air filters for trucks", "email": "info@filtro.com.tr", "website": "", "quality": "80"},
]
req = {"id": "A", "label": "white maize", "buyer_country": "KEN", "qty": "1 t", "spec": "s", "incoterm": "CFR"}
a, sa, na = w.shortlist(rows, "maize", {"product_family": "maize", "color": "white", "form": "grain"}, req)
names = {r[1]: r for r in a}
assert names["Grain SA"][4] == "supported" and names["Grain SA"][11].startswith("Subject:"), names.get("Grain SA")
assert "Yellow Co" not in names and sa.get("incompatible") == 1, sa  # yellow evidenced, white required
assert "Mill Ltd" not in names  # flour is not grain: no maize assertion -> research
assert names["Corn Trade"][4] == "plausible" and names["Corn Trade"][10] == "no" and not names["Corn Trade"][11]
assert "not an order or a commitment" in names["Grain SA"][11]
c, sc, nc = w.shortlist(rows, "reverse osmosis system", {"product_family": "reverse osmosis system"}, req)
cn = {r[1]: r for r in c}
assert cn["AquaRO"][4] == "supported" and "Filtro" not in cn and sc.get("incompatible") == 1, (cn, sc)
print("workflow demo: all passed")
