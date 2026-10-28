"""Universal sector taxonomy: every notice from every source is mapped to one of ~22 sectors that together
cover the whole economy. Mapping uses official codes first (CPV, UNSPSC, source-specific activity codes) and a
multilingual keyword fallback only when a source has no codes. Commodity groups (taxonomy.py) remain a finer
layer for goods that have price benchmarks.
"""
import re

SECTORS = {
    "AGRI_FOOD": "Agriculture & food",
    "ENERGY": "Energy, fuels & utilities",
    "POWER": "Power & electrical equipment",
    "MINING_METALS": "Mining, minerals & metals",
    "CHEMICALS": "Chemicals & plastics",
    "TEXTILES": "Textiles, apparel & leather",
    "CONSTR_MAT": "Construction materials & building systems",
    "BUILDING": "Building construction works",
    "INFRA": "Transport & civil infrastructure works",
    "WATER": "Water & wastewater",
    "MACHINERY": "Industrial & construction machinery",
    "TRANSPORT_EQ": "Vehicles, rolling stock, ships & aircraft",
    "DEFENCE": "Defence & security",
    "HEALTH": "Healthcare & pharmaceuticals",
    "LAB": "Scientific & measuring instruments",
    "ICT": "ICT & telecom",
    "CONSUMER": "Furniture, appliances & consumer goods",
    "MAINT": "Repair, maintenance & installation",
    "LOGISTICS": "Transport & logistics services",
    "ENGINEERING": "Engineering & architecture services",
    "CONSULTING": "Consulting, business & financial services",
    "ENV_WASTE": "Environment, waste & cleaning",
    "SOCIAL": "Education, social & hospitality services",
}

# CPV: longest prefix wins. Division-level defaults plus finer overrides.
CPV = {
    "03": "AGRI_FOOD", "15": "AGRI_FOOD", "77": "AGRI_FOOD",
    "09": "ENERGY", "65": "ENERGY", "76": "ENERGY", "0931": "POWER", "0933": "POWER", "4112": "WATER",
    "31": "POWER", "4531": "POWER", "45251": "POWER", "452314": "POWER", "45255": "ENERGY",
    "14": "MINING_METALS",
    "24": "CHEMICALS", "195": "CHEMICALS",
    "18": "TEXTILES", "19": "TEXTILES",
    "44": "CONSTR_MAT", "4416": "WATER", "4461": "WATER",
    "45": "BUILDING", "4522": "INFRA", "4523": "INFRA", "4524": "WATER", "45232": "WATER", "452313": "WATER",
    "45252": "WATER", "45253": "WATER", "45259": "WATER", "41": "WATER", "4212": "WATER", "65": "ENERGY",
    "16": "MACHINERY", "42": "MACHINERY", "43": "MACHINERY",
    "34": "TRANSPORT_EQ",
    "35": "DEFENCE", "7522": "DEFENCE", "5064": "DEFENCE", "5065": "DEFENCE", "7971": "DEFENCE",
    "33": "HEALTH", "85": "HEALTH",
    "38": "LAB",
    "30": "ICT", "32": "ICT", "48": "ICT", "64": "ICT", "72": "ICT",
    "37": "CONSUMER", "39": "CONSUMER", "22": "CONSUMER",
    "50": "MAINT", "51": "MAINT",
    "60": "LOGISTICS", "63": "LOGISTICS",
    "71": "ENGINEERING",
    "66": "CONSULTING", "70": "CONSULTING", "73": "CONSULTING", "75": "CONSULTING", "79": "CONSULTING",
    "90": "ENV_WASTE", "9091": "ENV_WASTE",
    "55": "SOCIAL", "80": "SOCIAL", "92": "SOCIAL", "98": "SOCIAL",
}

UNSPSC = {
    "10": "AGRI_FOOD", "50": "AGRI_FOOD", "70": "AGRI_FOOD", "11": "MINING_METALS", "12": "CHEMICALS",
    "13": "CHEMICALS", "14": "CONSUMER", "15": "ENERGY", "71": "ENERGY", "83": "ENERGY", "20": "MACHINERY",
    "21": "MACHINERY", "22": "MACHINERY", "23": "MACHINERY", "24": "MACHINERY", "27": "MACHINERY",
    "31": "MACHINERY", "25": "TRANSPORT_EQ", "26": "POWER", "39": "POWER", "30": "CONSTR_MAT",
    "40": "CONSTR_MAT", "32": "ICT", "43": "ICT", "45": "ICT", "41": "LAB", "42": "HEALTH", "51": "HEALTH",
    "85": "HEALTH", "44": "CONSUMER", "48": "CONSUMER", "49": "CONSUMER", "52": "CONSUMER", "54": "CONSUMER",
    "55": "CONSUMER", "56": "CONSUMER", "46": "DEFENCE", "92": "DEFENCE", "47": "ENV_WASTE", "76": "ENV_WASTE",
    "77": "ENV_WASTE", "53": "TEXTILES", "60": "SOCIAL", "86": "SOCIAL", "90": "SOCIAL", "91": "SOCIAL",
    "72": "BUILDING", "95": "BUILDING", "73": "MAINT", "78": "LOGISTICS", "80": "CONSULTING", "82": "CONSULTING",
    "84": "CONSULTING", "93": "CONSULTING", "94": "CONSULTING", "81": "ENGINEERING",
}

# Multilingual keyword fallback (en, fr, es, pt). Ordered: specific sectors before generic ones.
KW = [
    ("DEFENCE", r"defen[cs]e|military|militar|armou?r|ammunition|munici[oó]n|weapon|arme|surveillance|radar|"
                r"night vision|uav|drones?|body armou?r|police equipment|ej[eé]rcito|ex[eé]rcito|arm[ée]e"),
    ("HEALTH", r"medic|hospital|h[oô]pital|pharma|f[aá]rmac|medicine|m[eé]dicament|vaccin|drug|syringe|seringue|"
               r"diagnos|x-ray|surgical|cirurg|quir[uú]rg|health|sant[eé]|salud|sa[uú]de|laborat[oó]rio cl"),
    ("WATER", r"water supply|drinking water|potable|wastewater|sewer|sewage|sanitation|assainissement|"
              r"saneamiento|saneamento|desalination|borehole|forage|irrigation|irrigaci|dam\b|barrage|"
              r"\beau\b|agua potable|[aá]gua|water treatment|pumping station"),
    ("POWER", r"electri|transformer|transformador|transformateur|substation|sub-station|subestaci|switchgear|"
              r"solar|photovolta|fotovolta|\bpv\b|power plant|centrale|generator|g[eé]n[eé]rat|gerador|"
              r"transmission line|distribution line|power line|energ[iy]a el[eé]|wind (farm|turbine)|"
              r"battery storage|bess|hydropower|hydro[- ]?electric|street ?light|[ée]clairage|luminaria"),
    ("INFRA", r"\broad|highway|route|carretera|rodovi|estrada|bridge|\bpont|puente|ponte|railway|rail\b|"
              r"ferrovi|airport|a[eé]roport|port\b|harbou?r|tunnel|pavement|paving|pavimenta|asphalt"),
    ("ENERGY", r"\bfuel|diesel|gasoil|petrol|gasoline|carburant|combustible|combust[ií]vel|lpg|lng|\bgas\b|"
               r"oil and gas|p[eé]trole|lubricant|coal\b|charbon"),
    ("ICT", r"\bict\b|software|logiciel|computer|ordinateur|computador|laptop|server|servidor|network|r[eé]seau|"
            r"\bred(es)?\b de datos|telecom|fib(re|er) optic|fibra [oó]ptica|data cent|internet|broadband|"
            r"digital|it equipment|information system|syst[eè]me d.information|sistema de informa"),
    ("TRANSPORT_EQ", r"vehicle|v[eé]hicule|veh[ií]culo|ve[ií]culo|truck|camion|cami[oó]n|ambulanc|\bbus(es)?\b|"
                     r"motorcycle|moto\b|locomotive|rolling stock|wagon|vessel|boat|bateau|barco|aircraft|helicop"),
    ("MACHINERY", r"machiner|machine|m[aá]quina|excavat|tractor|tracteur|grader|loader|bulldozer|crane|grue|"
                  r"gr[uú]a|pump|pompe|bomba|compressor|equipment for|heavy equipment|agricultural equipment|"
                  r"[ée]quipements? agricoles"),
    ("LAB", r"laborator|scientific|measuring|instrument|meteorolog|calibration|spectromet|microscop"),
    ("AGRI_FOOD", r"\bfood|aliment|seeds?\b|semence|semilla|semente|fertili|engrais|fertilizante|livestock|"
                  r"b[eé]tail|ganado|gado|wheat|maize|ma[iï]s|rice|\briz|arroz|flour|farin|harina|sugar|sucre|"
                  r"az[uú]car|a[cç][uú]car|vegetable oil|huile|aceite|[oó]leo|agri|fishing|p[eê]che|pesca|veterin"),
    ("CHEMICALS", r"chemical|chimique|qu[ií]mic|reagent|r[eé]actif|reactivo|reagente|chlorine|chlore|cloro|"
                  r"plastic|plastique|pl[aá]stico|polyethylene|resin"),
    ("TEXTILES", r"uniform|textile|t[eê]xtil|fabric|tissu|tela|clothing|v[eê]tement|vestuario|vestu[aá]rio|"
                 r"footwear|chaussure|calzado|cal[cç]ado|boots|leather|cuir|cuero|couro|tent|tente|blanket|couverture"),
    ("MINING_METALS", r"\bsteel|acier|acero|a[cç]o\b|rebar|iron ore|copper|cuivre|cobre|aluminium|aluminum|"
                      r"mining|minier|miner[ií]a|minera[cç]"),
    ("CONSTR_MAT", r"cement|ciment|cemento|cimento|aggregate|gravel|sand\b|brick|ladrillo|tijolo|pipes?\b|"
                   r"tuyau|tuber[ií]a|tubula|timber|roofing|construction material|mat[eé]riaux"),
    ("ENV_WASTE", r"waste|d[eé]chet|residuo|res[ií]duo|landfill|recycl|cleaning|nettoyage|limpieza|limpeza|"
                  r"environment|environnement|ambiental|climate|climat|clim[aá]tic"),
    ("CONSUMER", r"furniture|mobilier|mobiliario|mobili[aá]rio|appliance|electrodom|stationery|papeterie|"
                 r"papeler[ií]a|office supplies|fournitures de bureau|textbook|manuels scolaires|printing|impres"),
    ("BUILDING", r"construction|construcci[oó]n|constru[cç][aã]o|building|b[aâ]timent|edificio|edif[ií]cio|"
                 r"rehabilitation|r[eé]habilitation|rehabilitaci|reabilita|renovation|r[eé]novation|"
                 r"civil works|travaux|obras?\b|works\b|school|[eé]cole|escuela|escola|housing|logement|vivienda"),
    ("MAINT", r"maintenance|mantenimiento|manuten[cç]|repair|r[eé]paration|reparaci|repara[cç]|installation|"
              r"instalaci|instala[cç]"),
    ("LOGISTICS", r"transport services|freight|fret|flete|frete|logistic|log[ií]stic|shipping|courier|storage|"
                  r"warehous|entrep[oô]t|almac[eé]n|armaz[eé]m|travel|voyage|viaje|viagem"),
    ("ENGINEERING", r"engineering|ing[eé]nierie|ingenier[ií]a|engenharia|design|conception|dise[nñ]o|"
                    r"projeto|supervision|supervisi[oó]n|survey|topograph|feasibility|faisabilit|factibilidad|"
                    r"viabilidade|architect"),
    ("SOCIAL", r"training|formation|capacitaci[oó]n|capacita[cç]|education|[ée]ducation|educaci[oó]n|"
               r"educa[cç][aã]o|catering|restauration|hotel|event|[ée]v[eé]nement|evento|social"),
    ("CONSULTING", r"consult|advis|conseil|asesor|assessoria|audit|evaluation|[ée]valuation|evaluaci|"
                   r"avalia[cç]|study|[ée]tude|estudio|estudo|research|recherche|investigaci|pesquisa|"
                   r"insurance|assurance|seguro|financial|legal|juridique|jur[ií]dic|marketing|communication|"
                   r"recruitment|individual contractor|expert"),
]
EXTRA = [
    ("ICT", r"cyber|informati|num[eé]rique|licen[cs]|ip/mpls|circuit card|synthesi[sz]er|telecommunicat|it services|"
            r"mesa de servicio|service desk|datenverarbeitung|edv|rechenzentr"),
    ("DEFENCE", r"vigilancia|seguridad privada|gardiennage|sicherheitsdienst|security guard|brandmelde|fire alarm|"
                r"police nationale|polic[eí]a|anti-terror|land mine|projectile"),
    ("HEALTH", r"d[eé]fibrillat|hygien|menstrual|vaccin|tierimpf|impfstoff|anthropom|paracet|amoxi|medizin"),
    ("ENERGY", r"p[eé]troli|petroleum products"),
    ("POWER", r"alumbrado|beleuchtung|onduleur|ups\b|אל פסק"),
    ("LAB", r"laboratoire|labor\b|labtronic|analy[sz]er"),
    ("TRANSPORT_EQ", r"viaturas|fahrzeug|taxi|fleet"),
    ("MACHINERY", r"valve|gland|motor|bolts?\b|bearing|gasket|\bseal|fastener|harness|refrigerat|compressor|"
                  r"hydraul|spare parts|ersatzteil|pi[eè]ces d[eé]tach"),
    ("SOCIAL", r"formation|insertion|accompagnement|culturel|mus[eé]e|restauration scolaire|crèche|animation"),
    ("BUILDING", r"travaux|toiture|[eé]tanch[eé]it|sanierung|neubau|umbau|r[eé]fection|mejoramiento|ampliaci[oó]n|corredor"),
    ("ENV_WASTE", r"reinigung|aseo|nettoyage|cenagoso|forest|biodivers|wetland"),
    ("CONSULTING", r"photograph|videograph|media monitoring|interpret|traducci|translation|fiducia|assur[ée]s sociaux|"
                   r"titres restaurant|arbeitssicherheit"),
    ("LOGISTICS", r"postal|acheminement|delivery services|maritime transport|sea transport|ocean transport|water transport|"
                  r"deep sea|coastal|inland water|shipping line|container (shipping|line|terminal)|port operat|"
                  r"terminal operat|stevedor|ship ?management|shipowner|ship owner|ship ?broker|chartering|tanker|"
                  r"bulk carrier|dry bulk|air cargo|air freight|cargo airline|trucking|truck transport|road transport|"
                  r"road freight|rail freight|freight rail|customs brok|freight forward|courier|towage|tugboat|"
                  r"bunker|warehousing|cold storage|3pl|third-party logistics|supply chain|transitaire|despachante|"
                  r"agente de carga|naviera|armador|transporte mar[ií]timo|transporte de carga"),
    ("CONSUMER", r"signage|beschilderung|electoral material|ear tags|kits"),
    ("AGRI_FOOD", r"ganader|apicult|beekeep|nursery|culinaire|\bfish|seafood|tuna\b|at[uú]n|thon\b|sardin|shrimp|prawn|"
                  r"crustacean|mollus|\bmeat|poultry|dairy|cheese|coffee|cocoa|cacao|\btea\b|fruit|vegetable|\bnuts?\b|"
                  r"cashew|spice|beverage|canned|cannery|frozen food|grain|cereal|oilseed|soybean|edible oil|bakery|"
                  r"confection|animal feed|slaughter|abattoir"),
    ("MINING_METALS", r"\bmetals?\b|ferro|zinc|nickel|\bores?\b|smelt|foundr|\bscrap|alloy|non-?ferrous|precious metal"),
    ("CONSTR_MAT", r"quarr|crushed stone|aggregates?\b|asphalt|bitumen|ready-?mix|concrete product|glass|ceramic"),
    ("ENERGY", r"\bcoal\b|\blng\b|\blpg\b|diesel|crude|\bfuels?\b|petroleum|refiner|natural gas"),
]
_KW = [(s, re.compile(rx, re.I)) for s, rx in EXTRA + KW]


def _prefix_lookup(code, table):
    code = re.sub(r"\D", "", str(code or ""))
    for n in range(len(code), 1, -1):
        s = table.get(code[:n])
        if s:
            return s
    return None


def from_cpv(codes):
    """Sector for a list of CPV codes (main code first)."""
    for c in codes or []:
        s = _prefix_lookup(str(c)[:8], CPV)
        if s:
            return s
    return None


def from_unspsc(code):
    return _prefix_lookup(str(code)[:8], UNSPSC)


def from_text(text):
    t = text or ""
    for s, rx in _KW:
        if rx.search(t):
            return s
    return None


def nature_of_cpv(codes):
    c = re.sub(r"\D", "", str((codes or [""])[0]))[:2]
    if not c:
        return ""
    return "works" if c == "45" else "services" if int(c) >= 50 else "goods"


def nature_of_sector(sector):
    if sector in ("BUILDING", "INFRA"):
        return "works"
    if sector in ("MAINT", "LOGISTICS", "ENGINEERING", "CONSULTING", "SOCIAL"):
        return "services"
    return "goods" if sector else ""


CPV_IN_TEXT = re.compile(r"\b(\d{8})-\d\b")


def cpv_in_text(text):
    """CPV codes quoted inside a title (e.g. Prozorro 'ДК 021:2015: 45450000-6')."""
    return CPV_IN_TEXT.findall(text or "")


def classify(text="", cpv=None, unspsc=None):
    """(sector id, method) using the most reliable scheme available."""
    s = from_cpv(cpv) if cpv else None
    if s:
        return s, "cpv"
    s = from_unspsc(unspsc) if unspsc else None
    if s:
        return s, "unspsc"
    inline = cpv_in_text(text)
    if inline:
        s = from_cpv(inline)
        if s:
            return s, "cpv"
    s = from_text(text)
    return (s, "keyword") if s else ("", "")
