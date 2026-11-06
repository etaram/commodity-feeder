"""Sandbox run of the deal-agent workflows on the private supplier list (skills package, 6 Nov 2026).

  A  product request -> supplier shortlist (match_guard states) -> usable contacts -> RFQ draft (never sent)
  C  client development (RO systems) -> RO makers and the buyers that procure RO, desalination or water treatment

Nothing is sent, no account is created. Results go to the private sheet tab 'Workflow demos' (owner workspace only);
the log prints counts, never names or contacts. Matching uses the stated assertions of each record: a product
family, color or form is "evidenced" only when the company's own product text states it, so a directory row can
reach "plausible" but a missing specification is a gap, not a fit."""
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

from .common import PRIVATE, log
from .validate import email_ok, phone_ok, url_ok

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / ".claude" / "skills" / "sinder-supplier-matching" / "scripts"))
from match_guard import classify  # noqa: E402

MAIZE = re.compile(r"\b(maize|corn)\b(?![\s-]+(flour|meal|starch|syrup|oil|flakes|grits|snacks?|chips|feed|silage|dogs?|seeds?))", re.I)
RO = re.compile(r"\b(reverse osmosis|ro (plants?|systems?|units?|membranes?)|desalinat\w*)\b", re.I)
AUTO = re.compile(r"\b(oil filters?|air filters?|fuel filters?|automotive|auto parts|car parts)\b", re.I)


def own_text(r):
    return " ".join(r.get(k, "") or "" for k in ("products", "about", "web_title", "industries", "goods"))


def assertions(r, family):
    t, out = own_text(r), []
    ev = f"universe:{r.get('supplier', '')}|{r.get('country', '')}"
    if family == "maize" and MAIZE.search(t):
        out.append({"property": "product_family", "value": "maize", "status": "source_statement", "evidence_id": ev})
        for col in ("white", "yellow"):
            if re.search(rf"\b{col} (maize|corn)\b", t, re.I):
                out.append({"property": "color", "value": col, "status": "source_statement", "evidence_id": ev})
        out.append({"property": "form", "value": "grain", "status": "source_statement", "evidence_id": ev})
    if family == "reverse osmosis system" and RO.search(t):
        out.append({"property": "product_family", "value": "reverse osmosis system", "status": "source_statement", "evidence_id": ev})
    return out


def contact(r):
    em = next((e.strip() for e in (r.get("email") or "").split(";") if email_ok(e.strip())), "")
    ph = next((p.strip() for p in (r.get("phone") or "").split(";") if phone_ok(p.strip(), r.get("country", ""))), "")
    web = r.get("website", "") if url_ok(r.get("website", "")) else ""
    return {"email": em, "phone": ph, "website": web, "usable": bool(em or ph or web)}


def rfq(req, r):
    return (f"Subject: Request for quotation - {req['label']}\n\nDear {r.get('supplier', '')} team,\n\n"
            f"We are preparing an offer for a buyer in {req['buyer_country']} and would like your quotation for:\n"
            f"- Product: {req['label']}\n- Quantity: {req['qty']}\n- Specification: {req['spec']}\n- Delivery: {req['incoterm']}\n\n"
            "Please state the price basis (Incoterm and named place), validity, lead time, payment terms, origin and the "
            "certificates you can provide.\n\nThis is a request for information, not an order or a commitment.\n\nSinder")


def shortlist(rows, family, mandatory, req, n=25):
    cands = []
    for r in rows:
        t = own_text(r)
        if family == "maize" and not re.search(r"\b(maize|corn)\b", t, re.I):
            continue
        if family == "reverse osmosis system" and not (RO.search(t) or re.search(r"\bfilters?\b", t, re.I)):
            continue
        asr = assertions(r, family)
        res = classify({"mandatory": mandatory}, {"entity_kind": "company", "assertions": asr, "evidence_text": t})
        if not any(x["property"] == "product_family" for x in asr):  # the word alone (flour, seed, filters) is not the product
            res = {**res, "state": "research", "review_flags": res.get("review_flags", []) + ["product not stated as such"]}
        if family == "reverse osmosis system" and AUTO.search(t) and not RO.search(t):
            res = {**res, "state": "incompatible", "review_flags": res.get("review_flags", []) + ["automotive filters"]}
        c = contact(r)
        rank = {"supported": 0, "plausible": 1, "research": 2, "incompatible": 3}[res["state"]]
        cands.append((rank, not c["usable"], -float(r.get("quality") or 0), r, res, c))
    cands.sort(key=lambda x: x[:3])
    states = {}
    for x in cands:
        states[x[4]["state"]] = states.get(x[4]["state"], 0) + 1
    top = [x for x in cands if x[4]["state"] in ("supported", "plausible")][:n]
    out = []
    for rank, _, _, r, res, c in top:
        out.append([req["id"], r.get("supplier", ""), r.get("country", ""), r.get("type", ""), res["state"], ", ".join(res.get("matched", [])),
                    ", ".join(res.get("gaps", []) + res.get("review_flags", [])), c["email"], c["phone"], c["website"],
                    "yes" if c["usable"] else "no", rfq(req, r) if c["usable"] and res["state"] == "supported" else ""])
    return out, states, len(cands)


def main():
    src = PRIVATE / "universe.csv"
    if not src.exists():
        log.info("workflow demo: no private universe in this run"); return
    rows = list(csv.DictReader(open(src, encoding="utf-8")))
    reqA = {"id": "A-white-maize", "label": "white maize, grade 1, non-GMO", "buyer_country": "KEN", "qty": "5,000 t", "spec": "white maize grade 1, moisture max 13.5%", "incoterm": "CFR Mombasa"}
    a, sa, na = shortlist(rows, "maize", {"product_family": "maize", "color": "white", "form": "grain"}, reqA)
    reqC = {"id": "C-RO-makers", "label": "reverse osmosis water treatment systems", "buyer_country": "SAU", "qty": "to be confirmed", "spec": "industrial RO, capacity per buyer", "incoterm": "to be agreed"}
    c, sc, nc = shortlist(rows, "reverse osmosis system", {"product_family": "reverse osmosis system"}, reqC)
    head = ["workflow", "company", "country", "type", "match state", "matched", "gaps and flags", "email", "phone", "website", "usable contact", "RFQ draft (not sent)"]
    summary = {"date": date.today().isoformat(), "universe": len(rows), "A": {"candidates": na, "states": sa, "shortlist": len(a), "usable": sum(r[10] == "yes" for r in a), "rfq_drafts": sum(bool(r[11]) for r in a)},
               "C": {"candidates": nc, "states": sc, "shortlist": len(c), "usable": sum(r[10] == "yes" for r in c)}}
    log.info("workflow demo: %s", json.dumps(summary))
    try:
        from .push import LEADS_SHEET, Sheets
        Sheets().replace_tab(LEADS_SHEET, "Workflow demos", [head] + a + c + [[json.dumps(summary)]], raw=True)
    except Exception as e:  # noqa: BLE001
        log.warning("workflow demo sheet: %s", e)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    main()
