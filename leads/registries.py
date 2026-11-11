"""Official exporter registries and directories of origin countries, each read from the authority's own publication.

  cameroon   National Cocoa and Coffee Board (ONCC): the list of active cocoa and coffee exporters for the year, with phone
             and e-mail (a public PDF linked from oncc.cm/exporters)
  nigeria    Nigerian Export Promotion Council: the "find your supplier" directory for importers (name, products, size,
             certifications, description)
  pakistan   Rice Exporters Association of Pakistan member roll with each member's contact page
  iran       Iran Pistachio Association member lists (exporters, growers, service providers)
  vietnam    Vietnam Food Association member roll (rice exporters and millers)
  paraguay   CAPECO (grain and oilseed exporters' chamber) member list with contacts
  south_africa  FPEF fresh produce exporter members (contact, phone, website, commodities)
  brazil     CECAFE coffee exporters' council member list

Each registry writes data/leads/registry_<country>.csv with the same columns, and leads/webindex.py puts the rows into the
supplier index: an official registry entry is proof of licence or registration (tier 2), a promotion-council listing is
the company's own profile (tier 3). An empty or failed read never replaces the last good file.

  python -m leads.registries
"""
import csv
import os
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


def south_africa():
    """Fresh Produce Exporters' Forum (FPEF), South Africa: the extensive exporter member list with contact person,
    telephone, website and the commodities each member exports (the site masks e-mail addresses)."""
    url = "https://www.fpef.co.za/exportermembersextensivelist"
    h = requests.get(url, headers=UA, timeout=90).text
    t = _clean(h)
    out = []
    for m in re.finditer(r"\| ([^|]{2,60}?) \| Contact person: \| ([^|]*?) \| Telephone: \| ([^|]*?) \| E-mail: \| [^|]*\| Website: \| ([^|]*?) \| Commodities: \| ([^|]*?) \|", t):
        name, person, tel, web, comm = (x.strip() for x in m.groups())
        if name.lower().startswith(("exporter members", "search")):
            continue
        web = "" if "8203" in web or len(web) < 5 else web
        out.append({"supplier": name, "country": "ZAF", "product": comm.lower() or "fresh fruit", "role": "exporter", "licence": "FPEF exporter member", "contact_person": person,
                    "phone": tel if tel.startswith("+") else "", "email": "", "website": web, "description": f"Fresh produce exporter, FPEF member; exports {comm.lower()}", "size": "", "certifications": "",
                    "source": "Fresh Produce Exporters' Forum member list", "source_url": url, "fetched": date.today().isoformat()})
    return out


def brazil():
    """CECAFE, the Brazilian coffee exporters' council: the member list (exporters, cooperatives, warehouses and the
    regional coffee trade centres); names only, as published."""
    url = "https://www.cecafe.com.br/conheca-o-cecafe/associados/"
    h = requests.get(url, headers=UA, timeout=90).text
    t = _clean(h)
    i = t.find("| Associados | Associados |")
    seg = t[i + 27:] if i >= 0 else t
    out = []
    for x in [y.strip() for y in seg.split("|")]:
        if not x or len(x) < 6:
            continue
        if x.lower().startswith(("links úteis", "como se associar", "contato", "rss", "home")) or re.match(r"\d{4}-\d{2}", x):
            if out and x.lower().startswith(("links úteis", "contato")):
                break
            continue
        if re.search(r"\d{4}-\d{2}-\d{2}", x) or x.lower() in ("associados",) or not out and not re.search(r"ltda|s/a|s\.a|coop|café|cafe|coffee|export|armaz|agro|com", x, re.I):
            continue   # the post's author line precedes the list
        name = x.replace("&#8211;", "-").replace("&amp;", "&")
        if not re.search(r"[A-Za-zÀ-ú]", name) or len(name) > 90:
            continue
        kind = "trade centre" if re.search(r"Centro d[eo] Com|Associação Comercial", name) else "cooperative" if re.search(r"Coop", name, re.I) else "warehouse" if re.search(r"Armaz", name, re.I) else "exporter"
        if kind == "trade centre":
            continue
        out.append({"supplier": name, "country": "BRA", "product": "coffee", "role": "producer cooperative and exporter" if kind == "cooperative" else kind, "licence": "CECAFE member", "contact_person": "", "phone": "", "email": "", "website": "",
                    "description": f"Member of CECAFE, the Brazilian coffee exporters' council ({kind})", "size": "", "certifications": "", "source": "CECAFE member list", "source_url": url, "fetched": date.today().isoformat()})
        if len(out) > 300:
            break
    return out


def _row(supplier, country, product, role, licence, description, source, url, person="", phone="", email="", website=""):
    return {"supplier": supplier, "country": country, "product": product, "role": role, "licence": licence, "contact_person": person, "phone": phone, "email": email, "website": website,
            "description": description, "size": "", "certifications": "", "source": source, "source_url": url, "fetched": date.today().isoformat()}


def _text(url, timeout=90):
    import html as _html
    return _html.unescape(_clean(requests.get(url, headers=UA, timeout=timeout).text))


def argentina():
    """CIARA-CEC, the Argentine oilseed industry chamber and cereal exporters' centre: each member with the products it
    trades, address, telephone, e-mail and website."""
    url = "https://www.ciaracec.com.ar/ciara/Asociados"
    out = []
    for block in _text(url).split("Cerrar ventana"):
        m = re.search(r"\| ([^|]{3,90}?) \| Ver datos \| Productos que comercializa: \| ([^|]*?) \|", block)
        if not m:
            continue
        name, products = m.group(1).strip(), m.group(2).strip().rstrip(".")
        tel = re.search(r"Tel: \| ([^|]*?) \|", block)
        em = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", block)
        web = re.search(r"Web: \| ([^|]*?) \|", block)
        phone = re.sub(r"\s*-\s*$", "", tel.group(1).strip()) if tel else ""
        phone = "+" + phone.replace("(", "").replace(")", "") if phone.startswith("(54") else ("+54 " + phone.lstrip("(0").replace(")", "") if re.match(r"\(?0\d", phone) else phone)
        out.append(_row(name, "ARG", "soybean, maize, wheat, sunflower, grains and vegetable oils", "exporter and crusher" if re.search(r"Aceite|Harina", products) else "exporter", "CIARA-CEC member",
                        f"Member of CIARA-CEC (Argentine oilseed industry chamber and cereal exporters' centre); trades: {products.lower()}", "CIARA-CEC member list", url,
                        phone=phone, email=em.group(0) if em else "", website=(web.group(1).strip().rstrip("/") if web and "." in web.group(1) else "")))
    return out


def indonesia():
    """GAPKI, the Indonesian palm oil association: member companies with province, address, telephone and e-mail as the
    association lists them (the first page of the public member search)."""
    url = "https://gapki.id/member-gapki/"
    out = []
    for block in _text(url).split("| Anggota GAPKI |")[1:]:
        m = re.match(r"\s*([^|]{3,90}?) \| Lokasi \| ([^|]*?) \|", block)
        if not m:
            continue
        tel = re.search(r"Telepon \| ([^|]*?) \|", block)
        em = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", block)
        phone = tel.group(1).strip() if tel else ""
        phone = "+62 " + phone[1:] if phone.startswith("0") else phone
        out.append(_row(m.group(1).strip(), "IDN", "palm oil (CPO), palm kernel", "producer", "GAPKI member", f"Member of GAPKI, the Indonesian palm oil association; {m.group(2).strip()}", "GAPKI member list", url,
                        phone=phone, email=em.group(0) if em and "gapki" not in em.group(0) else ""))
    return out


def ukraine():
    """Ukrainian Grain Association: full and associated member companies (grain exporters, traders, terminals)."""
    url = "https://uga.ua/en/members-and-partners/"
    out, seen = [], set()
    for name, kind in re.findall(r"\| ([^|]{3,90}?) \| (Полные|Ассоциированные) \|", _text(url)):
        name = re.sub(r"[“”«»\"]", "", name).strip()
        if name in seen:
            continue
        seen.add(name)
        out.append(_row(name, "UKR", "wheat, maize, barley, sunflower, grains and oilseeds", "exporter and trader" if kind == "Полные" else "trader or service company", "Ukrainian Grain Association member",
                        f"{'Full' if kind == 'Полные' else 'Associated'} member of the Ukrainian Grain Association", "Ukrainian Grain Association member list", url))
    return out


def colombia():
    """Asoexport, the Colombian coffee exporters' association: affiliated exporting companies."""
    url = "https://asoexport.org/home/afiliados/"
    out, seen = [], set()
    for name in re.findall(r'\| ([^|"]{4,80}?) \| " data-category="\d+"', _text(url)):
        name = _name(name.strip())
        if name not in seen:
            seen.add(name)
            out.append(_row(name, "COL", "coffee", "exporter", "Asoexport member", "Affiliated to Asoexport, the Colombian coffee exporters' association", "Asoexport affiliated companies", url))
    return out


def chile():
    """Chilenut, the Chilean walnut association: producer and exporter members."""
    url = "https://chilenut.cl/socios/"
    t = _text(url)
    i = t.find("Nuestros Socios")
    out, seen, role = [], set(), "producer"
    for seg in [x.strip() for x in t[i:].split("|")] if i >= 0 else []:
        if re.search(r"Socios Exportador", seg, re.I):
            role = "exporter"
        if re.search(r"Socios Productor", seg, re.I):
            role = "producer"
        if seg.lower().startswith(("contacto", "síguenos", "©")):
            break
        if len(seg) < 6 or not re.match(r"^[A-ZÁÉÍÓÚÑ0-9&.,' -]+$", seg) or seg in seen:
            continue
        seen.add(seg)
        out.append(_row(_name(seg), "CHL", "walnuts", role, "Chilenut member", f"Member of Chilenut, the Chilean walnut association ({role})", "Chilenut member list", url))
    return out


def peru():
    """Peruvian Chamber of Coffee and Cocoa: member exporters with the chamber's own short description of each."""
    url = "https://camcafeperu.com.pe/ES/asociados.php"
    out = []
    for name, desc in re.findall(r"\| ([^|]{3,80}?) \| ([^|]{40,900}?) \| Ver site", _text(url)):
        out.append(_row(name.strip(), "PER", "coffee, cocoa", "exporter", "Cámara Peruana del Café y Cacao member", desc.strip()[:400], "Peruvian Chamber of Coffee and Cocoa member list", url))
    return out


def india(budget_s=1500):
    """APEDA (India's agricultural export authority) exporter directory: the registered member exporters with
    address, the product line they declare and the state. About 480 pages of 9; the site is slow, so each run reads
    pages for budget_s seconds from where the last run stopped and merges into the file (data/leads/
    registry_india_state.json keeps the next page). The contact button posts the member's tax identifier, so it is
    not used or stored."""
    import html as _html
    import time as _time
    base = "https://agriexchange.apeda.gov.in/AgriDirectory/Exporter/Exporters?page={}"
    state_f, out_f = LEADS / "registry_india_state.json", LEADS / "registry_india.csv"
    try:
        state = json.load(open(state_f, encoding="utf-8"))
    except (OSError, ValueError):
        state = {"next": 1, "last": 0}
    have = {}
    if out_f.exists():
        for r in csv.DictReader(open(out_f, encoding="utf-8")):
            have[(r["supplier"].upper(), r["description"][-6:])] = r
    t0, page, read = _time.time(), state["next"], 0
    while _time.time() - t0 < budget_s:
        try:
            h = requests.get(base.format(page), headers=UA, timeout=(10, 60)).text
        except Exception:  # noqa: BLE001
            page += 1; continue
        state["last"] = max([int(x) for x in re.findall(r"Exporters\?page=(\d+)", h)] + [state.get("last") or 0])
        for box in re.findall(r'<div class="box col-md-4">(.*?)Click here to contact', h, flags=re.S):
            ps = [re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", x))).strip() for x in re.findall(r"<p[^>]*>(.*?)</p>", box, flags=re.S)]
            if len(ps) < 4 or not ps[0]:
                continue
            name, addr, prod, state_name = ps[0], ps[1], ps[2], ps[3]
            pin = ps[4] if len(ps) > 4 else ""
            row = _row(_name(name), "IND", prod.lower() or "agricultural products", "exporter", "APEDA registered exporter",
                       f"APEDA registered exporter; {prod}; {addr}, {state_name} {pin}".strip(), "APEDA exporter directory", base.format(page))
            have[(row["supplier"].upper(), row["description"][-6:])] = row
        read += 1
        page = 1 if state["last"] and page >= state["last"] else page + 1
        _time.sleep(1.0)
    state["next"] = page
    json.dump(state, open(state_f, "w", encoding="utf-8"))
    log.info("india (APEDA): %d pages read this run, next page %d of %d, %d exporters on file", read, page, state.get("last") or 0, len(have))
    return list(have.values())

def philippines():
    """Philippine Sugar Millers Association: the member sugar mills."""
    url = "https://psma.com.ph/members-and-industry-partners"
    t = _text(url)
    i, j = t.find("| Members |"), t.find("Institutional Focus")
    out = []
    for x in [y.strip() for y in t[i + 11:j].split("|")] if i >= 0 else []:
        x = re.sub(r"^\d+\.\s*", "", x).strip()
        if len(x) < 5 or x.lower().startswith("associate member"):
            continue
        out.append(_row(x, "PHL", "sugar (raw and refined)", "producer", "PSMA member", "Sugar mill, member of the Philippine Sugar Millers Association", "Philippine Sugar Millers Association member list", url))
    return out


REGISTRIES = {"cameroon": cameroon, "nigeria": nigeria, "pakistan": pakistan, "iran": iran, "vietnam": vietnam, "paraguay": paraguay, "south_africa": south_africa, "brazil": brazil, "argentina": argentina, "indonesia": indonesia, "ukraine": ukraine, "colombia": colombia, "chile": chile, "peru": peru, "india": india, "philippines": philippines}


def main(only=None):
    LEADS.mkdir(parents=True, exist_ok=True)
    rep = {}
    import concurrent.futures as cf
    import time as _time
    pool = cf.ThreadPoolExecutor(max_workers=4)
    for key, fn in REGISTRIES.items():
        if (only and key not in only) or (not only and key in SEPARATE):
            continue
        t0 = _time.time()
        limit = 1800 if key in SEPARATE else 300   # one slow or silent site must not hold the others
        try:
            rows = pool.submit(fn).result(timeout=limit)
        except cf.TimeoutError:
            log.warning("registry %s: gave up after %d s (previous file kept)", key, limit); rows = []
        except Exception as e:  # noqa: BLE001
            log.warning("registry %s: %s", key, str(e)[:120]); rows = []
        log.info("registry %s: %d rows in %.0f s", key, len(rows), _time.time() - t0)
        if len(rows) >= 5:
            with open(LEADS / f"registry_{key}.csv", "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
        rep[key] = {"rows": len(rows), "with_email": sum(1 for r in rows if r["email"]), "with_phone": sum(1 for r in rows if r["phone"])}
    print("registries:", json.dumps(rep), flush=True)
    os._exit(0)   # threads still waiting on a silent site are dropped here


SEPARATE = {"india"}   # long registries run in their own step with a time budget


if __name__ == "__main__":
    import logging
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    main(set(sys.argv[1:]) or None)
