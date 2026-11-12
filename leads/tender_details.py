"""Tender details (refined layer for open tenders): what a bid needs, read from the official machine-readable notice.

A tender row in the index has title, buyer, country, value, deadline and link. To work a deal one also needs the items
and quantities, the technical standards, the delivery place and terms, the bid security and the performance guarantee,
the eligibility and experience thresholds, the lots, the evaluation method, the clarification deadline and the
document links. This module reads them from the publisher's own structured record, in this order of preference:

  TED (EU)            eForms XML of the notice (ted.europa.eu/en/notice/<pn>/xml): lots, CPV, place of performance,
                      duration, tender guarantee (BT-75), selection criteria (BT-747/750), award criteria and weights
                      (BT-539/541), clarification deadline (BT-13), document URL (BT-15), submission URL (BT-18)
  BOAMP (France)      the same eForms record, published as JSON by the BOAMP open-data API (field "donnees")
  Prozorro (Ukraine)  public API 2.5: items with quantity and unit, lots, tender guarantee, ESPD criteria (eligibility,
                      contract guarantee), award criteria, enquiry period, documents
  PNCP (Brazil)       public API: purchase record, item list with quantity, unit and judging criterion, document files
  ChileCompra         official API (ticket): item list with quantity and unit, question deadline, contract duration
  World Bank          procurement notices API: the notice text (bid security, performance security, qualification,
                      lots), read with plain rules and quoted, never paraphrased

Rules: official sources only; every field carries the source URL, the date it was read and the basis (which element of
the record); a field the record does not state is "not stated"; nothing is inferred or invented. Text fields are
quoted from the notice (short snippets, e-mail addresses and phone numbers removed). No login, no CAPTCHA, no paywall;
one request at a time per publisher with a pause.

Which tenders: open, deadline at least MIN_DAYS away, Sinder focus sectors, from a supported publisher; best fit score
and value first; a record is read again after REFRESH_DAYS (amendments) and dropped when the tender closes.

Outputs
  data/tenders/details.jsonl.gz              full layer with document hashes (Actions cache tenderdetails-*)
  data/leads/refined/tender_details.csv      id, source, refined, filled, details (compact JSON) for the open tenders;
                                             public facts from official notices, no personal data
  data/leads/refined/tender_details_stats.json  counts and fill rates per field and per source

  python -m leads.tender_details run [--limit N] [--minutes M]
  python -m leads.tender_details sample [N]      measure fill rates on N tenders (default 50) and seal 10 raw records
"""
import csv
import datetime as dt
import gzip
import hashlib
import html
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from urllib.parse import quote

from .common import DATA, LEADS, log

VERSION = "details-1"
DIR = DATA / "tenders"
STORE = DIR / "details.jsonl.gz"
PUB = LEADS / "refined" / "tender_details.csv"
STATS = LEADS / "refined" / "tender_details_stats.json"
MIN_DAYS = 7
REFRESH_DAYS = 7
NS = "not stated"
UA = "Mozilla/5.0 (compatible; SinderTenders/1.0; +https://desk.sinder.pro)"

# the fields a bid needs (the case files listed them); fill rates are measured on these
FIELDS = ["items", "technical_standards", "delivery", "bid_security", "performance_guarantee", "eligibility", "lots",
          "evaluation", "clarification_deadline", "documents"]
EXTRA = ["submission_deadline", "submission_url", "duration", "tender_validity", "variants", "framework", "procedure"]
FOCUS = {"Power & electrical equipment", "Energy, fuels & utilities", "Healthcare & pharmaceuticals", "Defence & security",
         "Agriculture & food", "Mining, minerals & metals", "Chemicals & plastics", "Industrial & construction machinery",
         "Construction materials & building systems", "Scientific & measuring instruments", "ICT & telecom",
         "Water & wastewater", "Vehicles, rolling stock, ships & aircraft"}
SOURCES = {"TED (EU)": "ted", "BOAMP (France)": "boamp", "Prozorro (Ukraine)": "prozorro", "PNCP (Brazil)": "pncp",
           "ChileCompra": "chile", "World Bank": "worldbank"}
PAUSE = {"ted": 1.0, "boamp": 0.6, "prozorro": 0.3, "pncp": 0.8, "chile": 1.3, "worldbank": 0.6}

# ---------------------------------------------------------------- text rules (quoted, never paraphrased)
EMAIL = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,24}")
PHONE = re.compile(r"(?:\+|00)\d[\d\s().-]{7,18}\d|\b(?:tel|phone|tél|téléphone|telefone|teléfono|fax)\.?\s*:?\s*[\d\s().+-]{7,20}", re.I)
STD = re.compile(r"\b(?:EN|ISO|IEC|IEEE|ASTM|DIN|BS|NF|UNE|ELOT|ΕΛΟΤ|ANSI|NEMA|ASME|AWWA|ГОСТ|ДСТУ|GOST|DSTU|NBR|ABNT|NCh)"
                 r"(?:\s?(?:EN|ISO|IEC|Б\.В\.|B\.V\.))?[\s-]?\d{2,6}(?:[-‑/.]\d{1,4})*(?::\d{4})?\b")
CE = re.compile(r"\b(CE[ -]mark(?:ing|ed)?|marquage CE|marcado CE|CE-Kennzeichnung|σήμανση CE|marcatura CE|маркування CE)\b", re.I)
INCOTERMS = re.compile(r"\b(EXW|FCA|FAS|FOB|CFR|CIF|CPT|CIP|DAP|DPU|DDP)\b(?:\s+[A-Z][\w-]+)?")
BID_SEC = re.compile(r"(?:bid|tender|offer)[- ](?:security|guarantee|bond)|bid[- ]securing declaration|garantie de soumission|"
                     r"garant[ií]a (?:de seriedad|provisional)|garanzia provvisoria|cauzione provvisoria|Bietungsb[üu]rgschaft|wadium|"
                     r"εγγυητική επιστολή συμμετοχής|εγγύηση συμμετοχής|garantia (?:de|da) proposta|забезпечення тендерн\w*", re.I)
PERF = re.compile(r"performance (?:security|guarantee|bond)|garantie de bonne (?:fin|ex[ée]cution)|retenue de garantie|"
                  r"garant[ií]a (?:definitiva|de cumplimiento|de fiel cumplimiento)|garanzia definitiva|cauzione definitiva|"
                  r"(?:Vertrags)?erf[üu]llungsb[üu]rgschaft|zabezpieczenie nale[żz]ytego wykonania|"
                  r"εγγυητική επιστολή καλής εκτέλεσης|εγγύηση καλής εκτέλεσης|garantia (?:contratual|de execu[cç][aã]o)|"
                  r"забезпечення виконання договору", re.I)
DELIV = re.compile(r"(?:deliver\w*|livraison|livr\w+|entrega\w*|liefer\w*|consegn\w*|παράδοσ\w*|dostaw\w*|постав\w*)"
                   r"[^.;:\n]{0,60}?\b(\d{1,3})\s*(?:calendar |working |business )?"
                   r"(days?|weeks?|months?|jours?|semaines?|mois|d[ií]as?|semanas?|meses|Tage[n]?|Wochen|Monate[n]?|giorni|mesi|"
                   r"ημέρ\w+|ημερ\w+|dni|днів|календарних днів)", re.I)
QTY = re.compile(r"\b\d{1,3}(?:[ .,]\d{3})*(?:[.,]\d+)?\s?(?:pcs|pieces?|units?|nos\.?|sets?|km|kilomet(?:er|re)s?|metres?|meters?|"
                 r"tonnes?|tons?|kg|litres?|liters?|MVA|kVA|MW|kW|vehicles?|items?|Stück|Stk\.?|unités|pièces|unidades|uds\.?|"
                 r"τεμάχια|τεμ\.|τμχ\.?|szt\.?|doses?|vials?|boxes|lots?|шт\.?|комплект\w*)\b", re.I)
TURNOVER = re.compile(r"(?:turnover|chiffre d.affaires|volumen (?:anual )?de negocios|fatturato|Umsatz|κύκλο[ςυ] εργασιών|obr[óo]t|"
                      r"оборот|faturamento)[^.;\n]{0,160}", re.I)
EXPERIENCE = re.compile(r"(?:similar (?:contracts?|supplies|deliveries|projects)|experience|références|referencias|referenze|"
                        r"Referenzen|εμπειρία|doświadczeni\w*|досвід\w*|experi[êe]ncia|atestado de capacidade)[^.;\n]{0,200}", re.I)


def scrub(s, n=300):
    """A quoted snippet: markup out, e-mail addresses and phone numbers removed, spaces collapsed, cut at n."""
    s = html.unescape(html.unescape(str(s or "")))
    s = re.sub(r"<[^>]{0,400}>", " ", s)
    s = EMAIL.sub("[e-mail]", s)
    s = PHONE.sub("[phone]", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def snippet(text, m, width=160):
    """The sentence around a regex match (quoted from the notice)."""
    a, b = m.start(), m.end()
    lo = max(text.rfind(". ", 0, a), text.rfind("\n", 0, a), a - width)
    hi_c = [x for x in (text.find(". ", b), text.find("\n", b)) if x >= 0]
    hi = min(hi_c + [b + width])
    return scrub(text[max(0, lo + 1): hi + 1], 2 * width)


def find_all(rx, text, limit=4):
    out = []
    for m in rx.finditer(text or ""):
        s = snippet(text, m)
        if s and s not in out:
            out.append(s)
        if len(out) >= limit:
            break
    return out


def incoterms(text):
    """Incoterms named in a delivery context (the code alone, e.g. 'CIP' in French text, is too often something else)."""
    out = []
    for m in INCOTERMS.finditer(text or ""):
        ctx = (text[max(0, m.start() - 80): m.end() + 80]).lower()
        if re.search(r"incoterm|deliver|livraison|entrega|liefer|consegna|παράδοσ|dostaw|постав", ctx):
            v = m.group(0).strip()
            if v not in out:
                out.append(v)
    return out[:3]


def standards(text):
    out = []
    for m in STD.finditer(text or ""):
        v = re.sub(r"\s+", " ", m.group(0)).strip()
        if re.fullmatch(r"(?:EN|ISO|IEC|DIN|BS|NF|UNE)\s?(?:19|20)\d\d", v):
            continue  # a year after a bare prefix ("EN 2026") is not a standard
        if v not in out:
            out.append(v)
    if CE.search(text or ""):
        out.append("CE marking")
    return out[:25]


def field(v, src, at, basis):
    """One field with its provenance. Empty values become 'not stated' (the record does not give it)."""
    empty = v in (None, "", [], {}) or (isinstance(v, str) and not v.strip())
    return {"v": NS if empty else v, "s": src, "a": at, "b": basis}


def filled(f):
    return bool(f) and f.get("v") not in (NS, None, "", [])


# ---------------------------------------------------------------- generic tree (XML or xmltodict-style JSON)
def _local(tag):
    return tag.split("}", 1)[-1].split(":", 1)[-1]


def xml_tree(raw):
    """eForms XML -> nested dict with local names (no prefixes): {"name": node | [nodes]}, "@attr", "#text"."""
    root = ET.fromstring(raw)

    def conv(e):
        d = {f"@{_local(k)}": v for k, v in e.attrib.items()}
        for c in e:
            k, v = _local(c.tag), conv(c)
            if k in d:
                d[k] = d[k] if isinstance(d[k], list) else [d[k]]
                d[k].append(v)
            else:
                d[k] = v
        t = (e.text or "").strip()
        if t:
            if len(d) == 0:
                return t
            d["#text"] = t
        return d
    return {_local(root.tag): conv(root)}


def json_tree(o):
    """BOAMP's xmltodict JSON -> the same shape (prefixes dropped)."""
    if isinstance(o, dict):
        return {(k if k.startswith(("@", "#")) else k.split(":", 1)[-1]): json_tree(v) for k, v in o.items()}
    if isinstance(o, list):
        return [json_tree(v) for v in o]
    return o


def _list(x):
    return x if isinstance(x, list) else [] if x is None else [x]


def nodes(n, path):
    """Every node at a '/'-separated path of local names (lists followed at each step)."""
    cur = _list(n)
    for p in path.split("/"):
        nxt = []
        for c in cur:
            if isinstance(c, dict) and p in c:
                nxt += _list(c[p])
        cur = nxt
    return cur


def text(n):
    if isinstance(n, dict):
        return str(n.get("#text", "")).strip()
    return "" if n is None else str(n).strip()


def first(n, path):
    for x in nodes(n, path):
        t = text(x)
        if t:
            return t
    return ""


def attr(n, name):
    return str(n.get("@" + name, "")) if isinstance(n, dict) else ""


def by_list(n, path, list_name):
    """Values of coded elements at a path whose listName is list_name."""
    return [text(x) for x in nodes(n, path) if attr(x, "listName") == list_name and text(x)]


def _date(s):
    s = str(s or "").strip()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else ""


def _deadline(period):
    d, t = first(period, "EndDate"), first(period, "EndTime")
    if not _date(d):
        return ""
    return _date(d) + (" " + t[:5] if re.match(r"\d\d:\d\d", t) else "")


# ---------------------------------------------------------------- eForms (TED XML and BOAMP JSON)
CRIT = {"price": "price", "cost": "cost", "quality": "quality"}
SEL = {"sui-act": "suitability to pursue the activity", "ef-stand": "economic and financial standing",
       "tp-abil": "technical and professional ability", "slc-stand-other": "other", "slc-suit-reg-prof": "professional register",
       "slc-abil-staff": "staff", "slc-abil-references": "references (similar contracts)", "slc-stand-turnover": "turnover",
       "slc-stand-insur": "insurance", "slc-abil-qual-cert": "quality certificates", "slc-abil-env-cert": "environmental certificates",
       "slc-abil-equip": "equipment", "slc-stand-ratio": "financial ratio"}


def sel_label(code):
    """eForms selection-criterion code -> words ('slc-abil-ref-services' -> 'technical ability: ref services')."""
    if code in SEL:
        return SEL[code]
    parts = code.replace("slc-", "").split("-")
    head = {"stand": "economic and financial standing", "abil": "technical ability", "suit": "suitability"}.get(parts[0], parts[0])
    return head + (": " + " ".join(parts[1:]) if len(parts) > 1 else "")


def parse_eforms(tree, src, at):
    """Fields from an eForms competition notice. tree is the output of xml_tree or json_tree."""
    cn = None
    for k in ("ContractNotice", "PriorInformationNotice"):
        if isinstance(tree, dict) and k in tree:
            cn = tree[k]; break
    if cn is None:
        return None
    lots = nodes(cn, "ProcurementProjectLot")
    proj = (nodes(cn, "ProcurementProject") or [{}])[0]
    texts = [first(proj, "Name"), first(proj, "Description")]
    items, lot_rows, places, durations, guarantees, docs, crit_rows, sel_rows, clar, subm, urls, validity, variants, fw = \
        [], [], [], [], [], [], [], [], [], [], [], [], [], []
    for lot in lots:
        lid = first(lot, "ID")
        lp = (nodes(lot, "ProcurementProject") or [{}])[0]
        name, desc = first(lp, "Name"), first(lp, "Description")
        texts += [name, desc]
        cpv = by_list(lp, "MainCommodityClassification/ItemClassificationCode", "cpv")
        qty = ""
        for q in nodes(lp, "EstimatedQuantity") + nodes(lp, "Quantity"):
            if text(q):
                qty = f"{text(q)} {attr(q, 'unitCode')}".strip(); break
        amt = nodes(lp, "RequestedTenderTotal/EstimatedOverallContractAmount")
        val = f"{text(amt[0])} {attr(amt[0], 'currencyID')}".strip() if amt and text(amt[0]) else ""
        it = {"lot": lid, "name": scrub(name, 200)}
        if cpv:
            it["cpv"] = cpv[0]
        if qty:
            it["quantity"] = qty
        mention = find_all(QTY, f"{name}. {desc}", 2)
        if mention and not qty:
            it["quantity_in_text"] = mention
        items.append(it)
        lot_rows.append({k: v for k, v in (("id", lid), ("title", scrub(name, 160)), ("value", val)) if v})
        for a in nodes(lp, "RealizedLocation/Address"):
            p = ", ".join(x for x in (first(a, "CityName"), first(a, "PostalZone"), first(a, "CountrySubentityCode"),
                                      first(a, "Country/IdentificationCode")) if x)
            if p and p not in places:
                places.append(p)
        for pp in nodes(lp, "PlannedPeriod"):
            dm = nodes(pp, "DurationMeasure")
            d = f"{text(dm[0])} {attr(dm[0], 'unitCode').lower()}".strip() if dm and text(dm[0]) else ""
            s_, e_ = _date(first(pp, "StartDate")), _date(first(pp, "EndDate"))
            v = d or (f"{s_} to {e_}" if s_ or e_ else "")
            if v and v not in durations:
                durations.append(v)
        tt = (nodes(lot, "TenderingTerms") or [{}])[0]
        for g in nodes(tt, "RequiredFinancialGuarantee"):
            code = first(g, "GuaranteeTypeCode").lower()
            desc_g = scrub(first(g, "Description"), 300)
            amt_g = nodes(g, "LiabilityAmount")
            amount = f"{text(amt_g[0])} {attr(amt_g[0], 'currencyID')}".strip() if amt_g and text(amt_g[0]) else ""
            if code in ("true", "false"):
                guarantees.append({"lot": lid, "required": code == "true", **({"terms": desc_g} if desc_g else {}),
                                   **({"amount": amount} if amount else {})})
        for d in nodes(tt, "CallForTendersDocumentReference"):
            u = first(d, "Attachment/ExternalReference/URI")
            if u:
                u = html.unescape(u)
                if not any(x["url"] == u for x in docs):
                    docs.append({"url": u, "type": first(d, "DocumentType") or "procurement documents"})
        for c in nodes(tt, "AwardingTerms/AwardingCriterion/SubordinateAwardingCriterion"):
            typ = first(c, "AwardingCriterionTypeCode")
            w = ""
            for prm in nodes(c, "UBLExtensions/UBLExtension/ExtensionContent/EformsExtension/AwardCriterionParameter"):
                if first(prm, "ParameterCode") in ("per-exa", "poi-exa", "per-ran", "poi-ran", "wei"):
                    w = first(prm, "ParameterNumeric")
            row = {"lot": lid, "type": CRIT.get(typ, typ), "name": scrub(first(c, "Name") or first(c, "Description"), 120)}
            if w:
                row["weight"] = w
            crit_rows.append(row)
            texts.append(first(c, "Description"))
        for sc in nodes(tt, "UBLExtensions/UBLExtension/ExtensionContent/EformsExtension/SelectionCriteria"):
            if first(sc, "CriterionTypeCode") or first(sc, "TendererRequirementTypeCode"):
                code = first(sc, "CriterionTypeCode") or first(sc, "TendererRequirementTypeCode")
                d = first(sc, "Description")
                texts.append(d)
                row = {"type": sel_label(code), "text": scrub(d, 400)}
                if row not in sel_rows:
                    sel_rows.append(row)
        for er in nodes(tt, "ContractExecutionRequirement"):
            if attr((nodes(er, "ExecutionRequirementCode") or [{}])[0], "listName") == "conditions":
                texts.append(first(er, "Description"))
        ep = first(tt, "TenderRecipientParty/EndpointID")
        if ep and html.unescape(ep) not in urls:
            urls.append(html.unescape(ep))
        vd = nodes(tt, "TenderValidityPeriod/DurationMeasure")
        if vd and text(vd[0]):
            v = f"{text(vd[0])} {attr(vd[0], 'unitCode').lower()}"
            if v not in validity:
                validity.append(v)
        vc = first(tt, "VariantConstraintCode")
        if vc and vc not in variants:
            variants.append(vc)
        tp = (nodes(lot, "TenderingProcess") or [{}])[0]
        for p in nodes(tp, "AdditionalInformationRequestPeriod"):
            d = _deadline(p)
            if d and d not in clar:
                clar.append(d)
        for p in nodes(tp, "TenderSubmissionDeadlinePeriod"):
            d = _deadline(p)
            if d and d not in subm:
                subm.append(d)
        for cs in nodes(tp, "ContractingSystem/ContractingSystemTypeCode"):
            if attr(cs, "listName") == "framework-agreement" and text(cs) not in ("none", ""):
                fw.append(text(cs))
    # notice-level terms (lot distribution; some publishers put documents and guarantees here)
    ntt = (nodes(cn, "TenderingTerms") or [{}])[0]
    for d in nodes(ntt, "CallForTendersDocumentReference"):
        u = first(d, "Attachment/ExternalReference/URI")
        if u and not any(x["url"] == html.unescape(u) for x in docs):
            docs.append({"url": html.unescape(u), "type": first(d, "DocumentType") or "procurement documents"})
    maxsub = first(ntt, "LotDistribution/MaximumLotsSubmittedNumeric")
    maxaw = first(ntt, "LotDistribution/MaximumLotsAwardedNumeric")
    proc = first(cn, "TenderingProcess/ProcedureCode")
    all_text = "\n".join(t for t in texts if t)
    # evaluation method: the award criteria with their weights, per lot when the lots differ
    ev = ""
    if crit_rows:
        by_lot = defaultdict(list)
        for c in crit_rows:
            by_lot[c["lot"]].append(c)
        sigs = {tuple((c["type"], c.get("weight", "")) for c in v) for v in by_lot.values()}
        sample = next(iter(by_lot.values()))
        kinds = {c["type"] for c in sample}
        head = "lowest price" if kinds == {"price"} else "lowest cost" if kinds == {"cost"} else "best price-quality ratio"
        parts = [f"{c['type']}{(' ' + c['weight']) if c.get('weight') else ''}: {c['name']}" for c in sample]
        ev = {"method": head, "criteria": parts[:12]}
        if len(sigs) > 1:
            ev["note"] = f"criteria differ between the {len(by_lot)} lots; shown for lot {sample[0]['lot']}"
    elig = sel_rows[:]
    for s_ in find_all(TURNOVER, all_text, 2) + find_all(EXPERIENCE, all_text, 2):
        if not any(s_ in (r.get("text") or "") for r in elig):
            elig.append({"type": "quoted from the notice", "text": s_})
    gb = ""
    if guarantees:
        req = [g for g in guarantees if g["required"]]
        if req:
            gb = {"required": True, "lots": len(req), "terms": next((g.get("terms") for g in req if g.get("terms")), ""),
                  **({"amount": next(g["amount"] for g in req if g.get("amount"))} if any(g.get("amount") for g in req) else {})}
            gb = {k: v for k, v in gb.items() if v not in ("", None)}
        else:
            gb = {"required": False}
    perf = find_all(PERF, all_text, 2)
    if not gb:
        quoted = find_all(BID_SEC, all_text, 2)
        gb = {"quoted": quoted} if quoted else ""
    deliv = {}
    if places:
        deliv["place"] = places[:6]
    if durations:
        deliv["period"] = durations[:4]
    inc = incoterms(all_text)
    if inc:
        deliv["incoterms"] = inc
    dt_ = find_all(DELIV, all_text, 2)
    if dt_:
        deliv["delivery_time_quoted"] = dt_
    lots_v = ""
    if lots:
        lots_v = {"count": len(lots), "lots": lot_rows[:40]}
        if maxsub:
            lots_v["max_lots_per_tenderer"] = maxsub
        if maxaw:
            lots_v["max_lots_awarded"] = maxaw
    out = {
        "items": field(items[:60], src, at, "eForms lots: name, CPV (BT-262), quantity (BT-25) or quantities quoted from the lot description"),
        "technical_standards": field(standards(all_text), src, at, "standards named in the notice text (lot descriptions, criteria)"),
        "delivery": field(deliv, src, at, "eForms place of performance (BT-5071/5131), duration (BT-36), terms quoted from the notice"),
        "bid_security": field(gb, src, at, "eForms tender guarantee (BT-751 required, BT-75 description)" if guarantees else "notice text"),
        "performance_guarantee": field({"quoted": perf} if perf else "", src, at, "notice text (eForms has no structured field)"),
        "eligibility": field(elig[:10], src, at, "eForms selection criteria (BT-747/750) and thresholds quoted from the notice"),
        "lots": field(lots_v, src, at, "eForms lots (BT-137) and lot distribution (BT-31/33)"),
        "evaluation": field(ev, src, at, "eForms award criteria (BT-539 type, BT-541 weight, BT-540 description)"),
        "clarification_deadline": field(clar[0] if len(clar) == 1 else clar, src, at, "eForms additional information deadline (BT-13)"),
        "documents": field(docs[:10], src, at, "eForms procurement documents URL (BT-15)"),
        "submission_deadline": field(subm[0] if len(subm) == 1 else subm, src, at, "eForms tender submission deadline (BT-131)"),
        "submission_url": field(urls[:3], src, at, "eForms submission URL (BT-18)"),
        "duration": field(durations[:4], src, at, "eForms duration (BT-36/536/537)"),
        "tender_validity": field(validity[:2], src, at, "eForms tender validity (BT-98)"),
        "variants": field(variants[:2], src, at, "eForms variants (BT-63)"),
        "framework": field(fw[:1], src, at, "eForms framework agreement (BT-765)"),
        "procedure": field(proc, src, at, "eForms procedure type (BT-105)"),
    }
    return out


# ---------------------------------------------------------------- Prozorro (Ukraine)
def parse_prozorro(d, src, at):
    items, lots, docs, sel, crit, perf, bidsec = [], [], [], [], [], [], ""
    for it in d.get("items") or []:
        x = {"name": scrub(it.get("description_en") or it.get("description"), 200)}
        if it.get("quantity") is not None:
            u = (it.get("unit") or {})
            x["quantity"] = f"{it['quantity']} {u.get('name') or u.get('code') or ''}".strip()
        c = (it.get("classification") or {}).get("id")
        if c:
            x["cpv"] = c
        if it.get("relatedLot"):
            x["lot"] = it["relatedLot"][:8]
        items.append(x)
    for lt in d.get("lots") or []:
        v = lt.get("value") or {}
        lots.append({"id": (lt.get("id") or "")[:8], "title": scrub(lt.get("title_en") or lt.get("title"), 160),
                     **({"value": f"{v.get('amount')} {v.get('currency', '')}".strip()} if v.get("amount") else {})})
    g = d.get("guarantee") or {}
    lg = [lt.get("guarantee") for lt in d.get("lots") or [] if (lt.get("guarantee") or {}).get("amount")]
    if g.get("amount"):
        bidsec = {"required": True, "amount": f"{g['amount']} {g.get('currency', '')}".strip()}
    elif lg:
        bidsec = {"required": True, "amount_per_lot": [f"{x['amount']} {x.get('currency', '')}".strip() for x in lg[:10]]}
    for c in d.get("criteria") or []:
        cid = ((c.get("classification") or {}).get("id") or "")
        title = scrub(c.get("title_en") or c.get("title"), 200)
        desc = scrub(c.get("description_en") or c.get("description"), 300)
        if cid.startswith("CRITERION.SELECTION"):
            sel.append({"type": cid.replace("CRITERION.SELECTION.", "").lower().replace("_", " ").replace(".", ": "), "text": title + (f": {desc}" if desc else "")})
        elif cid == "CRITERION.OTHER.CONTRACT.GUARANTEE":
            perf.append(title + (f": {desc}" if desc else ""))
        elif cid == "CRITERION.OTHER.BID.GUARANTEE" and not bidsec:
            bidsec = {"required": True, "terms": title + (f": {desc}" if desc else "")}
    for f_ in d.get("features") or []:
        crit.append(f"{scrub(f_.get('title_en') or f_.get('title'), 100)} (non-price, max {max([e.get('value', 0) for e in f_.get('enum') or [{}]] or [0])})")
    for doc in d.get("documents") or []:
        if doc.get("url") and doc.get("documentOf", "tender") in ("tender", "lot"):
            docs.append({"url": doc["url"], "type": doc.get("documentType") or "document", "title": scrub(doc.get("title"), 120)})
    ac = d.get("awardCriteria") or ""
    ev = ""
    if ac:
        ev = {"method": {"lowestCost": "lowest price", "rating": "rating (price and other criteria)", "lifeCycleCost": "life-cycle cost"}.get(ac, ac)}
        if crit:
            ev["criteria"] = crit[:10]
    places, dates = [], []
    for it in d.get("items") or []:
        a = it.get("deliveryAddress") or {}
        p = ", ".join(x for x in (a.get("locality"), a.get("region"), a.get("countryName_en") or a.get("countryName")) if x)
        if p and p not in places:
            places.append(p)
        e = _date((it.get("deliveryDate") or {}).get("endDate"))
        if e and e not in dates:
            dates.append(e)
    deliv = {k: v for k, v in (("place", places[:6]), ("deliver_by", dates[:4])) if v}
    txt = " ".join([d.get("description_en") or d.get("description") or ""] + [i.get("description") or "" for i in d.get("items") or []])
    enq = _date((d.get("enquiryPeriod") or {}).get("endDate"))
    return {
        "items": field(items[:80], src, at, "Prozorro items: description, quantity, unit, CPV"),
        "technical_standards": field(standards(txt), src, at, "standards named in the tender and item descriptions"),
        "delivery": field(deliv, src, at, "Prozorro items: delivery address and delivery date"),
        "bid_security": field(bidsec, src, at,
                              "Prozorro tender/lot guarantee (amount) and ESPD criterion OTHER.BID.GUARANTEE"),
        "performance_guarantee": field({"terms": perf} if perf else "", src, at, "Prozorro ESPD criterion OTHER.CONTRACT.GUARANTEE"),
        "eligibility": field(sel[:10], src, at, "Prozorro ESPD selection criteria"),
        "lots": field({"count": len(lots), "lots": lots[:40]} if lots else "", src, at, "Prozorro lots"),
        "evaluation": field(ev, src, at, "Prozorro awardCriteria and non-price features"),
        "clarification_deadline": field(enq, src, at, "Prozorro enquiry period end"),
        "documents": field(docs[:15], src, at, "Prozorro tender documents"),
        "submission_deadline": field(_date((d.get("tenderPeriod") or {}).get("endDate")), src, at, "Prozorro tender period end"),
        "procedure": field(d.get("procurementMethodType") or "", src, at, "Prozorro procurementMethodType"),
    }


# ---------------------------------------------------------------- PNCP (Brazil)
def parse_pncp(compra, itens, arquivos, srcs, at):
    src_c, src_i, src_a = srcs
    items, judging = [], []
    for it in itens or []:
        x = {"item": it.get("numeroItem"), "name": scrub(it.get("descricao"), 200)}
        if it.get("quantidade") is not None:
            x["quantity"] = f"{it['quantidade']} {it.get('unidadeMedida') or ''}".strip()
        if it.get("valorUnitarioEstimado"):
            x["unit_price_est"] = f"{it['valorUnitarioEstimado']} BRL"
        items.append(x)
        j = it.get("criterioJulgamentoNome")
        if j and j not in judging:
            judging.append(j)
    docs = [{"url": a.get("url") or a.get("uri"), "type": a.get("tipoDocumentoNome") or "documento", "title": scrub(a.get("titulo"), 120)}
            for a in arquivos or [] if a.get("url") or a.get("uri")]
    txt = f"{compra.get('objetoCompra') or ''}. {compra.get('informacaoComplementar') or ''}"
    perf = find_all(PERF, txt, 2)
    bid = find_all(BID_SEC, txt, 2)
    deliv = {}
    un = compra.get("unidadeOrgao") or {}
    if un.get("municipioNome"):
        deliv["buyer_unit_location"] = f"{un.get('municipioNome')}, {un.get('ufSigla', '')}".strip(", ")
    dq = find_all(DELIV, txt, 2)
    if dq:
        deliv["delivery_time_quoted"] = dq
    return {
        "items": field(items[:120], src_i, at, "PNCP itens: descricao, quantidade, unidadeMedida, valorUnitarioEstimado"),
        "technical_standards": field(standards(txt + " " + " ".join(i.get("descricao") or "" for i in itens or [])), src_i, at,
                                     "standards named in the purchase object and item descriptions"),
        "delivery": field(deliv, src_c, at, "PNCP purchase record (buyer unit) and terms quoted from it"),
        "bid_security": field({"quoted": bid} if bid else "", src_c, at, "purchase record text (PNCP has no structured field)"),
        "performance_guarantee": field({"quoted": perf} if perf else "", src_c, at, "purchase record text (PNCP has no structured field)"),
        "eligibility": field("", src_c, at, "not in the PNCP record (the edital document holds it)"),
        "lots": field({"count": len(items), "note": "each item is judged separately"} if judging and all("item" in j.lower() for j in judging) else "",
                      src_i, at, "PNCP item judging criterion"),
        "evaluation": field({"method": "; ".join(judging), "dispute": compra.get("modoDisputaNome") or ""} if judging else "", src_i, at,
                            "PNCP criterioJulgamentoNome per item, modoDisputaNome"),
        "clarification_deadline": field("", src_c, at, "not in the PNCP record"),
        "documents": field(docs[:15], src_a, at, "PNCP arquivos (edital, termo de referência)"),
        "submission_deadline": field(_date(compra.get("dataEncerramentoProposta")), src_c, at, "PNCP dataEncerramentoProposta"),
        "submission_url": field([compra["linkSistemaOrigem"]] if compra.get("linkSistemaOrigem") else [], src_c, at, "PNCP linkSistemaOrigem"),
        "procedure": field(compra.get("modalidadeNome") or "", src_c, at, "PNCP modalidadeNome"),
    }


# ---------------------------------------------------------------- ChileCompra
def parse_chile(x, src, at):
    items = []
    for it in ((x.get("Items") or {}).get("Listado") or []):
        r = {"name": scrub(f"{it.get('NombreProducto') or ''}: {it.get('Descripcion') or ''}".strip(": "), 200)}
        if it.get("Cantidad") is not None:
            r["quantity"] = f"{it['Cantidad']} {it.get('UnidadMedida') or ''}".strip()
        if it.get("CodigoProducto"):
            r["unspsc"] = str(it["CodigoProducto"])
        items.append(r)
    f = x.get("Fechas") or {}
    txt = f"{x.get('Nombre') or ''}. {x.get('Descripcion') or ''}"
    dur = ""
    if x.get("TiempoDuracionContrato"):
        dur = f"{x['TiempoDuracionContrato']} {({'1': 'hours', '2': 'days', '3': 'weeks', '4': 'months', '5': 'years'}).get(str(x.get('UnidadTiempoDuracionContrato')), '')}".strip()
    deliv = {k: v for k, v in (("period", [dur] if dur else []), ("delivery_time_quoted", find_all(DELIV, txt, 2))) if v}
    perf = find_all(PERF, txt, 2)
    bid = find_all(BID_SEC, txt, 2)
    return {
        "items": field(items[:120], src, at, "ChileCompra Items: NombreProducto, Descripcion, Cantidad, UnidadMedida"),
        "technical_standards": field(standards(txt + " " + " ".join(i["name"] for i in items)), src, at, "standards named in the tender and item descriptions"),
        "delivery": field(deliv, src, at, "ChileCompra TiempoDuracionContrato and terms quoted from the description"),
        "bid_security": field({"quoted": bid} if bid else "", src, at, "tender description (the API has no guarantee field)"),
        "performance_guarantee": field({"quoted": perf} if perf else "", src, at, "tender description (the API has no guarantee field)"),
        "eligibility": field("", src, at, "not in the API record (the bases document holds it)"),
        "lots": field("", src, at, "not in the API record"),
        "evaluation": field("", src, at, "not in the API record (the bases document holds it)"),
        "clarification_deadline": field(_date(f.get("FechaFinal")), src, at, "ChileCompra Fechas.FechaFinal (end of questions)"),
        "documents": field([], src, at, "the API lists no document links"),
        "submission_deadline": field(_date(f.get("FechaCierre")), src, at, "ChileCompra Fechas.FechaCierre"),
        "duration": field([dur] if dur else [], src, at, "ChileCompra TiempoDuracionContrato"),
        "procedure": field(x.get("Tipo") or "", src, at, "ChileCompra Tipo"),
    }


# ---------------------------------------------------------------- World Bank (notice text)
WB_LOT = re.compile(r"\bLot[s]?\s*(?:No\.?\s*)?(\d{1,3})\s*[:\-–]\s*([^\n;]{3,140})", re.I)
WB_ELIG = re.compile(r"(?:qualification (?:requirements|criteria)|eligib\w+|minimum (?:average )?annual turnover|"
                     r"specific experience|general experience|financial capacity)[^\n]{0,260}", re.I)
WB_DOCS = re.compile(r"https?://[^\s\"'<>)]+", re.I)
WB_CLAR = re.compile(r"(?:clarification|questions?|queries)[^\n.]{0,120}?(\d{1,2}(?:st|nd|rd|th)?\s+[A-Z][a-z]+,?\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})", re.I)


def parse_worldbank(n, src, at):
    raw = n.get("notice_text") or ""
    t = re.sub(r"<\s*(br|/p|/li|/tr|/div|/h\d)\s*/?>", "\n", raw, flags=re.I)
    t = html.unescape(html.unescape(re.sub(r"<[^>]{0,400}>", " ", t)))
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    lots = []
    for m in WB_LOT.finditer(t):
        r = {"id": m.group(1), "title": scrub(m.group(2), 140)}
        if r not in lots:
            lots.append(r)
    bid = find_all(BID_SEC, t, 2)
    perf = find_all(PERF, t, 2)
    elig = [{"type": "quoted from the notice", "text": scrub(m.group(0), 300)} for m in list(WB_ELIG.finditer(t))[:6]]
    docs = []
    for u in WB_DOCS.findall(raw):
        u = html.unescape(u).rstrip(".,;")
        if not EMAIL.search(u) and u not in [d["url"] for d in docs] and len(docs) < 8:
            docs.append({"url": u, "type": "link in the notice"})
    clar = [m.group(1) for m in WB_CLAR.finditer(t)][:2]
    deliv = {k: v for k, v in (("incoterms", incoterms(t)),
                                ("delivery_time_quoted", find_all(DELIV, t, 2))) if v}
    ev = find_all(re.compile(r"lowest evaluated (?:bid|cost)|most advantageous bid|rated criteria|quality.cost based", re.I), t, 2)
    items = [{"name": scrub(n.get("bid_description"), 300)}] if n.get("bid_description") else []
    q = find_all(QTY, t, 4)
    if q and items:
        items[0]["quantity_in_text"] = q
    return {
        "items": field(items, src, at, "World Bank notice: bid description and quantities quoted from the notice text"),
        "technical_standards": field(standards(t), src, at, "standards named in the notice text"),
        "delivery": field(deliv, src, at, "notice text"),
        "bid_security": field({"quoted": bid} if bid else "", src, at, "notice text (World Bank procurement notice)"),
        "performance_guarantee": field({"quoted": perf} if perf else "", src, at, "notice text"),
        "eligibility": field(elig, src, at, "notice text: qualification and eligibility paragraphs"),
        "lots": field({"count": len(lots), "lots": lots[:30]} if lots else "", src, at, "notice text: lots listed"),
        "evaluation": field({"quoted": ev} if ev else "", src, at, "notice text"),
        "clarification_deadline": field(clar, src, at, "notice text"),
        "documents": field(docs, src, at, "links printed in the notice"),
        "submission_deadline": field(_date(n.get("submission_deadline_date")), src, at, "World Bank submission_deadline_date"),
        "procedure": field(n.get("procurement_method_name") or "", src, at, "World Bank procurement_method_name"),
    }


# ---------------------------------------------------------------- fetching (one publisher at a time, with a pause)
def _session():
    import requests
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en;q=0.9"})
    return s


def _get(s, url, kind="json", tries=3, **kw):
    """GET with a short back-off on 429/5xx. Returns (status, body) where body is parsed JSON or bytes."""
    last = 0
    for i in range(tries):
        try:
            r = s.get(url, timeout=60, **kw)
        except Exception as e:  # noqa: BLE001
            last = type(e).__name__; time.sleep(3 * (i + 1)); continue
        last = r.status_code
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(int(r.headers.get("Retry-After") or 0) or 5 * (i + 1)); continue
        if r.status_code != 200:
            return r.status_code, None
        if kind == "json":
            try:
                return 200, r.json()
            except ValueError:
                return "bad json", None
        return 200, r.content
    return last, None


def ted_url(tid):
    return f"https://ted.europa.eu/en/notice/{tid.replace('TED-', '', 1)}/xml"


def fetch_one(s, row, ctx):
    """(fields, raw bytes, source url) for one tender row, or (None, reason, url)."""
    kind, tid, at = SOURCES.get(row["source"]), row["id"], dt.date.today().isoformat()
    if kind == "ted":
        url = ted_url(tid)
        st, raw = _get(s, url, kind="bytes")
        if raw is None:
            return None, f"HTTP {st}", url
        try:
            f = parse_eforms(xml_tree(raw), url, at)
        except ET.ParseError:
            return None, "not XML", url
        return (f, raw, url) if f else (None, "not an eForms competition notice", url)
    if kind == "boamp":
        idweb = tid.replace("FR-", "", 1)
        url = ("https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/records?limit=1&where="
               + quote(f'idweb="{idweb}"'))
        st, j = _get(s, url)
        rec = ((j or {}).get("results") or [None])[0]
        if not rec:
            return None, f"HTTP {st}" if j is None else "not found", url
        try:
            don = json.loads(rec.get("donnees") or "{}")
        except ValueError:
            return None, "bad donnees", url
        ef = don.get("EFORMS")
        if not ef:
            return None, "national BOAMP format (not eForms)", url
        f = parse_eforms(json_tree(ef), url, at)
        return (f, json.dumps(ef, ensure_ascii=False).encode(), url) if f else (None, "not a competition notice", url)
    if kind == "prozorro":
        pz = ctx.get("prozorro", {}).get(tid)
        if not pz:
            return None, "internal id unknown", row.get("link", "")
        url = f"https://public-api.prozorro.gov.ua/api/2.5/tenders/{pz}"
        st, j = _get(s, url)
        d = (j or {}).get("data")
        if not d:
            return None, f"HTTP {st}", url
        return parse_prozorro(d, url, at), json.dumps(d, ensure_ascii=False).encode(), url
    if kind == "pncp":
        m = re.match(r"PNCP-(\d{14})-\d+-(\d+)/(\d{4})$", tid)
        if not m:
            return None, "id format", row.get("link", "")
        cnpj, seq, ano = m.group(1), int(m.group(2)), m.group(3)
        u_c = f"https://pncp.gov.br/api/consulta/v1/orgaos/{cnpj}/compras/{ano}/{seq}"
        u_i = f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens?pagina=1&tamanhoPagina=200"
        u_a = f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos"
        st, compra = _get(s, u_c)
        if not compra:
            return None, f"HTTP {st}", u_c
        time.sleep(PAUSE["pncp"]); _, itens = _get(s, u_i)
        time.sleep(PAUSE["pncp"]); _, arqs = _get(s, u_a)
        raw = json.dumps({"compra": compra, "itens": itens, "arquivos": arqs}, ensure_ascii=False).encode()
        return parse_pncp(compra, itens if isinstance(itens, list) else [], arqs if isinstance(arqs, list) else [], (u_c, u_i, u_a), at), raw, u_c
    if kind == "chile":
        ticket = os.environ.get("CHILE_TICKET", "")
        code = tid.replace("CL-", "", 1)
        url = f"https://api.mercadopublico.cl/servicios/v1/publico/licitaciones.json?codigo={code}"
        if not ticket:
            return None, "no API ticket", url
        st, j = _get(s, url, params={"ticket": ticket})
        x = ((j or {}).get("Listado") or [None])[0]
        if not x:
            return None, f"HTTP {st}", url
        x = {k: v for k, v in x.items() if k not in ("Comprador",) and "Responsable" not in k and "Email" not in k}
        return parse_chile(x, url, at), json.dumps(x, ensure_ascii=False).encode(), url
    if kind == "worldbank":
        op = tid.replace("WB-", "", 1)
        url = f"https://search.worldbank.org/api/v2/procnotices?format=json&id={op}"
        st, j = _get(s, url)
        n = ((j or {}).get("procnotices") or [None])[0]
        if not n:
            return None, f"HTTP {st}", url
        keep = {k: n.get(k) for k in ("id", "notice_text", "bid_description", "submission_deadline_date", "procurement_method_name",
                                      "notice_type", "project_ctry_name", "project_id")}
        return parse_worldbank(keep, url, at), json.dumps(keep, ensure_ascii=False).encode(), url
    return None, "unsupported source", row.get("link", "")


# ---------------------------------------------------------------- selection and storage
def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def open_tenders():
    """Open tender rows from the published index (data/leads/sheet/tenders_*.csv) with the fit score."""
    import glob
    fit = {}
    fp = LEADS / "fit.csv"
    if fp.exists():
        for r in csv.DictReader(open(fp, encoding="utf-8")):
            fit[r["id"]] = _num(r.get("base_score"))
    rows = []
    for f in sorted(glob.glob(str(LEADS / "sheet" / "tenders_[0-9][0-9].csv"))):
        for r in csv.DictReader(open(f, encoding="utf-8")):
            if r.get("id"):
                r["_fit"] = fit.get(r["id"]) or _num(r.get("score"))
                rows.append(r)
    return rows


def eligible(r, today):
    if r.get("source") not in SOURCES or r.get("sector") not in FOCUS or (r.get("stage") or "tender") != "tender":
        return False
    d = _date(r.get("deadline"))
    return bool(d) and d >= (today + dt.timedelta(days=MIN_DAYS)).isoformat()


def priority(r):
    return (-r["_fit"], -_num(r.get("est_value_usd")))


def load_store():
    out = {}
    if STORE.exists():
        with gzip.open(STORE, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line); out[d["id"]] = d
                except (ValueError, KeyError):
                    pass
    return out


def save_store(store):
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        for d in store.values():
            f.write(json.dumps(d, ensure_ascii=False, separators=(",", ":")) + "\n")
    tmp.replace(STORE)


def prozorro_ids():
    p = LEADS / "cache" / "prozorro.jsonl"
    out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("id") and d.get("pz_id"):
                out[d["id"]] = d["pz_id"]
    return out


def due(rec, row, today):
    if not rec or rec.get("version") != VERSION:
        return True
    if rec.get("deadline") != _date(row.get("deadline")):
        return True  # deadline moved: an amendment, read again
    return rec.get("read", "") < (today - dt.timedelta(days=REFRESH_DAYS)).isoformat()


def n_filled(fields):
    return sum(1 for k in FIELDS if filled(fields.get(k)))


def publish(store, open_ids):
    """Open tenders with details -> the public CSV the app joins to the tender card (compact JSON per row)."""
    PUB.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for d in store.values():
        if d["id"] not in open_ids or not d.get("fields"):
            continue
        f = {k: d["fields"][k] for k in FIELDS + EXTRA if k in d["fields"]}
        rows.append({"id": d["id"], "source": d.get("source", ""), "refined": d.get("read", ""), "filled": n_filled(d["fields"]),
                     "details": json.dumps({"v": VERSION, "src": d.get("url", ""), "f": f}, ensure_ascii=False, separators=(",", ":"))})
    rows.sort(key=lambda r: r["id"])
    with open(PUB, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "source", "refined", "filled", "details"]); w.writeheader(); w.writerows(rows)
    return rows


def has_quantities(fields):
    """Items with a stated quantity (structured, or quoted from the notice text)."""
    v = (fields.get("items") or {}).get("v")
    return isinstance(v, list) and any(isinstance(i, dict) and (i.get("quantity") or i.get("quantity_in_text")) for i in v)


def fill_rates(recs):
    """Per field: share of records where the official record states it; per source as well. 'quantities' counts the
    records whose items carry a quantity (an item list without quantities is not enough to price a bid)."""
    out, by_src = {}, defaultdict(lambda: Counter())
    n = len(recs)
    for k in FIELDS + EXTRA:
        c = sum(1 for d in recs if filled(d["fields"].get(k)))
        out[k] = {"filled": c, "of": n, "rate": round(c / n, 3) if n else 0}
    c = sum(1 for d in recs if has_quantities(d["fields"]))
    out["quantities"] = {"filled": c, "of": n, "rate": round(c / n, 3) if n else 0}
    for d in recs:
        b = by_src[d.get("source", "")]
        b["n"] += 1
        for k in FIELDS:
            b[k] += 1 if filled(d["fields"].get(k)) else 0
        b["quantities"] += 1 if has_quantities(d["fields"]) else 0
    return out, {s: {"n": c["n"], **{k: round(c[k] / c["n"], 2) for k in FIELDS + ["quantities"]}} for s, c in by_src.items()}


def run(limit=400, minutes=25, ids=None, sample=0):
    today = dt.date.today()
    t0 = time.time()
    rows = open_tenders()
    open_ids = {r["id"] for r in rows if _date(r.get("deadline")) >= today.isoformat() or not _date(r.get("deadline"))}
    cand = [r for r in rows if eligible(r, today)]
    if ids:
        want = set(ids)
        cand = [r for r in rows if r["id"] in want]
    cand.sort(key=priority)
    store = load_store()
    ctx = {"prozorro": prozorro_ids()}
    if sample:
        # a stratified sample: the best-ranked open tenders of each supported publisher, in proportion to the open
        # focus set but at least 3 per publisher that has any
        share = Counter(r["source"] for r in cand)
        tot = sum(share.values()) or 1
        quota = {s: max(3, round(sample * c / tot)) for s, c in share.items()}
        while sum(quota.values()) > sample:
            s_ = max(quota, key=lambda k: quota[k]); quota[s_] -= 1
        picked, cnt = [], Counter()
        for r in cand:
            if cnt[r["source"]] < quota.get(r["source"], 0):
                picked.append(r); cnt[r["source"]] += 1
        todo = picked
    else:
        todo = [r for r in cand if due(store.get(r["id"]), r, today)][:limit]
    log.info("tender details: %d open focus tenders from supported publishers, %d to read now (%s)", len(cand), len(todo),
             dict(Counter(r["source"] for r in todo)))
    s = _session()
    done, fails, raws = [], Counter(), {}
    for r in todo:
        if time.time() - t0 > minutes * 60:
            log.info("tender details: time budget reached after %d", len(done)); break
        kind = SOURCES[r["source"]]
        try:
            f, raw, url = fetch_one(s, r, ctx)
        except Exception as e:  # noqa: BLE001
            f, raw, url = None, type(e).__name__, ""
        time.sleep(PAUSE.get(kind, 1.0))
        if f is None:
            fails[f"{kind}: {raw}"] += 1
            continue
        rec = {"id": r["id"], "source": r["source"], "url": url, "read": today.isoformat(), "version": VERSION,
               "deadline": _date(r.get("deadline")), "hash": hashlib.sha256(raw).hexdigest()[:16], "fields": f}
        store[r["id"]] = rec
        done.append(rec)
        if sample:
            raws[r["id"]] = raw
    # drop closed tenders from the store
    for k in [k for k, d in store.items() if d.get("deadline") and d["deadline"] < today.isoformat()]:
        store.pop(k)
    if not sample:
        save_store(store)
    pub = publish(store, open_ids) if not sample else []
    rates, per_src = fill_rates(done)
    stats = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "version": VERSION, "mode": "sample" if sample else "run",
             "read_now": len(done), "failed": dict(fails), "published_open": len(pub), "store": len(store),
             "fill_rate_this_run": rates, "by_source_this_run": per_src}
    if not sample:
        allrates, allsrc = fill_rates([d for d in store.values() if d["id"] in open_ids])
        stats["fill_rate_published"], stats["by_source_published"] = allrates, allsrc
    log.info("tender details: read %d, failed %s, published %d open, store %d", len(done), dict(fails), len(pub), len(store))
    for k in FIELDS + ["quantities"]:
        log.info("  fill %-24s %5.1f%% (%d/%d)", k, 100 * rates[k]["rate"], rates[k]["filled"], rates[k]["of"])
    for s_, v in per_src.items():
        log.info("  source %-20s n=%d %s", s_, v["n"], " ".join(f"{k[:5]}={v[k]:.2f}" for k in FIELDS + ["quantities"]))
    return stats, done, raws


def main(a):
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    mode = a[0] if a else "run"
    lim = int(a[a.index("--limit") + 1]) if "--limit" in a else 400
    mins = int(a[a.index("--minutes") + 1]) if "--minutes" in a else 25
    ids = a[a.index("--ids") + 1].split(",") if "--ids" in a else None
    if mode == "probe":  # development aid: how the publishers answer (status, type, size; no content)
        s = _session()
        for u in a[1:]:
            try:
                r = s.get(u, timeout=60, allow_redirects=True)
                print("PROBE", r.status_code, r.headers.get("content-type", ""), len(r.content), r.url[:120],
                      {k: v for k, v in r.headers.items() if k.lower() in ("x-amzn-waf-action", "server", "location", "retry-after", "content-disposition")},
                      repr(r.content[:160]) if r.status_code != 200 else "")
            except Exception as e:  # noqa: BLE001
                print("PROBE", u[:120], type(e).__name__)
        r = s.post("https://api.ted.europa.eu/v3/notices/search", json={"query": "publication-number=762189-2026", "fields": ["publication-number", "links", "ojs-number"], "limit": 1}, timeout=60)
        print("PROBE api", r.status_code, r.text[:1500])
        return
    if mode == "sample":
        n = int(a[1]) if len(a) > 1 and a[1].isdigit() else 50
        stats, done, raws = run(sample=n, minutes=mins, ids=ids)
        (LEADS / "refined").mkdir(parents=True, exist_ok=True)
        (LEADS / "refined" / "tender_details_sample.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False))
        # the spot check: 10 records (spread over the publishers) with their raw official record, sealed to the reviewer
        from .source_cycle import save_sealed
        pick, seen = [], Counter()
        for d in done:
            if seen[d["source"]] < 3 and len(pick) < 10:
                pick.append(d); seen[d["source"]] += 1
        for d in done:
            if len(pick) >= 10:
                break
            if d not in pick:
                pick.append(d)
        blob = json.dumps({"sample": done, "raw": {d["id"]: raws[d["id"]].decode("utf-8", "replace") for d in pick}}, ensure_ascii=False)
        p = save_sealed("tender_details_sample", gzip.compress(blob.encode("utf-8")))
        print(f"SAMPLE sealed {p} ({len(pick)} raw records, {len(done)} parsed)")
        return
    stats, _, _ = run(limit=lim, minutes=mins, ids=ids)
    STATS.parent.mkdir(parents=True, exist_ok=True)
    STATS.write_text(json.dumps(stats, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
