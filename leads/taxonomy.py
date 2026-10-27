"""Commodity groups that link the tracker (HS codes) to procurement classifications.

Each group:
  hs     HS chapters (2 digits) the group covers in the Master tab
  cpv    EU CPV codes (TED). A notice is assigned to the group with the longest matching CPV prefix.
  wb     World Bank procurement keywords (goods notices only)
  mr     mr.gov.il (Israel Government Procurement Administration) category codes
  ref    Master rows used as the headline price benchmark for the group
"""
GROUPS = [
    {"id": "MEAT", "name": "Meat & livestock", "hs": ["01", "02", "05", "16"],
     "cpv": ["15100000", "03320000"], "wb": ["meat", "livestock"], "mr": ["ZD160003", "ZD020001"], "ref": [53, 55]},
    {"id": "FISH", "name": "Fish & seafood", "hs": ["03"],
     "cpv": ["03310000", "15200000"], "wb": ["fish"], "mr": [], "ref": []},
    {"id": "DAIRY", "name": "Dairy & eggs", "hs": ["04"],
     "cpv": ["15500000", "03142500"], "wb": ["milk powder", "dairy"], "mr": ["ZD160003"], "ref": [56]},
    {"id": "FRUITVEG", "name": "Fruit, vegetables & nuts", "hs": ["07", "08", "20"],
     "cpv": ["03220000", "15300000"], "wb": ["vegetables", "fruits"], "mr": ["ZD160006"], "ref": [51]},
    {"id": "GRAIN", "name": "Cereals, rice & flour", "hs": ["10", "11", "19"],
     "cpv": ["03211000", "03210000", "15600000"], "wb": ["wheat", "maize", "rice", "flour", "grain"],
     "mr": ["ZD160007"], "ref": [33, 36, 40]},
    {"id": "OILSEED", "name": "Oilseeds, vegetable oils & fats", "hs": ["12", "15"],
     "cpv": ["03111000", "15400000"], "wb": ["vegetable oil", "edible oil", "seeds"], "mr": ["ZD020003"],
     "ref": [37, 39, 44]},
    {"id": "SOFTS", "name": "Sugar, coffee, tea, cocoa & spices", "hs": ["09", "17", "18"],
     "cpv": ["15830000", "15840000", "15860000", "15870000"], "wb": ["sugar", "coffee", "tea"], "mr": [],
     "ref": [48, 45, 47]},
    {"id": "FEED", "name": "Animal feed", "hs": ["23"],
     "cpv": ["15700000"], "wb": ["animal feed", "fodder"], "mr": ["ZD020004"], "ref": [38]},
    {"id": "BEVTOB", "name": "Beverages & tobacco", "hs": ["22", "24"],
     "cpv": ["15900000"], "wb": [], "mr": [], "ref": []},
    {"id": "FUEL", "name": "Fuels & energy", "hs": ["27"],
     "cpv": ["09100000", "09200000"], "wb": ["diesel", "fuel", "coal", "LPG", "bitumen", "lubricants"],
     "mr": ["ZD03", "ZD030001", "ZD030002", "ZD030003"], "ref": [2, 9, 10, 11]},
    {"id": "MINERAL", "name": "Minerals, cement, aggregates & glass", "hs": ["25", "26", "68", "70"],
     "cpv": ["14200000", "14300000", "14400000", "14500000", "14600000", "44111000", "44114000", "44113000"],
     "wb": ["cement", "aggregates", "ballast", "salt", "lime", "bitumen"],
     "mr": ["ZD060002", "ZD060005", "ZD060007", "ZD19"], "ref": [15]},
    {"id": "CHEM", "name": "Chemicals", "hs": ["28", "29", "38"],
     "cpv": ["24100000", "24200000", "24300000", "24900000"],
     "wb": ["chemicals", "chlorine", "aluminium sulphate", "reagents"], "mr": ["ZD08", "ZD070001"], "ref": []},
    {"id": "FERT", "name": "Fertilizers", "hs": ["31"],
     "cpv": ["24400000"], "wb": ["fertilizer", "urea"], "mr": ["ZD020003"], "ref": []},
    {"id": "PLASTIC", "name": "Plastics & rubber", "hs": ["39", "40"],
     "cpv": ["24500000", "19500000"], "wb": ["polyethylene", "plastic", "rubber"], "mr": ["ZD05"], "ref": [57]},
    {"id": "WOODPAPER", "name": "Wood, pulp & paper", "hs": ["44", "47", "48"],
     "cpv": ["03410000", "03419000", "30197600"], "wb": ["timber", "paper"], "mr": ["ZD14", "ZD070010", "ZD060020"],
     "ref": [52]},
    {"id": "TEXTILE", "name": "Textiles, fibres & hides", "hs": ["41", "50", "51", "52", "53", "54", "55"],
     "cpv": ["19100000", "19200000", "19400000"], "wb": ["cotton", "fabric", "yarn"],
     "mr": ["ZD72", "ZD190006", "ZD070002"], "ref": [50]},
    {"id": "STEEL", "name": "Iron & steel", "hs": ["72", "73"],
     "cpv": ["14710000", "44330000", "44170000", "44160000"],
     "wb": ["steel", "rebar", "reinforcement bars", "steel pipes", "rails"], "mr": ["ZD070003", "ZD060014"],
     "ref": [31]},
    {"id": "NONFERROUS", "name": "Non-ferrous metals", "hs": ["74", "75", "76", "78", "79", "80", "81"],
     "cpv": ["14700000", "14720000", "14730000"], "wb": ["copper", "aluminium", "zinc"], "mr": [],
     "ref": [21, 22, 23]},
    {"id": "PRECIOUS", "name": "Precious metals & stones", "hs": ["71"],
     "cpv": [], "wb": [], "mr": [], "ref": [17, 18]},
]
BY_ID = {g["id"]: g for g in GROUPS}
CH2GROUP = {ch: g["id"] for g in GROUPS for ch in g["hs"]}


def group_of_cpv(codes):
    """Most specific group for a list of CPV codes (longest prefix match of the group's CPV)."""
    best, blen = None, -1
    for c in codes:
        c = str(c)[:8]
        for g in GROUPS:
            for gc in g["cpv"]:
                p = gc.rstrip("0")
                if c.startswith(p) and len(p) > blen:
                    best, blen = g["id"], len(p)
    return best
