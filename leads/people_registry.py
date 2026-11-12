"""probe (temporary scaffold, replaced below)"""
import json
import sys
import time

import requests

UA = "Mozilla/5.0 (compatible; SinderCompanyCheck/1.0; +https://github.com/etaram/commodity-feeder)"
PROBES = [
    ("CZ vr small", "GET", "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty-vr/03479919", None),
    ("SK entity", "GET", "https://api.statistics.sk/rpo/v1/entity/1003617?showHistoricalData=false&showOrganizationUnits=false", None),
    ("PL krs spzoo", "GET", "https://api-krs.ms.gov.pl/api/krs/OdpisAktualny/0000140528?rejestr=P&format=json", None),
    ("FR id", "GET", "https://recherche-entreprises.api.gouv.fr/search?q=542051180&per_page=2", None),
    ("FR name", "GET", "https://recherche-entreprises.api.gouv.fr/search?q=danone&per_page=5", None),
    ("NO unit", "GET", "https://data.brreg.no/enhetsregisteret/api/enheter/923609016", None),
    ("NO roles", "GET", "https://data.brreg.no/enhetsregisteret/api/enheter/923609016/roller", None),
    ("NO name", "GET", "https://data.brreg.no/enhetsregisteret/api/enheter?navn=equinor&size=5", None),
    ("CZ name", "POST", "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/vyhledat", {"obchodniJmeno": "ČEZ", "pocet": 5}),
    ("PL krs", "GET", "https://api-krs.ms.gov.pl/api/krs/OdpisAktualny/0000028860?rejestr=P&format=json", None),
    ("PL wl", "GET", "https://wl-api.mf.gov.pl/api/search/nip/7740001454?date=" + time.strftime("%Y-%m-%d"), None),
    ("FI id", "GET", "https://avoindata.prh.fi/opendata-ytj-api/v3/companies?businessId=0112038-9", None),
    ("BR brasilapi", "GET", "https://brasilapi.com.br/api/cnpj/v1/33000167000101", None),
    ("BR minhareceita", "GET", "https://minhareceita.org/33000167000101", None),
    ("SK rpo", "GET", "https://api.statistics.sk/rpo/v1/search?identifier=31322832", None),
    ("EE autocomplete", "GET", "https://ariregister.rik.ee/est/api/autocomplete?q=eesti%20energia", None),
    ("GB no key", "GET", "https://api.company-information.service.gov.uk/company/00102498/officers", None),
    ("DK cvr dist", "GET", "http://distribution.virk.dk/cvr-permanent/virksomhed/_search", None),
]


def probe(out):
    s = requests.Session()
    s.headers["User-Agent"] = UA
    res = {}
    for lab, m, u, body in PROBES:
        try:
            r = s.post(u, json=body, timeout=25) if m == "POST" else s.get(u, timeout=25)
            res[lab] = {"status": r.status_code, "ctype": r.headers.get("content-type", ""), "body": r.text[:120000],
                        "rl": {k: v for k, v in r.headers.items() if "limit" in k.lower() or "retry" in k.lower()}}
            print(lab, r.status_code, len(r.text))
        except Exception as e:  # noqa: BLE001
            res[lab] = {"error": type(e).__name__}
            print(lab, "error", type(e).__name__)
        time.sleep(1)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)


if __name__ == "__main__":
    probe(sys.argv[2])
