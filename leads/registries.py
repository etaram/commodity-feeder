"""Official exporter registries and directories of origin countries, each read from the authority's own publication.

  cameroon   National Cocoa and Coffee Board (ONCC): the list of active cocoa and coffee exporters for the year, with phone
             and e-mail (a public PDF linked from oncc.cm/exporters)
  nigeria    Nigerian Export Promotion Council: the "find your supplier" directory for importers (name, products, size,
             certifications, description)
  pakistan   Rice Exporters Association of Pakistan member roll with each member's contact page
  iran       Iran Pistachio Association member lists (exporters, growers, service providers)
  vietnam    Vietnam Food Association member roll (rice exporters and millers)
  paraguay   CAPECO (grain and oilseed exporters' chamber) member list with contacts

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


def _clean(h):
    t = re.sub(r"(\|\s*)+", "| ", re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S))))
    return t.replace("&#8211;", "-").replace("&#8217;", "'").replace("&amp;", "&").replace("&nbsp;", " ")


def _previous(key):
    f = LEADS / f"registry_{key}.csv"
    return {r["supplier"]: r for r in csv.DictReader(open(f, encoding="utf-8"))} if f.exists() else {}


def pakistan():
    """Rice Exporters Association of Pakistan: the member roll (membership number, contact person, company), with the
    member's detail page read for phone, e-mail and website; detail pages are fetched 150 per run and kept between runs."""
    url = "https://www.reap.com.pk/memberProfile"
    h = requests.get(url, headers=UA, timeout=60).text
    prev = _previous("pakistan")
    out, fetched = [], 0
    for tr in re.findall(r"<tr.*?</tr>", h, flags=re.S):
        c = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x)).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)]
        link = re.search(r'href="(/memberDetails/\d+)"', tr)
        if len(c) < 3 or not re.match(r"\d-\d-\d{2}-\d{4}", c[0]) or c[2].upper() == "REAP":
            continue
        company, person = _name(c[2]), _name(c[1]).replace("Mr. ", "").replace("Mrs. ", "")
        r = prev.get(company) or {"supplier": company, "country": "PAK", "product": "rice (basmati and non-basmati)", "role": "exporter", "licence": f"REAP member {c[0]}",
                                  "contact_person": person, "phone": "", "email": "", "website": "", "description": "Member of the Rice Exporters Association of Pakistan (the statutory exporters' body)",
                                  "size": "", "certifications": "", "source": "Rice Exporters Association of Pakistan member roll", "source_url": url, "fetched": date.today().isoformat()}
        if r.get("email", "").lower().endswith("reap.com.pk"):
            r["email"] = ""; r["phone"] = r["phone"] if r["phone"].startswith("+") else ""
        if link and not (r["phone"] or r["email"]) and fetched < 150:
            try:
                d = requests.get("https://www.reap.com.pk" + link.group(1), headers=UA, timeout=30).text
                fetched += 1
                t = _clean(d)
                t = t.split("Head Office")[0]   # the association's own footer carries its phone and mailbox
                ems = [e for e in re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", t) if "reap.com.pk" not in e.lower()]
                ph = re.search(r"(\+92[\d\s-]{8,16}|0\d{2,3}[\s-]?\d{6,8})", t)
                webs = [w for w in re.findall(r"(?:www\.)[\w-]+\.[\w.-]+", t) if "reap" not in w]
                phone = ph.group(0).strip() if ph else ""
                r["email"], r["phone"], r["website"] = (ems[0] if ems else ""), ("+92 " + phone[1:] if phone.startswith("0") else phone), (webs[0] if webs else "")
                r["source_url"] = "https://www.reap.com.pk" + link.group(1)
                r["fetched"] = date.today().isoformat()
            except Exception:  # noqa: BLE001
                pass
        out.append(r)
    return out


def iran():
    """Iran Pistachio Association member lists (exporters, growers, service providers): company, phone, e-mail, website.
    The site pages further rows with a script, so each list's first page is what the association publishes to a reader."""
    out = []
    for cat, role in ((4, "exporter"), (1, "grower"), (5, "processor or service provider")):
        url = f"https://iranpistachio.org/en/members/view/form/catid/{cat}?catid={cat}"
        try:
            h = requests.get(url, headers=UA, timeout=40).text
        except Exception:  # noqa: BLE001
            continue
        for tr in re.findall(r"<tr.*?</tr>", h, flags=re.S):
            c = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x)).strip() for x in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)]
            if len(c) < 7 or c[0] == "Name":
                continue
            person, company, tel, _fax, mob, email, site = c[:7]
            name = company or person
            if not name:
                continue
            phone = ("+98 " + tel.lstrip("0")) if tel else (("+98 " + mob.lstrip("0")) if mob else "")
            out.append({"supplier": name, "country": "IRN", "product": "pistachio", "role": role, "licence": "Iran Pistachio Association member", "contact_person": person if company else "",
                        "phone": phone, "email": email if "@" in email else "", "website": site, "description": f"Iran Pistachio Association member ({role})", "size": "", "certifications": "",
                        "source": "Iran Pistachio Association member list", "source_url": url, "fetched": date.today().isoformat()})
    return out


def vietnam():
    """Vietnam Food Association member roll: the rice exporters, millers and food companies that make up the
    association (banks and associate members marked with * are left out), grouped north / centre / south."""
    url = "https://vietfood.org.vn/hoi-vien/danh-sach-hoi-vien/"
    h = requests.get(url, headers=UA, timeout=60).text
    m = re.search(r"<(main|article)", h)
    t = _clean(h[m.start():] if m else h)
    out, region = [], ""
    for seg in [x.strip() for x in t.split("|")]:
        if seg in ("MIỀN BẮC", "MIỀN TRUNG", "MIỀN NAM"):
            region = {"MIỀN BẮC": "north", "MIỀN TRUNG": "central", "MIỀN NAM": "south"}[seg]
            continue
        if not region or len(seg) < 8 or seg.endswith("*") or not re.match(r"^(CTY|TỔNG CTY|CÔNG TY|TỔNG CÔNG TY|DNTN|HTX|LIÊN HIỆP)", seg):
            continue
        if seg.startswith("NGÂN HÀNG"):
            continue
        name = re.sub(r"\s+", " ", seg).title().replace("Cty ", "Cty ").replace("Tnhh", "TNHH").replace("Xnk", "XNK").replace("Mtv", "MTV")
        out.append({"supplier": name, "country": "VNM", "product": "rice", "role": "exporter and miller", "licence": "Vietnam Food Association member", "contact_person": "", "phone": "", "email": "", "website": "",
                    "description": f"Member of the Vietnam Food Association (rice exporters' association), {region} Vietnam", "size": "", "certifications": "",
                    "source": "Vietnam Food Association member roll", "source_url": url, "fetched": date.today().isoformat()})
    return out


def paraguay():
    """CAPECO, the Paraguayan chamber of cereal and oilseed exporters and traders: the member page lists each company
    with its contact people, address, phone and e-mail addresses (soy, maize, wheat, rice exporters and crushers)."""
    url = "https://capeco.org.py/socios/"
    h = requests.get(url, headers=UA, timeout=60).text
    t = _clean(h)
    t = t[t.find("| Socios | Socios |") + 19:] if "| Socios | Socios |" in t else t
    segs = [x.strip() for x in t.split("|")]
    out, cur = [], None
    def flush():
        if cur and cur["supplier"]:
            out.append(cur)
    for seg in segs:
        if not seg:
            continue
        if re.match(r"^[A-ZÁÉÍÓÚÑ0-9][A-ZÁÉÍÓÚÑ0-9&.,' -]{3,}(S\.A\.|S\.R\.L\.|S\.A\.E\.|LTDA\.?|S\.A\.C\.I\.|S\.A\.I\.C\.|SA|SRL|S\.A\.I\.C\.A\.|S\.A\.E\.C\.A\.|COOP\.?[A-Z. ]*|LIMITADA)$", seg):
            flush()
            cur = {"supplier": _name(seg), "country": "PRY", "product": "soybean, maize, wheat, rice, grains and oilseeds", "role": "exporter and trader", "licence": "CAPECO member", "contact_person": "", "phone": "", "email": "", "website": "",
                   "description": "Member of CAPECO, the Paraguayan chamber of grain and oilseed exporters and traders", "size": "", "certifications": "", "source": "CAPECO member list", "source_url": url, "fetched": date.today().isoformat()}
            continue
        if cur is None:
            continue
        if seg.lower().startswith(("contacto", "responsabilidad", "ambito")) or seg in ("ENLACES", "PROGRAMAS"):
            flush(); cur = None; break
        if "@" in seg:
            cur["email"] = cur["email"] or seg.split()[0]
        elif seg.startswith("Tel"):
            m = re.search(r"\(?0?(\d{2,4})\)?[\s.]*([\d.\s]{5,12})", seg)
            cur["phone"] = cur["phone"] or (f"+595 {m.group(1)} {m.group(2).replace('.', '').strip()}" if m else "")
        elif seg.startswith("www") or re.match(r"^[a-z0-9-]+\.(com|py)", seg):
            cur["website"] = cur["website"] or seg
        elif re.match(r"^[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ' -]{5,40}$", seg) and not cur["contact_person"] and not re.search(r"KM|RUTA|AVDA|CALLE|S\.A", seg):
            cur["contact_person"] = _name(seg)
    flush()
    return out


REGISTRIES = {"cameroon": cameroon, "nigeria": nigeria, "pakistan": pakistan, "iran": iran, "vietnam": vietnam, "paraguay": paraguay}


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
