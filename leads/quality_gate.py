"""Quality gate v1 for suppliers (owner, 13 Nov 2026: quality decides; only real information you can work with).

A supplier is REFINED only when every condition holds, each from evidence the system holds:
  identity   a company name and a valid ISO 3166 alpha-3 country (a legal id from a register or the site makes it 'strong')
  site       its own website was read and the name on the site matches the record (verdict ok, name match high)
  role       the site states what it is: manufacturer / producer, trader / distributor, contractor, service (a phrase found)
  products   at least two product or category phrases from the site that are not navigation or boilerplate
  contact    an official business contact published by the company: an email on the company's own domain, or a phone
  fresh      checked within FRESH_DAYS (the re-check rule)
Missing or failing conditions are counted per reason; nothing is filled by guessing. The gate never deletes a record.

  python -m leads.quality_gate <enrich dir>   counts only (public log); writes <dir>/refined.keys (private, root only)
"""
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path

VERSION = "supplier-gate-1 (2026-11-13)"
FRESH_DAYS = 180
ISO3 = re.compile(r"^[A-Z]{3}$")
NAV = re.compile(r"^(home|homepage|about|about us|who we are|contact|contact us|contacts|news|blog|careers?|jobs|privacy|"
                 r"cookie|cookies|terms|login|log in|sign in|register|search|menu|faq|sitemap|our company|company|team|"
                 r"our team|history|mission|vision|gallery|downloads?|media|events?|partners?|clients|references|"
                 r"welcome|follow us|social|newsletter|quick links|links|useful links|support|help|services|our services|"
                 r"products|our products|solutions|industries|projects|read more|learn more|more|top|language|english|"
                 r"inicio|contacto|nosotros|empresa|accueil|qui sommes-nous|startseite|kontakt|impressum|uber uns|über uns)$", re.I)
ROLE_OK = {"manufacturer", "producer", "trader", "distributor", "exporter", "contractor", "service", "supplier", "importer", "wholesaler"}


def product_phrases(rec):
    out = []
    for p in rec.get("products") or []:
        t = re.sub(r"\s+", " ", str(p)).strip(" -|:·•")
        if len(t) < 3 or len(t) > 80 or NAV.match(t) or re.fullmatch(r"[\W\d_]+", t):
            continue
        if re.search(r"(©|copyright|all rights|cookie|privacy|javascript|\bcall us\b|\bemail us\b)", t, re.I):
            continue
        out.append(t)
    return list(dict.fromkeys(out))


def official_contact(rec):
    dom = (rec.get("domain") or "").lower().removeprefix("www.")
    emails = rec.get("emails") or []
    for e in emails:
        addr = (e.get("email") if isinstance(e, dict) else str(e)).lower()
        host = addr.split("@")[-1]
        if dom and (host == dom or host.endswith("." + dom) or dom.endswith("." + host)):
            return "email on own domain"
    if [p for p in rec.get("phones") or [] if p]:
        return "phone on own site"
    return ""


def roles_of(rec):
    r = set()
    for x in rec.get("roles") or []:
        v = (x.get("role") if isinstance(x, dict) else str(x)).lower()
        for k in ROLE_OK:
            if k in v:
                r.add(k)
    if rec.get("role"):
        v = str(rec["role"]).lower()
        r |= {k for k in ROLE_OK if k in v}
    return sorted(r)


def gate(rec, today=None):
    """(refined: bool, failed: [reasons], facts: dict)"""
    today = today or dt.date.today()
    fails = []
    country = str(rec.get("country") or "").upper()
    if not (rec.get("supplier") and ISO3.match(country)):
        fails.append("identity: no name or no ISO country")
    if rec.get("verdict") != "ok":
        fails.append(f"site: {rec.get('verdict') or 'not read'}")
    elif rec.get("name_match") != "high":
        fails.append(f"site: name match {rec.get('name_match') or 'unknown'}")
    roles = roles_of(rec)
    if not roles:
        fails.append("role: not stated on the site")
    prods = product_phrases(rec)
    if len(prods) < 2:
        fails.append("products: fewer than 2 product phrases")
    contact = official_contact(rec)
    if not contact:
        fails.append("contact: no email on own domain and no phone")
    try:
        checked = dt.date.fromisoformat(str(rec.get("checked") or rec.get("checked_at") or "")[:10])
        if (today - checked).days > FRESH_DAYS:
            fails.append("fresh: checked more than 180 days ago")
    except ValueError:
        fails.append("fresh: no check date")
    strong = bool(rec.get("legal_ids"))
    return not fails, fails, {"roles": roles, "products": len(prods), "contact": contact, "strong_identity": strong, "country": country}


def run(d):
    d = Path(d)
    n, ok, strong = 0, 0, 0
    first, every = Counter(), Counter()
    by_country, by_role = Counter(), Counter()
    keys = []
    seen = set()
    with open(d / "site.jsonl", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except ValueError:
                every["unreadable line"] += 1
                continue
            k = rec.get("key")
            if not k or k in seen:
                continue
            seen.add(k); n += 1
            passed, fails, facts = gate(rec)
            for x in fails:
                every[x.split(":")[0]] += 1
            if fails:
                first[fails[0].split(":")[0] + ": " + fails[0].split(": ", 1)[-1][:40]] += 1
                continue
            ok += 1; strong += facts["strong_identity"]
            by_country[facts["country"]] += 1
            for r in facts["roles"]:
                by_role[r] += 1
            keys.append(k)
    (d / "refined.keys").write_text("\n".join(keys), encoding="utf-8")
    out = {"gate": VERSION, "suppliers_checked": n, "refined": ok, "refined_with_legal_id": strong,
           "refined_countries": len(by_country), "refined_by_role": dict(by_role.most_common()),
           "refined_top_countries": dict(by_country.most_common(25)),
           "failing_condition_counts": dict(every.most_common()), "first_failure": dict(first.most_common(25))}
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return out


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "/opt/sinder/enrich")
