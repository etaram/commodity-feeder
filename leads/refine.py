"""Data refinement (טיוב) for the supplier universe: cleans fields, groups duplicates, attaches the official website,
completes products, role and contacts from the company's own site, checks that the evidence belongs to the company,
and records the source and date of every change, the conflicts and the gaps. Code only; the cases code cannot
settle go to a bounded AI review queue (read by the Deal Desk's daily job) and come back as labelled readings.

Never destructive: the raw universe row is untouched; the refined layer is a separate file keyed by supplier|country
(data/checks/refine/refined.jsonl), versioned (REFINE_VERSION), backed up per run (data/checks/refine/history/), and the supplier
build applies it only while REFINE is not "off". A record is re-processed only when its inputs changed (input hash:
the raw fields that matter, its website check's content hash, its AI reading) or its result expired.

Stages per supplier:
  1 clean      e-mails, phones, website (buyer, government, exchange, directory or mail-provider domains rejected with
               the reason), country code, registration id; free-mail boxes kept but marked personal
  2 duplicates union of: same legal id; same normalised name in the same country; same website domain in the same
               country; same company e-mail domain in the same country. Group id + canonical record; nothing deleted
  3 website    the record's own site when the domain matches the name; else a company e-mail domain; else a site the
               website check found and confirmed (the page names the company). Each with its basis and date
  4 complete   from a website check that names the company: description, products, role, certificates, export
               countries, registration ids, e-mails on the company's own domain, phones. Source URL and date per field
  5 belongs    the site's products against the record's contract and shipment evidence; the site's sector against
               the record's; namesakes (same name in other countries) that may own part of the evidence; e-mail domain
               against the website; phone calling code against the country
  6 status     completed fields, contact channel found, conflicts, gaps, needs_ai (with the question for the model)

Outputs: data/checks/refine/refined.jsonl (private, Actions cache), data/checks/refine/check_queue.txt (sites for the website check
to read next), data/leads/refine_progress.json (counts only, public), sheet tabs 'Refine progress' and 'Refine issues'.

  python -m leads.refine [--sample N]
"""
import csv
import gzip
import hashlib
import html
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from .common import DATA, LEADS, PRIVATE, log
from .contacts import CC, clean_email, clean_phone, email_kind

REFINE_VERSION = "refine-4"
DIR = DATA / "checks" / "refine"  # kept with the website checks, in their Actions cache
OUT = DIR / "refined.jsonl.gz"  # about 10x smaller than plain JSON lines; read and written as a stream
HIST = DIR / "history"
CHECKS = DATA / "checks" / "company_checks.jsonl"
VALID_DAYS = 120  # a refined record is re-derived at least this often even if nothing changed

LEGAL = re.compile(r"\b(s\.?a\.?s?|ltda|ltd|limited|llc|inc|gmbh|ag|kg|srl|s\.?r\.?l|spa|s\.?p\.?a|bv|nv|plc|pty|cc|co|corp|"
                   r"corporation|company|sarl|sa de cv|de cv|cia|eirl|sac|oy|ab|as|a/s|kft|zrt|sp z o o|jsc|ojsc|pjsc|ooo|tov|"
                   r"llp|pvt|private|public|the|and|of|et|y|e|group|holding|holdings|international|intl|industries|industrial|"
                   r"trading|enterprises?|services?|solutions?)\b", re.I)
FREE = re.compile(r"@(gmail|yahoo|hotmail|outlook|live|icloud|aol|gmx|mail|yandex|ukr|i\.ua|meta\.ua|bigmir|web\.de|orange|free|"
                  r"laposte|wanadoo|libero|terra|uol|bol|ig|rediffmail|qq|163|126|sina|naver|hanmail|proton|zoho|seznam|wp\.pl|o2|"
                  r"interia|abv|btinternet|sky|comcast|verizon|att|sbcglobal|prodigy|telkomsa|mweb|iafrica|vodamail)\.", re.I)
BAD_SITE = [
    ("government or public body", re.compile(r"(\.gov(\.[a-z]{2})?$|\.gob\.|\.gouv\.|\.go\.[a-z]{2}$|\.mil(\.[a-z]{2})?$|europa\.eu$|\.int$|un\.org$)")),
    ("stock exchange or market data", re.compile(r"(euronext|bolsa|nasdaq|nyse|londonstockexchange|spglobal|marketscreener|bloomberg|reuters|"
                                                  r"investing\.com|morningstar|tradingview|finance\.yahoo|wsj\.com)")),
    ("directory or social profile", re.compile(r"(linkedin|facebook|instagram|twitter|x\.com|youtube|wikipedia|wikidata|kompass|dnb\.com|"
                                               r"zoominfo|crunchbase|opencorporates|yellowpages|europages|alibaba|made-in-china|indiamart|"
                                               r"tradeindia|glassdoor|indeed|bizapedia|companieshouse|northdata)")),
    ("mail or certified-mail provider", re.compile(r"(pec\.it|legalmail|arubapec|postacert|gmail|outlook|yahoo|hotmail)")),
    ("hosting placeholder", re.compile(r"(wixsite\.com|blogspot\.|wordpress\.com|weebly\.com|godaddysites|business\.site|sites\.google)")),
]
ISO3 = None


def iso3_set():
    global ISO3
    if ISO3 is None:
        try:
            ISO3 = set(json.loads((DATA.parent / "dealdesk" / "lib" / "countrynames.json").read_text(encoding="utf-8")))
        except (OSError, ValueError):
            ISO3 = set()
    return ISO3


def norm_name(n):
    n = re.sub(r"[^\w ]", " ", html.unescape(html.unescape(n or "")).replace("&", " and ").lower())
    n = LEGAL.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip()[:80]


def host_of(url):
    h = re.sub(r"^https?://", "", (url or "").strip().lower()).split("/")[0].split(":")[0]
    return h[4:] if h.startswith("www.") else h


def root_of(h):
    p = h.split(".")
    return ".".join(p[-3:]) if len(p) >= 3 and re.match(r"^(co|com|org|net|gov|ac|edu)$", p[-2]) and len(p[-1]) == 2 else ".".join(p[-2:])


def site_rejection(url, name):
    """Why a website is certainly not the company's own site (government, exchange, directory, mail or hosting
    domains), or ''. A domain that does not carry the name is not rejected: acronyms and group domains are common
    (edm.co.mz is Electricidade de Mocambique), so such a site stays a candidate for the website check to confirm."""
    h = host_of(url)
    if not h or "." not in h:
        return "not a web address"
    for why, rx in BAD_SITE:
        # an exchange's or a directory's own site is that company's site (Euronext on euronext.com)
        if rx.search(h) and not (why in ("stock exchange or market data", "directory or social profile") and name_in_domain(name, h)
                                 and not re.search(r"linkedin|facebook|instagram|twitter|youtube|wikipedia", h)):
            return why
    return ""


def name_in_domain(name, host):
    label = re.sub(r"[^a-z0-9]", "", ".".join(host.split(".")[:-1]) or host)
    words = [w for w in re.split(r"[^a-z0-9]+", norm_name(name)) if len(w) >= 3]
    if not words or not label:
        return False
    if any((len(w) >= 4 and (w in label or w[:4] in label)) or (len(w) == 3 and label.startswith(w)) for w in words):
        return True
    # acronyms: from every word, and from the words without the short connectors (de, of, la, und ...)
    import unicodedata
    folded = "".join(c for c in unicodedata.normalize("NFKD", (name or "").lower()) if not unicodedata.combining(c))
    folded = re.sub(r"\b(ltd|limited|llc|inc|gmbh|sa|s\.a|sas|srl|spa|bv|nv|plc|pty|pvt|corp|co|cia|sac|ag|kg|oy|ab|as)\b\.?", " ", folded)
    allw = re.split(r"[^a-z0-9]+", folded)
    for ini in ("".join(w[0] for w in allw if w), "".join(w[0] for w in allw if len(w) > 2)):
        if len(ini) >= 2 and label.startswith(ini):
            return True
    return False


def core_label(h):
    """The brand label of a domain: baxter.com.pl and baxter.com are both 'baxter'."""
    r = root_of(h or "")
    return r.split(".")[0] if r else ""


def sha(*parts):
    return hashlib.sha1("\x1f".join(str(p) for p in parts).encode("utf-8", "ignore")).hexdigest()[:16]


# ---------------------------------------------------------------- stage 2: duplicates
class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def duplicate_groups(rows):
    """{key: (group_id, canonical_key, reasons)} for rows that share an identity signal with another row."""
    uf, why = UF(), defaultdict(set)
    idx = defaultdict(list)
    for r in rows:
        k = r["_key"]
        uf.find(k)
        if r.get("legal_id"):
            idx[("legal id", re.sub(r"\W", "", r["legal_id"]).upper())].append(k)
        nn = norm_name(r["supplier"]).replace(" ", "")  # "A.B.C. Ltd" and "ABC Limited" are one name
        if len(nn) >= 4:
            idx[("same name, same country", nn, r["country"])].append(k)
        # a website or an e-mail domain is an identity signal only when it carries the company's name: tender
        # records often hold a distributor's, a tender portal's or a group's domain (Baxter and Sarstedt shared one)
        h = host_of(r.get("website", ""))
        if h and not site_rejection(r.get("website", ""), r["supplier"]) and name_in_domain(r["supplier"], h):
            idx[("same website", root_of(h), r["country"])].append(k)
        e = (r.get("email") or "").split(";")[0].strip().lower()
        if "@" in e and not FREE.search(e) and name_in_domain(r["supplier"], e.split("@")[1]):
            idx[("same e-mail domain", root_of(e.split("@")[1]), r["country"])].append(k)
    for sig, ks in idx.items():
        if 1 < len(ks) <= 25:  # a signal shared by dozens is a portal or a parent group, not one company
            for k in ks[1:]:
                uf.union(ks[0], k)
            for k in ks:
                why[k].add(sig[0])
    groups = defaultdict(list)
    for r in rows:
        groups[uf.find(r["_key"])].append(r)
    out = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        canon = max(members, key=lambda r: (r.get("tier") in ("1", "2"), int(r.get("quality") or 0), int(r.get("wins") or 0)))
        gid = "dg-" + sha(*sorted(m["_key"] for m in members))[:10]
        for m in members:
            out[m["_key"]] = (gid, canon["_key"], sorted(why[m["_key"]]), len(members))
    return out


# ---------------------------------------------------------------- stages 1, 3-6 for one record
def refine_one(r, check, ai, dup, namesakes, today):
    key, name, cty = r["_key"], r["supplier"], r["country"]
    now = today.isoformat()
    filled, conflicts, gaps, cleaned = {}, [], [], {}

    def fill(field, value, source, basis):
        if value:
            filled[field] = {"value": value, "source": source, "basis": basis, "date": now}

    # 1 clean
    if cty and iso3_set() and cty not in iso3_set() and cty not in ("XKX", "EUR", "INT"):  # Kosovo; EU and international bodies
        cleaned["country"] = {"from": cty, "to": "", "reason": "not an ISO 3166 country code"}
    em_raw = r.get("email") or ""
    em = clean_email(em_raw)
    if em_raw and em != em_raw:
        cleaned["email"] = {"from": em_raw[:120], "to": em, "reason": "invalid or placeholder addresses removed"}
    personal = [e for e in em.split("; ") if e and FREE.search(e)]
    ph_raw = r.get("phone") or ""
    ph = clean_phone(ph_raw, cty)
    if ph_raw and ph != ph_raw:
        cleaned["phone"] = {"from": ph_raw[:80], "to": ph, "reason": "normalised to +code number; invalid parts removed"}
    site, site_basis, candidate = "", "", ""
    if r.get("website"):
        bad = site_rejection(r["website"], name)
        if bad:
            cleaned["website"] = {"from": r["website"][:160], "to": "", "reason": bad}
        elif name_in_domain(name, host_of(r["website"])):
            site, site_basis = "https://" + host_of(r["website"]) + "/", f"record ({r.get('website_source') or 'notice or registry'}), domain carries the name"
        else:
            candidate = "https://" + host_of(r["website"]) + "/"  # confirmed only if the page names the company

    # 3 website: e-mail domain, then a checked site that names the company
    if not site:
        for e in em.split("; "):
            if "@" in e and not FREE.search(e):
                d = e.split("@")[1]
                if name_in_domain(name, d) and not site_rejection("https://" + d, name):
                    site, site_basis = f"https://{d}/", "company e-mail domain carries the name"
                    break
    ck_ok = check and check.get("verdict") == "ok" and check.get("name_match") in ("high", "partial")
    if check:
        if ck_ok:
            cs = check.get("website") or ""
            if not site or root_of(host_of(cs)) == root_of(host_of(site)):
                site, site_basis = "https://" + host_of(cs) + "/", f"the site names the company ({check.get('name_match')} match), read {check.get('checked')}"
            elif root_of(host_of(cs)) != root_of(host_of(site)):
                conflicts.append(f"record site {host_of(site)} and checked site {host_of(cs)} differ")
        elif check.get("verdict") == "name mismatch":
            conflicts.append(f"the site {host_of(check.get('website', ''))} does not name the company")
            if site and root_of(host_of(site)) == root_of(host_of(check.get("website", ""))):
                cleaned["website"] = {"from": site, "to": "", "reason": "the site does not name the company (checked)"}
                site, site_basis = "", ""
        elif check.get("verdict") in ("unreachable", "parked or placeholder page", "blocked by bot protection"):
            gaps.append(f"website {check.get('verdict')}")
        elif check.get("verdict") == "no website found":
            gaps.append("no official website found (likely domains tried)")
    if site:
        fill("website", site, site, site_basis)
    elif candidate and not check:
        gaps.append("website on record not confirmed yet (domain does not carry the name; queued for the website check)")

    # 4 complete from the company's own site (only when the page names the company)
    if ck_ok:
        src = check.get("website", "")
        fill("description", (check.get("description") or "")[:400], src, "company website (its own words)")
        if check.get("products"):
            fill("products", "; ".join(check["products"][:15])[:500], src, "company website: product headings and menus")
        if check.get("roles"):
            fill("role", "; ".join(x["role"] for x in check["roles"]), src, "company website: " + "; ".join(x["phrase"] for x in check["roles"])[:160])
        if check.get("certificates"):
            fill("certificates", "; ".join(check["certificates"]), src, "named on the company website (a claim, not a certificate check)")
        if check.get("export_countries"):
            fill("export_countries", " ".join(check["export_countries"]), src, f"company website: '{check.get('export_wording', '')}'")
        if check.get("legal_ids"):
            fill("legal_ids", "; ".join(f"{x['kind']} {x['value']}" for x in check["legal_ids"]), src, "printed on the company website")
        own = [x["email"] for x in check.get("emails", [])]
        if own:
            fill("emails_own_domain", "; ".join(own[:3]), src, "on the company's own domain: " + ", ".join(x["kind"] for x in check["emails"][:3]))
        if check.get("phones"):
            fill("phones_site", "; ".join(check["phones"][:2]), src, "on the company website")
    if ai:
        for f_ in ("sector", "role"):
            if ai.get(f_):
                fill("ai_" + f_, ai[f_], ai.get("source", ""), f"model reading of the company's own site, {ai.get('date', '')} (not verified)")
        if ai.get("belongs") == "no":
            conflicts.append("model reading: the site is not this company's")

    # 5 does the evidence belong to the company?
    if ck_ok and check.get("sector_conflict"):
        conflicts.append(f"site says {check.get('sector')}, record says {check.get('record_sector')}")
    if ck_ok and check.get("products") and (r.get("supplied") or r.get("hs_names")):
        site_words = {w for p in check["products"] for w in re.findall(r"[a-z]{4,}", p.lower())}
        rec_words = set(re.findall(r"[a-z]{4,}", f"{r.get('supplied', '')} {r.get('hs_names', '')} {r.get('commodities', '')}".lower()))
        if site_words and rec_words and not (site_words & rec_words):
            conflicts.append("the site's products share no word with the contracts or shipments on record")
    if namesakes.get(norm_name(name), 0) > 1 and (r.get("shipments_12m") or r.get("hs_codes")):
        conflicts.append(f"the same name exists in {namesakes[norm_name(name)]} countries; shipment evidence matched by name may belong to a namesake")
    # soft checks: worth a look, not a contradiction (a group's .com mailbox for its .pl site, a head-office number)
    notes = []
    best_mail = (filled.get("emails_own_domain") or {}).get("value") or em
    if best_mail and site and "@" in best_mail:
        md = best_mail.split(";")[0].strip().split("@")[1]
        if core_label(md) != core_label(host_of(site)) and not name_in_domain(name, md):
            notes.append("e-mail domain is not the company's (neither the website's nor carrying its name)")
    if ph and cty in CC and ph.startswith("+") and not ph.replace(" ", "").startswith("+" + CC[cty]):
        notes.append(f"phone is not a {cty} number (+{CC[cty]}): head office or a reseller")

    # 6 status
    contact = bool((filled.get("emails_own_domain") or {}).get("value") or (em and not personal) or ph or (filled.get("phones_site") or {}).get("value"))
    if not site:
        gaps.append("no official website")
    if not contact:
        gaps.append("no contact channel" if not personal else "only a personal mailbox")
    if not (r.get("products") or filled.get("products") or filled.get("description")):
        gaps.append("no product description from the company")
    if not (filled.get("role") or r.get("type") in ("goods supplier", "trader") or r.get("trader") == "yes" or r.get("epc")):
        gaps.append("role not established")
    needs_ai = ""
    if ck_ok and not ai:
        if not check.get("sector") and (check.get("products") or check.get("description")):
            needs_ai = "sector: the site has product text but code found no clear sector"
        elif check.get("sector_conflict"):
            needs_ai = "sector: the site and the record disagree"
    elif check and check.get("name_match") == "partial" and not ai:
        needs_ai = "identity: the site names the company only partly"
    out = {"key": key, "supplier": name, "country": cty, "version": REFINE_VERSION, "refined": now,
           "cleaned": cleaned, "filled": filled, "conflicts": conflicts, "notes": notes, "gaps": gaps, "contact_found": contact,
           "personal_mailbox": bool(personal), "needs_ai": needs_ai}
    if dup:
        out["duplicate"] = {"group": dup[0], "canonical": dup[1], "signals": dup[2], "size": dup[3]}
    return out


def load_jsonl(p):
    out = {}
    if p.exists():
        txt = gzip.open(p, "rt", encoding="utf-8").read() if str(p).endswith(".gz") else p.read_text(encoding="utf-8")
        for line in txt.splitlines():
            try:
                d = json.loads(line); out[d["key"]] = d
            except (ValueError, KeyError):
                pass
    return out


def load_ai():
    """Model readings written back by the Deal Desk ('Refine AI' tab: key, date, sector, role, belongs, source, note)."""
    try:
        from .push import UNIVERSE_SHEET, Sheets
        rows = Sheets().values(UNIVERSE_SHEET, "'Refine AI'!A2:G50000")
    except (Exception, SystemExit) as e:  # noqa: BLE001
        log.info("refine: no AI readings (%s)", str(e)[:80])
        return {}
    out = {}
    for r in rows:
        r = r + [""] * 7
        if r[0]:
            out[r[0]] = {"date": r[1], "sector": r[2], "role": r[3], "belongs": r[4], "source": r[5], "note": r[6]}
    return out


def main(sample=0):
    src = PRIVATE / "universe.csv"
    if not src.exists():
        log.info("refine: no universe yet"); return {}
    DIR.mkdir(parents=True, exist_ok=True); HIST.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(open(src, encoding="utf-8")))
    for r in rows:
        r["_key"] = f"{r['supplier']}|{r['country']}"
    if sample:
        # a sample across tiers and sectors, deterministic: every n-th row
        step = max(1, len(rows) // sample)
        rows_s = rows[::step][:sample]
    else:
        rows_s = rows
    today = date.today()
    checks, ai, prev = load_jsonl(CHECKS), load_ai(), load_jsonl(OUT)
    namesakes = Counter()
    seen_nc = set()
    for r in rows:
        nn = norm_name(r["supplier"])
        if len(nn) >= 5 and (nn, r["country"]) not in seen_nc:
            seen_nc.add((nn, r["country"])); namesakes[nn] += 1
    dups = duplicate_groups(rows)  # always over the whole universe: a sample must see every duplicate partner
    stale = (today - timedelta(days=VALID_DAYS)).isoformat()
    out, stats, reused = dict(prev), Counter(), 0
    queue = []
    for r in rows_s:
        k = r["_key"]
        ck, a, dp = checks.get(k), ai.get(k), dups.get(k)
        h = sha(REFINE_VERSION, r.get("website"), r.get("email"), r.get("phone"), r.get("legal_id"), r.get("products"), r.get("supplied"),
                r.get("main_sector"), r.get("hs_codes"), (ck or {}).get("content_hash"), (ck or {}).get("verdict"), json.dumps(a or {}, sort_keys=True), json.dumps(dp or []))
        p = prev.get(k)
        if p and p.get("input_hash") == h and p.get("refined", "") >= stale:
            reused += 1
            res = p
        else:
            res = refine_one(r, ck, a, dp, namesakes, today)
            res["input_hash"] = h
            out[k] = res
        stats["processed"] += 1
        stats["completed"] += bool(res["filled"])
        stats["contact_found"] += res["contact_found"]
        stats["website"] += "website" in res["filled"]
        stats["with_conflicts"] += bool(res["conflicts"])
        stats["with_notes"] += bool(res.get("notes"))
        stats["with_gaps"] += bool(res["gaps"])
        stats["cleaned"] += bool(res["cleaned"])
        stats["duplicates"] += "duplicate" in res
        stats["needs_ai"] += bool(res["needs_ai"])
        for g in res["gaps"]:
            stats["gap: " + g.split(" (")[0]] += 1
        for c in res["conflicts"]:
            stats["conflict: " + re.sub(r"\d+|[a-z0-9.-]+\.[a-z]{2,}", "#", c)[:60]] += 1
        for c in res.get("notes", []):
            stats["note: " + re.sub(r"\b[A-Z]{3}\b|\+\d+|\d+", "#", c)[:60]] += 1
        # the website check reads next: a site on record not checked yet, or proven suppliers with no site at all
        if not ck and (r.get("website") or r.get("tier") in ("1", "2")):
            queue.append((0 if r.get("tier") in ("1", "2") else 1, -int(r.get("quality") or 0), k))
    # backup the previous refined layer, then write the new one (one line per record)
    # backup of the previous layer once a day (the job runs hourly); the last 7 days are kept (rollback = copy one back)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    if OUT.exists() and not list(HIST.glob(f"refined-{stamp}*.jsonl.gz")):
        shutil.copyfile(OUT, HIST / f"refined-{stamp}T{datetime.now(timezone.utc).strftime('%H%M')}.jsonl.gz")
        for old in sorted(HIST.glob("refined-*.jsonl.gz"))[:-7]:
            old.unlink()
    with gzip.open(OUT, "wt", encoding="utf-8", compresslevel=6) as fo:
        for v in out.values():
            fo.write(json.dumps(v, ensure_ascii=False) + "\n")
    queue.sort()
    (DIR / "check_queue.txt").write_text("\n".join(k for _, _, k in queue[:20000]), encoding="utf-8")
    total = len(rows)
    prog = {"version": REFINE_VERSION, "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "universe": total, "sample": sample or None,
            "processed": stats["processed"], "reused_unchanged": reused, "completed": stats["completed"], "contact_found": stats["contact_found"],
            "official_website": stats["website"], "with_conflicts": stats["with_conflicts"], "with_notes": stats["with_notes"], "with_gaps": stats["with_gaps"], "cleaned": stats["cleaned"],
            "in_duplicate_groups": stats["duplicates"], "duplicate_groups": len({v[0] for v in dups.values()}), "needs_ai": stats["needs_ai"],
            "websites_checked": len(checks), "website_check_queue": len(queue),
            "gaps": {k[5:]: v for k, v in stats.most_common() if k.startswith("gap: ")},
            "conflicts": {k[10:]: v for k, v in stats.most_common(40) if k.startswith("conflict: ")},
            "notes": {k[6:]: v for k, v in stats.most_common(40) if k.startswith("note: ")}}
    (LEADS / "refine_progress.json").write_text(json.dumps(prog, ensure_ascii=False, indent=1), encoding="utf-8")
    push_sheet(out, prog)
    log.info("refine: %s", json.dumps({k: v for k, v in prog.items() if k not in ("gaps", "conflicts")}))
    return prog


def push_sheet(out, prog):
    try:
        from .push import UNIVERSE_SHEET, Sheets
        sh = Sheets()
    except (Exception, SystemExit) as e:  # noqa: BLE001
        log.info("refine: sheet not written (%s)", str(e)[:80]); return
    rows = [["metric", "value"]] + [[k, json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v] for k, v in prog.items()]
    sh.replace_tab(UNIVERSE_SHEET, "Refine progress", rows, raw=True)
    # issues: conflicts first, then the AI queue, then gaps on proven suppliers; plus the AI review queue for the Deal Desk
    issues = [["key", "supplier", "country", "conflicts", "gaps", "needs_ai", "website", "duplicate_group", "refined"]]
    pick = sorted(out.values(), key=lambda v: (not v["conflicts"], not v["needs_ai"], len(v["gaps"]) == 0))
    for v in pick[:20000]:
        if not (v["conflicts"] or v["needs_ai"] or v["gaps"]):
            continue
        issues.append([v["key"], v["supplier"], v["country"], "; ".join(v["conflicts"]), "; ".join(v["gaps"]), v["needs_ai"],
                       (v["filled"].get("website") or {}).get("value", ""), (v.get("duplicate") or {}).get("group", ""), v["refined"]])
    sh.replace_tab(UNIVERSE_SHEET, "Refine issues", issues, raw=True)
    checks = load_jsonl(CHECKS)
    q = [["key", "question", "supplier", "country", "website", "description", "products", "record_sector", "site_sector", "record_evidence"]]
    for v in out.values():
        if v["needs_ai"] and len(q) <= 2000:
            ck = checks.get(v["key"]) or {}
            q.append([v["key"], v["needs_ai"], v["supplier"], v["country"], ck.get("website", ""), (ck.get("description") or "")[:400],
                      "; ".join((ck.get("products") or [])[:15])[:500], ck.get("record_sector", ""), ck.get("sector", ""), ""])
    sh.replace_tab(UNIVERSE_SHEET, "Refine AI queue", q, raw=True)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    a = sys.argv[1:]
    print(json.dumps(main(int(a[a.index("--sample") + 1]) if "--sample" in a else 0), ensure_ascii=False, indent=1)[:3000])
