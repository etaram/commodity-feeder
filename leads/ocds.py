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


def award_rows(rel, *, source, prefix, country):
    """Award rows (one per award with a named supplier) from an OCDS release."""
    out = []
    tn = rel.get("tender") or {}
    cpv = codes(tn, "CPV")
    title = clean(tn.get("title") or "")
    sector, _ = classify(title, cpv=cpv or None)
    gid, _ = match_cpv(cpv[:1]) if cpv else (None, -1)
    buyer = (rel.get("buyer") or {}).get("name") or ""
    parties = {p.get("id"): p for p in rel.get("parties") or []}
    bids = tn.get("numberOfTenderers", "")
    for i, a in enumerate(rel.get("awards") or []):
        sups = a.get("suppliers") or []
        names = [clean(s.get("name") or (parties.get(s.get("id")) or {}).get("name"), 100) for s in sups]
        names = [n for n in names if n]
        if not names:
            continue
        wc, contacts = [], []
        for s in sups:
            p = parties.get(s.get("id")) or {}
            addr = p.get("address") or s.get("address") or {}
            c = addr.get("countryName") or ""
            if c:
                wc.append(c)
            cp = p.get("contactPoint") or s.get("contactPoint") or {}
            ident = p.get("identifier") or s.get("identifier") or {}
            contacts.append({
                "name": clean(s.get("name") or p.get("name"), 120), "country": c,
                "email": clean(cp.get("email"), 120), "phone": clean(cp.get("telephone"), 60),
                "website": clean(cp.get("url") or p.get("url") or "", 120),
                "address": clean(" ".join(x for x in [addr.get("streetAddress"), addr.get("postalCode"),
                                                      addr.get("locality")] if x), 160),
                "legal_id": clean(f"{ident.get('scheme', '')}:{ident.get('id', '')}" if ident.get("id") else "", 60),
            })
        val = a.get("value") or {}
        out.append({
            "id": f"{prefix}-{rel.get('ocid', '')}-{a.get('id', i)}", "source": source, "group": gid or "",
            "sector": sector, "title": (clean(a.get("title")) or title)[:200], "buyer": clean(buyer, 120),
            "country": country, "cpv": " ".join(cpv[:4]), "published": (a.get("date") or rel.get("date") or "")[:10],
            "winners": names[:6], "winner_country": ",".join(dict.fromkeys(wc))[:40], "winner_size": "",
            "value": val.get("amount") if val.get("amount") not in (None, 0) else "", "currency": val.get("currency", ""),
            "bids": bids if isinstance(bids, int) else "", "email": "", "link": "",
            "contacts": contacts,
        })
    return out
