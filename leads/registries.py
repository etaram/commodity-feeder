"""Official exporter registries and directories of origin countries, each read from the authority's own publication.

  cameroon   National Cocoa and Coffee Board (ONCC): the list of active cocoa and coffee exporters for the year, with phone
             and e-mail (a public PDF linked from oncc.cm/exporters)
  nigeria    Nigerian Export Promotion Council: the "find your supplier" directory for importers (name, products, size,
             certifications, description)

Each registry writes data/leads/registry_<country>.csv with the same columns, and leads/webindex.py puts the rows into the
supplier index: an official registry entry is proof of licence or registration (tier 2), a promotion-council listing is
the company's own profile (tier 3). An empty or failed read never replaces the last good file.

  python -m leads.registries
"""
import csv
import io
import json
import re
from datetime import date

import requests

from .common import LEADS, log

UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)", "Accept-Language": "en"}
FIELDS = ["supplier", "country", "product", "role", "licence", "contact_person", "phone", "email", "website", "description", "size", "certifications", "source", "source_url", "fetched"]


def _name(s):
    s = re.sub(r"\s+", " ", s).strip()
    return s.title().replace("Sarl", "SARL").replace("Sa ", "SA ").replace("Ltd", "Ltd").replace("Plc", "PLC") if s.isupper() else s


def cameroon():
    import pdfplumber
    h = requests.get("https://oncc.cm/exporters", headers=UA, timeout=40).text
    m = re.search(r'href="(/resources/list-of-active-cocoa[^"]*)"', h)
    if not m:
        return []
    h2 = requests.get("https://oncc.cm" + m.group(1), headers=UA, timeout=40).text
    pdf = re.search(r'href="(https://oncc\.cm/content/library/documents/[^"]+\.pdf)"', h2)
    year = re.search(r"Exporters (\d{4})", h2)
    if not pdf:
        return []
    r = requests.get(pdf.group(1), headers=UA, timeout=60)
    out = []
    with pdfplumber.open(io.BytesIO(r.content)) as d:
        for pg in d.pages:
            for tb in pg.extract_tables():
                for rowx in tb:
                    if not rowx or not rowx[0] or rowx[0].strip().upper() in ("EXPORTERS", ""):
                        continue
                    name = re.sub(r"\s+", " ", rowx[0]).strip()
                    phone = re.sub(r"\s+", " ", (rowx[1] or "")).strip() if len(rowx) > 1 else ""
                    email = (rowx[2] or "").strip() if len(rowx) > 2 else ""
                    if len(name) < 3:
                        continue
                    coop = bool(re.search(r"COOP|SCOOP|UNION|FARM", name, re.I))
                    out.append({"supplier": _name(name), "country": "CMR", "product": "cocoa, coffee", "role": "producer cooperative and exporter" if coop else "exporter",
                                "licence": f"active cocoa and coffee exporter {year.group(1) if year else ''}".strip(), "contact_person": "", "phone": ("+237 " + phone) if phone and not phone.startswith("+") else phone,
                                "email": email if "@" in email else "", "website": "", "description": "Licensed exporter of cocoa and coffee (National Cocoa and Coffee Board register)", "size": "", "certifications": "",
                                "source": "National Cocoa and Coffee Board of Cameroon (ONCC): list of active exporters", "source_url": "https://oncc.cm/exporters", "fetched": date.today().isoformat()})
    return out


def nigeria():
    h = requests.get("https://nepc.gov.ng/importer/find-your-supplier/", headers=UA, timeout=40).text
    t = re.sub(r"(\|\s*)+", "| ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S))))
    t = t.replace("&#8217;", "'").replace("&amp;", "&").replace("&nbsp;", " ").replace("&#8230;", "...")
    out = []
    for m in re.finditer(r"\| ([A-Z][^|]{3,70}?) \| (?:Certifications: \| ([^|]+?) \| )?Size: \| ([^|]+?) \| ([^|]{30,}?)\| READ MORE", t):
        name, certs, size, desc = m.group(1).strip(), (m.group(2) or "").strip(), m.group(3).strip(), m.group(4).strip()
        prods = ", ".join(p for p in ("cashew", "cocoa", "sesame", "ginger", "beans", "leather", "shea", "hibiscus", "soybean") if re.search(p, desc, re.I)) or "agricultural products"
        out.append({"supplier": name, "country": "NGA", "product": prods, "role": "exporter", "licence": "NEPC supplier directory", "contact_person": "", "phone": "", "email": "", "website": "",
                    "description": desc[:260], "size": size, "certifications": certs, "source": "Nigerian Export Promotion Council: find your supplier", "source_url": "https://nepc.gov.ng/importer/find-your-supplier/",
                    "fetched": date.today().isoformat()})
    return out


REGISTRIES = {"cameroon": cameroon, "nigeria": nigeria}


def main():
    LEADS.mkdir(parents=True, exist_ok=True)
    rep = {}
    for key, fn in REGISTRIES.items():
        try:
            rows = fn()
        except Exception as e:  # noqa: BLE001
            log.warning("registry %s: %s", key, str(e)[:120]); rows = []
        if len(rows) >= 5:
            with open(LEADS / f"registry_{key}.csv", "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
        rep[key] = {"rows": len(rows), "with_email": sum(1 for r in rows if r["email"]), "with_phone": sum(1 for r in rows if r["phone"])}
    print("registries:", json.dumps(rep))


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    main()
