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
     "mr": ["ZD060002", "ZD060005", "ZD060007", "ZD19"], "ref": [808, 791]},
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
SUP = {'MEAT': '\\b(meat|beef|pork|poultry|chicken|mutton|lamb|veal|livestock|cattle|halal)\\b|בשר|עופות',
       'FISH': '\\b(fish|seafood|shrimps?|prawns?|tuna|salmon|squid|sardines?)\\b|דגים',
       'DAIRY': '\\b(dairy|milk|cheese|butter|whey|eggs?|lactose|casein)\\b|חלב|גבינ|ביצים',
       'FRUITVEG': '\\b(fruits?|vegetables?|onions?|potato(es)?|garlic|citrus|dates|nuts|cashews?|almonds?|raisins|avocados?|bananas?)\\b|פירות|ירקות',
       'GRAIN': '\\b(rice|wheat|maize|corn|flour|barley|sorghum|grains?|cereals?|pulses|lentils|chickpeas|oats|millet)\\b|אורז|חיטה|קמח|דגנים',
       'OILSEED': '\\b(sesame|soybeans?|soya|sunflower|palm oil|vegetable oils?|edible oils?|oilseeds?|groundnuts?|peanuts?|rapeseed|canola|olive oil)\\b|שומשום|שמן',
       'SOFTS': '\\b(sugar|coffee|tea|cocoa|spices?|pepper|cardamom|turmeric|cinnamon|cloves|ginger|vanilla|saffron|honey)\\b|סוכר|קפה|תבלינ',
       'FEED': '\\b(animal feed|fodder|soybean meal|fish ?meal|ddgs|alfalfa|feed additives?|livestock feed)\\b|מספוא',
       'BEVTOB': '\\b(beverages?|juices?|tobacco|wine|beer|spirits)\\b|משקאות|טבק',
       'FUEL': '\\b(diesel|gasoil|fuel oil|petroleum|crude oil|lpg|lng|bitumen|asphalt|coal|petcoke|jet fuel|gasoline|petrochemicals?|lubricants?|base oil)\\b|דלק|סולר|ביטומן|פחם',
       'MINERAL': '\\b(cement|clinker|aggregates?|gravel|limestone|gypsum|salt|kaolin|glass|ceramics?|marble|granite|minerals?|iron ore|bentonite|silica)\\b|מלט|צמנט|זכוכית|מחצב',
       'CHEM': '\\b(chemicals?|caustic soda|soda ash|sulphur|sulfur|sulphuric|acids?|methanol|ammonia|chlorine|dyes?|pigments?|solvents?|resins?|activated carbon|titanium dioxide)\\b|כימיק|גופרית|חומצ',
       'FERT': '\\b(fertili[sz]ers?|urea|dap|npk|potash|ammonium nitrate|ammonium sulphate|phosphates?)\\b|דשנ',
       'PLASTIC': '\\b(plastics?|polymers?|polyethylene|pvc|hdpe|ldpe|polypropylene|pet resin|rubber|latex|masterbatch)\\b|פלסטיק|גומי|פולימר',
       'WOODPAPER': '\\b(timber|lumber|wood|plywood|pulp|paper|kraft|cardboard|cartons?|mdf)\\b|נייר|קרטון|עצים',
       'TEXTILE': '\\b(cotton|yarns?|fabrics?|textiles?|fibres?|fibers?|jute|wool|leather|hides|coir|polyester)\\b|טקסטיל|כותנה',
       'STEEL': '\\b(steel|iron|rebars?|billets?|hrc|crc|wire rods?|scrap metal|pig iron|ferro|ferroalloys?|stainless)\\b|פלדה|ברזל|גרוטאות',
       'NONFERROUS': '\\b(copper|aluminium|aluminum|zinc|nickel|refined lead|lead ingots?|tin ingots?|cobalt|lithium|magnesium|titanium|tungsten|molybdenum|non-ferrous|cathodes?|ingots?)\\b|נחושת|אלומיניום|אבץ|ניקל',
       'PRECIOUS': '\\b(gold|silver|platinum|palladium|diamonds?|gemstones?)\\b|זהב|יהלומ'}
KW_EXTRA = {
    "MEAT": ["beef", "pork", "poultry", "chicken", "mutton"], "FISH": ["seafood", "tuna", "salmon"],
    "DAIRY": ["milk", "cheese", "butter", "eggs"], "FRUITVEG": ["fruit", "potatoes", "onions"],
    "GRAIN": ["corn", "oats"], "OILSEED": ["cooking oil", "soybean", "sunflower oil"],
    "SOFTS": ["spices", "cocoa"], "FEED": ["hay", "livestock feed"],
    "FUEL": ["gasoline", "jet fuel", "JP-8", "propane", "heating oil", "asphalt", "natural gas"],
    "MINERAL": ["gravel", "sand", "road salt", "limestone", "crushed stone", "glass"],
    "CHEM": ["caustic soda", "sodium hypochlorite", "sulfuric acid", "ferric chloride", "methanol", "polymer"],
    "FERT": ["fertiliser", "potash", "ammonium nitrate"], "PLASTIC": ["plastic resin", "HDPE", "PVC resin"],
    "WOODPAPER": ["lumber", "plywood", "pulp"], "TEXTILE": ["fabric", "leather", "wool"],
    "STEEL": ["steel plate", "steel bar", "stainless steel", "structural steel", "scrap metal"],
    "NONFERROUS": ["aluminum", "nickel", "titanium", "copper wire", "copper cathode"],
    "PRECIOUS": ["gold", "silver", "platinum"],
}
for _g in GROUPS:
    _g["sup"] = SUP.get(_g["id"], "")
    _g["kw"] = list(dict.fromkeys(_g["wb"] + KW_EXTRA.get(_g["id"], [])))
BY_ID = {g["id"]: g for g in GROUPS}
CH2GROUP = {ch: g["id"] for g in GROUPS for ch in g["hs"]}


def match_cpv(codes):
    """(group id, matched prefix length) for a list of CPV codes."""
    best, blen = None, -1
    for c in codes:
        c = str(c)[:8]
        for g in GROUPS:
            for gc in g["cpv"]:
                p = gc.rstrip("0")
                if c.startswith(p) and len(p) > blen:
                    best, blen = g["id"], len(p)
    return best, blen


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


import re as _re
_KW_RX = [(g["id"], _re.compile(r"\b(" + "|".join(_re.escape(k) for k in sorted(g["kw"], key=len, reverse=True)) + r")s?\b", _re.I))
          for g in GROUPS if g["kw"]]
NOISE = _re.compile(r"\b(injector|pump|filter|valve|hose|gauge|nozzle|assembly|kit|parts?|seal|gasket|sensor|"
                    r"vehicle|truck|services?|consult|maintenance|repair|software|training|study|design|"
                    r"construction|installation|equipment|dispenser|tank|meter|card|engines?|engi|guard|power suppl\w*|"
                    r"barriers?|couplings?|motors?|generators?|batter\w*|electronic|modules?|brackets?|masks?|gloves|"
                    r"aprons)\b", _re.I)


def group_of_text(text):
    """Commodity group for a tender title by keyword, or None (noise words exclude)."""
    if not text or NOISE.search(text):
        return None
    for gid, rx in _KW_RX:
        if rx.search(text):
            return gid
    return None
