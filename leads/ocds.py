"""Generic OCDS release -> tender row, shared by every source that publishes the Open Contracting Data Standard."""
from .common import clean
from .sectors import classify
from .taxonomy import match_cpv


def codes(tn, scheme):
    out = []
    c = tn.get("classification") or {}
    if (c.get("scheme") or "").upper().startswith(scheme) and c.get("id"):
        out.append(str(c["id"]))
    for it in tn.get("items") or []:
        for cl in [it.get("classification") or {}] + (it.get("additionalClassifications") or []):
            if (cl.get("scheme") or "").upper().startswith(scheme) and cl.get("id"):
                out.append(str(cl["id"]))
    return [x.split("-")[0] for x in dict.fromkeys(out)]


def tender_row(rel, *, source, prefix, country, lang="", access="National", link="", today_s=""):
    """Row for an OCDS release that carries an open tender; None if it is not open or has no tender."""
    tn = rel.get("tender") or {}
    if not tn or (tn.get("status") and tn["status"] not in ("active", "planned", "planning")):
        return None
    end = ((tn.get("tenderPeriod") or {}).get("endDate") or "")[:10]
    if end and today_s and end < today_s:
        return None
    cpv, unspsc = codes(tn, "CPV"), codes(tn, "UNSPSC")
    title = clean(tn.get("title") or "")
    desc = clean(tn.get("description") or "")
    text = f"{title} | {desc}" if desc and desc != title else title
    sector, method = classify(text, cpv=cpv or None, unspsc=unspsc[0] if unspsc else None)
    gid, depth = match_cpv(cpv[:1]) if cpv else (None, -1)
    buyer = rel.get("buyer") or {}
    party = next((p for p in rel.get("parties") or [] if "buyer" in (p.get("roles") or [])), {})
    cp = party.get("contactPoint") or buyer.get("contactPoint") or {}
    val = tn.get("value") or {}
    amt = val.get("amount")
    return {
        "id": f"{prefix}-{rel.get('ocid') or tn.get('id')}", "source": source, "group": gid or "",
        "match": depth if gid else "", "sector": sector, "nature": tn.get("mainProcurementCategory", ""),
        "cpv": " ".join(cpv[:6]), "classification": " ".join((cpv or unspsc)[:6]) or method,
        "country": country, "buyer": clean(buyer.get("name") or party.get("name"), 120), "title": text[:300],
        "notice_type": clean(tn.get("procurementMethodDetails") or tn.get("procurementMethod") or "", 60),
        "stage": "planned" if tn.get("status") in ("planned", "planning") else "tender", "access": access,
        "published": (rel.get("date") or "")[:10], "deadline": end,
        "value": amt if amt not in (None, "", 0) else "", "currency": val.get("currency", "") if amt else "",
        "link": link or ((tn.get("documents") or [{}])[0].get("url", "") if tn.get("documents") else ""),
        "contact": clean(f"{cp.get('email', '')} {cp.get('telephone', '')}", 120), "lang": lang,
    }
