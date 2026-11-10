"""Uganda's official Coffee and Cocoa Directory (Uganda Coffee Development Authority, a public PDF): producer
co-operatives, farms, primary processors, processors and exporters, roasters and cocoa actors, each with its location,
contact person, phone, e-mail, website and a line on what it does.

The PDF is set in two columns; each entry is a name followed by labelled lines ("Location:", "Contact Person:", "Mob:",
"Email:", "Web:", "Description:"). The columns are read one after the other so an entry stays together. The section
heading above an entry gives its role. Output: data/leads/uganda_directory.csv (an official directory: a listing with
contacts, to verify before relying on it, as the directory itself recommends).

  python -m leads.uganda_directory
"""
import csv
import io
import json
import re
from datetime import date

import requests

from .common import LEADS, log

URL = "https://ugandacoffee.go.ug/Coffee_and_Cocoa_Directory.pdf"
UA = {"User-Agent": "Mozilla/5.0 (compatible; SinderLeads/1.0; +https://desk.sinder.pro)"}
OUT = LEADS / "uganda_directory.csv"
FIELDS = ["supplier", "country", "section", "role", "product", "location", "contact_person", "phone", "email", "website", "description", "source", "source_url", "fetched"]
LABEL = re.compile(r"^(Location|Contact Person|Contact Persons|Mob|Tel|Email|E-mail|Web|Website|Facebook|Twitter|Instagram|LinkedIn|Description|Established|GPS Coordinates|P\.?O\.? ?Box|Whatsapp|WhatsApp)\s*:", re.I)
# section heading -> (role, product); only sections that are suppliers of coffee or cocoa are kept
SECTIONS = [(r"Coffee Producer Co-?operatives", "producer cooperative", "coffee"), (r"Coffee Farms, Farmers, Farmer Groups", "farm or farmer group", "coffee"),
            (r"Coffee Primary Processing Factories", "primary processor", "coffee"), (r"Coffee Processors and Exporters", "processor and exporter", "coffee"),
            (r"Coffee Exporters", "exporter", "coffee"), (r"Coffee Roasters", "roaster", "coffee"), (r"Cocoa Farmers|Cocoa Producer", "producer", "cocoa"),
            (r"Cocoa Processors|Cocoa Exporters|Cocoa Buyers", "processor and exporter", "cocoa"), (r"Cocoa Nursery", "", ""), (r"Coffee Nursery Operators", "", ""),
            (r"Coffee Agro-?Input|Soil Solutions|Tissue Plant|Tools and Processing Equipment|Packaging|Financial|Support Institutions|Logistics|Research|Associations and|Certification|Coffee Shops|Caf[eé]s", "", "")]


def columns(page):
    """The two columns of a page as text, left then right."""
    w, h = page.width, page.height
    out = []
    for box in ((0, 0, w / 2, h), (w / 2, 0, w, h)):
        try:
            out.append(page.crop(box).extract_text() or "")
        except Exception:  # noqa: BLE001
            out.append("")
    return "\n".join(out)


def parse(text):
    """Entries of a stretch of directory text: [(section, name, {field: value})]."""
    lines = [re.sub(r"\s+", " ", x).strip() for x in text.split("\n")]
    # running heads and footers of the pages (also when the column split cuts them in half) are not directory text
    noise = re.compile(r"MAAIF|REPUBLIC OF UGANDA|Animal Industry|Ministry of Agricultur|Value Chains?$|^nt in Uganda|^oa Value|Coffee and Coco\b|^Directory Uganda$|Developmen$|^\d{1,3} Directory Uganda", re.I)
    lines = [x for x in lines if x and not re.fullmatch(r"Coffee and Cocoa Directory Uganda|\d{1,3}|[ivx]{1,5}", x) and not noise.search(x)]
    out, section, name, cur, last, pend = [], ("", ""), "", None, "", []

    def close():
        nonlocal cur, name
        if cur is not None and name:
            out.append((section, name, cur))
        cur, name = None, ""

    for ln in lines:
        sec = next(((role, prod) for rx, role, prod in SECTIONS if re.fullmatch(rx + r".{0,25}", ln, re.I)), None)
        if sec is not None:
            close(); section, pend = sec, []; continue
        m = LABEL.match(ln)
        if m:
            key = m.group(1).lower()
            if key == "location" and (cur is None or "location" in cur):   # a new entry: its name is the pending unlabelled line(s)
                close()
                name, cur = " ".join(pend[-2:]).strip() if pend and len(" ".join(pend[-2:])) <= 90 else (pend[-1] if pend else ""), {}
            if cur is None:
                continue
            last = "contact" if key.startswith("contact") else "phone" if key in ("mob", "tel", "whatsapp") else "email" if key in ("email", "e-mail") else "web" if key in ("web", "website") else key
            cur[last] = (cur.get(last, "") + " " + ln[m.end():].strip()).strip() if last in cur and last in ("phone", "email") else cur.get(last) or ln[m.end():].strip()
            pend = []
            continue
        # an unlabelled line: the continuation of a description, or the name of the next entry
        if cur is not None and last == "description" and not (len(ln) <= 70 and not ln.endswith((".", ",", ";")) and ln[:1].isupper() and (cur["description"].endswith(".") or len(cur["description"]) > 200)):
            cur["description"] = (cur.get("description", "") + " " + ln).strip()
            pend = []
        else:
            pend.append(ln)
            if len(pend) > 3:
                pend = pend[-3:]
    close()
    return out


def main():
    import pdfplumber
    r = requests.get(URL, headers=UA, timeout=120)
    r.raise_for_status()
    with pdfplumber.open(io.BytesIO(r.content)) as d:
        text = "\n".join(columns(p) for p in d.pages[9:88])   # the listings; the front matter and the index are skipped
    rows, seen = [], set()
    for (role, prod), name, f in parse(text):
        name = re.sub(r"^[\W\d]+", "", name).strip()
        if not role or len(name) < 3 or len(name) > 90 or name.lower() in seen or LABEL.match(name):
            continue
        seen.add(name.lower())
        em = re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", f.get("email", ""))
        web = re.search(r"(?:https?://)?(?:www\.)?[\w-]+(?:\.[\w-]+)+[^\s,;]*", f.get("web", ""))
        ph = re.findall(r"\+?\d[\d ]{8,15}\d", f.get("phone", ""))
        rows.append({"supplier": name, "country": "UGA", "section": f"{prod} {role}", "role": role, "product": prod, "location": f.get("location", "")[:120],
                     "contact_person": f.get("contact", "")[:80], "phone": "; ".join(dict.fromkeys(re.sub(r"\s+", " ", p).strip() for p in ph))[:80], "email": "; ".join(dict.fromkeys(em))[:120],
                     "website": (web.group(0).rstrip(".") if web else "")[:100], "description": re.sub(r"\s*\[See details.*$", "", f.get("description", ""))[:260],
                     "source": "Uganda Coffee Development Authority: Coffee and Cocoa Directory", "source_url": URL, "fetched": date.today().isoformat()})
    if len(rows) >= 40:   # a failed read never replaces the last good file
        with open(OUT, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
    by = {}
    for x in rows:
        by[x["section"]] = by.get(x["section"], 0) + 1
    print("uganda directory:", json.dumps({"entries": len(rows), "with_email": sum(1 for x in rows if x["email"]), "with_phone": sum(1 for x in rows if x["phone"]), "with_website": sum(1 for x in rows if x["website"]), "sections": by}))
    for x in rows[:3] + rows[len(rows) // 2:len(rows) // 2 + 3]:
        print("   sample:", {k: x[k] for k in ("supplier", "section", "location", "phone", "description")})


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    main()
