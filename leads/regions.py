"""Country -> trade region (destination regions used by the Deal Desk freight table)."""
REGIONS = {
    "Europe": "ALB AND AUT BEL BGR BIH BLR CHE CYP CZE DEU DNK ESP EST FIN FRA GBR GRC HRV HUN IRL ISL ITA LIE LTU LUX LVA "
              "MCO MDA MKD MLT MNE NLD NOR POL PRT ROU SRB SVK SVN SWE UKR XKX",
    "Israel": "ISR",
    "Middle East & North Africa": "ARE BHR DZA EGY IRN IRQ JOR KWT LBN LBY MAR OMN PSE QAT SAU SYR TUN TUR YEM",
    "Sub-Saharan Africa": "AGO BDI BEN BFA BWA CAF CIV CMR COD COG COM CPV DJI ERI ETH GAB GHA GIN GMB GNB GNQ KEN LBR LSO MDG "
                          "MLI MOZ MRT MUS MWI NAM NER NGA RWA SDN SEN SLE SOM SSD STP SWZ SYC TCD TGO TZA UGA ZAF ZMB ZWE",
    "North America": "USA CAN MEX",
    "Latin America": "ARG BOL BRA CHL COL CRI CUB DOM ECU GTM HND HTI JAM NIC PAN PER PRY SLV TTO URY VEN BHS BRB BLZ GUY SUR",
    "South Asia": "AFG BGD BTN IND LKA MDV NPL PAK",
    "East Asia": "CHN HKG JPN KOR MAC MNG PRK TWN",
    "Southeast Asia": "BRN IDN KHM LAO MMR MYS PHL SGP THA TLS VNM",
    "CIS & Central Asia": "ARM AZE GEO KAZ KGZ RUS TJK TKM UZB",
    "Oceania": "AUS NZL PNG FJI",
}
ISO3_REGION = {c: r for r, s in REGIONS.items() for c in s.split()}
NAME_ISO3 = {
    "united kingdom": "GBR", "united states": "USA", "usa": "USA", "china": "CHN", "china, hong kong sar": "HKG",
    "rep. of korea": "KOR", "republic of korea": "KOR", "korea, rep.": "KOR", "russian federation": "RUS", "türkiye": "TUR",
    "turkey": "TUR", "viet nam": "VNM", "iran": "IRN", "united rep. of tanzania": "TZA", "tanzania": "TZA",
    "dem. rep. of the congo": "COD", "congo": "COG", "côte d'ivoire": "CIV", "bolivia (plurinational state of)": "BOL",
    "venezuela": "VEN", "rep. of moldova": "MDA", "czechia": "CZE", "lao people's dem. rep.": "LAO",
    "netherlands": "NLD", "other asia, nes": "TWN", "taiwan": "TWN", "saudi arabia": "SAU", "united arab emirates": "ARE",
    "north macedonia": "MKD", "bosnia herzegovina": "BIH", "state of palestine": "PSE", "syria": "SYR",
}


def iso3(name_or_code):
    s = (name_or_code or "").strip()
    if len(s) == 3 and s.isupper():
        return s
    k = s.lower()
    if k in NAME_ISO3:
        return NAME_ISO3[k]
    try:
        import pycountry
        return pycountry.countries.lookup(s).alpha_3
    except Exception:  # noqa: BLE001
        try:
            import pycountry
            return pycountry.countries.search_fuzzy(s)[0].alpha_3
        except Exception:  # noqa: BLE001
            return ""


def region(name_or_code):
    return ISO3_REGION.get(iso3(name_or_code), "Other")
