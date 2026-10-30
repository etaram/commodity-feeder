"""Builds a compact name index of official sanctions lists (OFAC SDN + consolidated, UN Security Council, EU consolidated)
for the Deal Desk business-intelligence screening. Names only; no personal data beyond what the lists publish.
Output: data/leads/sanctions.json  {updated, counts, e: [[names...], list, program, type, ref], ...}"""
import csv
import datetime as dt
import io
import json
import logging
import re
import sys
import xml.etree.ElementTree as ET

from .common import LEADS, log, session

OFAC = "https://www.treasury.gov/ofac/downloads/"
UN = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
EU = "https://webgate.ec.europa.eu/fsd/fsf/public/files/csvFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw"


def get(s, url):
    r = s.get(url, timeout=180)
    r.raise_for_status()
    return r.content.decode("utf-8-sig", errors="replace")


def ofac(s):
    out = {}
    for ln in csv.reader(io.StringIO(get(s, OFAC + "sdn.csv"))):
        if len(ln) < 4 or not ln[0].strip().isdigit():
            continue
        t = ln[2].strip().strip("-0 ") or "entity"
        out[ln[0]] = [[ln[1].strip()], "OFAC SDN", ln[3].strip(), t, ln[0]]
    try:
        for ln in csv.reader(io.StringIO(get(s, OFAC + "alt.csv"))):
            if len(ln) >= 4 and ln[0] in out and ln[3].strip():
                out[ln[0]][0].append(ln[3].strip())
    except Exception as e:  # noqa: BLE001
        log.warning("OFAC alt: %s", e)
    try:  # non-SDN consolidated lists (SSI, NS-MBS, FSE ...)
        for ln in csv.reader(io.StringIO(get(s, OFAC + "consolidated/cons_prim.csv"))):
            if len(ln) >= 4 and ln[0].strip().isdigit() and ln[0] not in out:
                out["c" + ln[0]] = [[ln[1].strip()], "OFAC consolidated", ln[3].strip(), ln[2].strip().strip("-0 ") or "entity", ln[0]]
    except Exception as e:  # noqa: BLE001
        log.warning("OFAC cons: %s", e)
    return list(out.values())


def un(s):
    root = ET.fromstring(get(s, UN).encode("utf-8"))
    rows = []
    for kind, tag in (("individual", "INDIVIDUAL"), ("entity", "ENTITY")):
        for e in root.iter(tag):
            g = lambda k: (e.findtext(k) or "").strip()  # noqa: E731
            name = " ".join(x for x in (g("FIRST_NAME"), g("SECOND_NAME"), g("THIRD_NAME"), g("FOURTH_NAME")) if x)
            names = [name] + [(a.findtext("ALIAS_NAME") or "").strip() for a in e.iter(f"{tag}_ALIAS")]
            names = [n for n in names if n]
            if names:
                rows.append([names, "UN Security Council", g("UN_LIST_TYPE"), kind, g("REFERENCE_NUMBER")])
    return rows


def eu(s):
    txt = get(s, EU)
    rd = csv.DictReader(io.StringIO(txt), delimiter=";")
    out = {}
    for r in rd:
        ref = (r.get("Entity_LogicalId") or "").strip()
        nm = (r.get("NameAlias_WholeName") or "").strip()
        if not ref or not nm:
            continue
        if ref not in out:
            out[ref] = [[], "EU consolidated", (r.get("Entity_Regulation_Programme") or "").strip(), (r.get("Entity_SubjectType") or "").strip() or "entity", (r.get("Entity_EU_ReferenceNumber") or ref).strip()]
        if nm not in out[ref][0]:
            out[ref][0].append(nm)
    return list(out.values())


def main():
    s = session()
    ent, counts = [], {}
    for name, fn in (("ofac", ofac), ("un", un), ("eu", eu)):
        try:
            rows = fn(s)
            counts[name] = len(rows); ent += rows
            log.info("sanctions %s: %d", name, len(rows))
        except Exception as e:  # noqa: BLE001
            log.warning("sanctions %s failed: %s", name, str(e)[:200]); counts[name] = -1
    if not ent:
        sys.exit("no sanctions data")
    for r in ent:
        r[0] = list(dict.fromkeys(re.sub(r"\s+", " ", n)[:120] for n in r[0]))[:12]
    out = LEADS / "sanctions.json"
    old = json.loads(out.read_text()) if out.exists() else {}
    if counts.get("ofac", 0) < 0 and old.get("e"):  # keep the previous list if a source failed
        log.warning("keeping previous sanctions data"); return
    out.write_text(json.dumps({"updated": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M"), "counts": counts, "e": ent}, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
