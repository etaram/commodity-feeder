"""Refinement of every module beyond suppliers: tenders, buyers (and accounts), projects, logistics, financing and
importers. Same principles as leads/refine.py:

  1. clean wrong fields and find duplicates, never deleting an original (duplicates point to a canonical record)
  2. check every official link (notice, project page, institution page) and the official website where there is one
  3. complete from official sources only (the notice's own contact, the buyer's own domain, GLEIF), with source and date
  4. check that the evidence belongs to the record (the page names it, the register record has the same name and country)
  5. mark conflicts and gaps; nothing is marked verified without a record behind it
  6. publish a compact overlay (duplicates, closed notices, dead links, fills) that the search index applies

Code does the work; a record that did not change and is still valid is reused. Network work (link checks, site reads,
register lookups) has a per-run budget and its own cache, so the whole store is covered over successive runs.
Nothing here contacts anyone: links are read, never submitted.

Outputs
  data/checks/refine/modules/<module>.jsonl.gz      full refined layer (Actions cache, with daily backups in history/)
  data/leads/refined/<module>.csv                   overlay of records with a fix, a duplicate or a conflict (public data only)
  data/leads/refine_progress.json  "modules"        real counts per module
Rollback: REFINE_MODULES=off makes the index ignore the overlay; a backup in history/ can be copied back.
Run: python -m leads.refine_modules [--sample N] [--links 2500] [--sites 200] [--registers 5]"""
import csv
import gzip
import html
import json
import re
import shutil
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from .common import DATA, LEADS, log
from .contacts import clean_email, clean_phone, email_kind
from .refine import FREE, iso3_set, norm_name, sha

VERSION = "modules-1"
VALID_DAYS = 120
DIR = DATA / "checks" / "refine" / "modules"
HIST = DIR / "history"
PUB = LEADS / "refined"
LINKS = DIR / "links.json"
SITES = DIR / "sites.jsonl"
REGS = DIR / "registers.jsonl"
LINK_DAYS, SITE_DAYS, REG_DAYS = 30, 90, 180
EMAIL = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,24}")
PHONE = re.compile(r"(?:\+|00)\d[\d\s().-]{7,18}\d")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
GOV = re.compile(r"(\.gov(\.[a-z]{2})?$|\.gob\.|\.gouv\.|\.go\.[a-z]{2}$|\.gv\.|\.govt\.|\.mil(\.[a-z]{2})?$|\.int$|\.edu(\.[a-z]{2})?$|"
                 r"\.ac\.[a-z]{2}$|\.nhs\.|\.(admin|bund)\.[a-z]{2}$|\.[a-z]{2}\.gov|europa\.eu$|un\.org$)", re.I)
FIN_CATS = {"ECA", "DFI", "multilateral", "insurer", "bank", "fund", "grant"}
LOG_CATS = {"forwarder", "inspection", "customs", "ocean_carrier", "air_cargo", "insurance", "breakbulk", "port_terminal", "platform"}
DEFENCE = {"yes", "no", "case by case", "not stated"}


# ---------------------------------------------------------------- small pure helpers
def clean_text(v):
    return re.sub(r"\s+", " ", html.unescape(html.unescape(str(v or "")))).strip()


def host(u):
    h = re.sub(r"^https?://", "", (u or "").strip().lower()).split("/")[0].split(":")[0]
    return h[4:] if h.startswith("www.") else h


def root(h):
    p = h.split(".")
    return ".".join(p[-3:]) if len(p) >= 3 and len(p[-1]) == 2 and p[-2] in ("co", "com", "gov", "go", "gob", "org", "ac", "or", "net", "edu", "nhs", "gv") else ".".join(p[-2:])


def iso_date(v):
    v = (v or "").strip()
    if DATE.match(v):
        return v[:10]
    m = re.match(r"^(\d{1,2})[./-](\d{1,2})[./-](\d{4})", v)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        if mo <= 12 and d <= 31:
            return f"{y}-{mo:02d}-{d:02d}"
    return ""


def num(v):
    try:
        x = float(str(v).replace(",", ""))
        return x if x == x else None
    except (TypeError, ValueError):
        return None


ISO2TO3 = {}


def to_iso3(c):
    c = (c or "").strip().upper()
    if len(c) == 3:
        return c
    if len(c) == 2:
        if not ISO2TO3:
            try:
                import pycountry
                for x in pycountry.countries:
                    ISO2TO3[x.alpha_2] = x.alpha_3
            except Exception:  # noqa: BLE001
                pass
            ISO2TO3.update({"UK": "GBR", "XK": "XKX", "EL": "GRC"})
        return ISO2TO3.get(c, "")
    return ""


NAME2ISO3 = {}
REGIONAL = re.compile(r"\s-\s|\b(multi\w*|regional|world|africa|asia|europe|america|caribbean|pacific|islands countries|oecs|countries|middle east|"
                      r"sahel|balkans|mekong|caucasus|-)\b", re.I)


def name_to_iso3(n):
    """Country name as development banks write it ('Congo, Democratic Republic of', 'Lao PDR') -> ISO3, or ''."""
    if not NAME2ISO3:
        try:
            for k, names in json.loads((DATA.parent / "dealdesk" / "lib" / "countrynames.json").read_text(encoding="utf-8")).items():
                for x in names:
                    NAME2ISO3[re.sub(r"[^a-z]", "", x.lower())] = k
        except (OSError, ValueError):
            pass
        NAME2ISO3.update({"congodemocraticrepublicof": "COD", "congorepublicof": "COG", "laopdr": "LAO", "somaliafederalrepublicof": "SOM",
                          "yemenrepublicof": "YEM", "egyptarabrepublicof": "EGY", "iranislamicrepublicof": "IRN", "gambiathe": "GMB",
                          "turkiye": "TUR", "kyrgyzrepublic": "KGZ", "slovakrepublic": "SVK", "westbankandgaza": "PSE", "cotedivoire": "CIV",
                          "micronesiafederatedstatesof": "FSM", "venezuelarepublicabolivarianade": "VEN", "koreademocraticpeoplesrepublicof": "PRK",
                          "bahamasthe": "BHS", "korearepublicof": "KOR", "russianfederation": "RUS", "syrianarabrepublic": "SYR"})
    return NAME2ISO3.get(re.sub(r"[^a-z]", "", (n or "").lower()), "")


def country_fix(c, cleaned):
    """ISO 3166 alpha-3, converting alpha-2; records the change."""
    if not c:
        return ""
    c3 = to_iso3(c)
    ok = iso3_set()
    if c3 and (not ok or c3 in ok or c3 in ("XKX", "EUR", "INT")):
        if c3 != c:
            cleaned["country"] = {"from": c, "to": c3, "reason": "converted to a 3-letter ISO code"}
        return c3
    by_name = name_to_iso3(c)
    if by_name:
        cleaned["country"] = {"from": c, "to": by_name, "reason": "country name converted to a 3-letter ISO code"}
        return by_name
    if REGIONAL.search(c):
        return ""  # a region or several countries: a valid value for a regional project, nothing to fix
    cleaned["country"] = {"from": c, "to": "", "reason": "not an ISO 3166 country code or a country name"}
    return ""


def url_ok(u):
    return bool(re.match(r"^https?://[^\s/]+\.[a-z]{2,}", (u or "").strip(), re.I))


def emails_in(text):
    out = []
    for e in EMAIL.findall(text or ""):
        e = clean_email(e.strip(".'").lower())
        if e and e not in out:
            out.append(e)
    return out


class Groups:
    """Union-find over record keys: duplicates point at one canonical key, nothing is removed."""

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


def dup_groups(rows, keyf, sigs, best):
    """rows -> {key: (canonical, size, signal)} for groups of 2+. sigs(row) -> list of (signal name, value)."""
    g, by, why = Groups(), defaultdict(list), {}
    for r in rows:
        for name, v in sigs(r):
            if v:
                by[(name, v)].append(keyf(r))
    for (name, _), ks in by.items():
        if 1 < len(ks) <= 25:  # a value shared by many records is a placeholder, not an identity
            for k in ks[1:]:
                g.union(ks[0], k); why[k] = name; why[ks[0]] = why.get(ks[0], name)
    members = defaultdict(list)
    rk = {keyf(r): r for r in rows}
    for k in rk:
        members[g.find(k)].append(k)
    out = {}
    for ks in members.values():
        if len(ks) > 1:
            canon = max(ks, key=lambda k: best(rk[k]))
            for k in ks:
                out[k] = (canon, len(ks), why.get(k, ""))
    return out


def tender_dups(tenders):
    """{id: (canonical id, group size, signal)} for the same notice listed twice (by two sources, or twice by one).
    Same link with the same title, deadline and value; or the same title, buyer, country, deadline and value."""
    title = lambda r: norm_name(r.get("title_en") or r.get("title", ""))  # noqa: E731
    val = lambda r: round(num(r.get("est_value_usd")) or 0)  # noqa: E731
    return dup_groups(
        tenders, lambda r: r["id"],
        lambda r: [("same notice link and title", ((r.get("link") or "").split("#")[0].rstrip("/").lower(), title(r), iso_date(r.get("deadline", "")), val(r))
                    if url_ok(r.get("link")) and title(r) else ""),
                   ("same title, buyer and deadline", (title(r), norm_name(r.get("buyer", ""))[:60], r.get("country", ""), iso_date(r.get("deadline", "")), val(r))
                    if title(r) and r.get("deadline") else "")],
        lambda r: (r.get("stage") == "tender", bool(r.get("est_value_usd")), bool(r.get("contact")), -int(re.sub(r"\D", "", str(r.get("first_seen", "")))[:8] or 0)))


def link_verdict(info):
    """Conflict text for a checked link, or '' (pure). info: {"status": int|str, "checked": date}."""
    st = (info or {}).get("status")
    if st in (404, 410):
        return f"official link returns {st} (checked {info.get('checked')})"
    if st == "dns":
        return f"official link's host does not exist (checked {info.get('checked')})"
    return ""


def base(key, module, today):
    return {"key": key, "module": module, "version": VERSION, "refined": today.isoformat(), "cleaned": {}, "filled": {}, "conflicts": [],
            "notes": [], "gaps": [], "status": "", "contact_found": False}


def fill(out, field, value, source, basis, today):
    if value:
        out["filled"][field] = {"value": value, "source": source, "basis": basis, "date": today.isoformat()}


# ---------------------------------------------------------------- module rules (pure: caches are passed in)
def refine_tender(r, today, links, buyer_fill):
    out = base(r["id"], "tenders", today)
    c = out["cleaned"]
    country_fix(r.get("country", ""), c)
    dl = iso_date(r.get("deadline", ""))
    if r.get("deadline") and dl != r["deadline"][:10]:
        c["deadline"] = {"from": r["deadline"], "to": dl, "reason": "date normalised to YYYY-MM-DD" if dl else "not a date"}
    pub = iso_date(r.get("published", ""))
    from .validate import date_ok
    for v_, role in ((dl, "deadline"), (pub, "published")):
        if v_:
            ok, why = date_ok(v_, role, today)
            if not ok:
                out["conflicts"].append(why)
    v = num(r.get("est_value_usd"))
    if v is not None and (v < 0 or v > 5e10):
        c["est_value_usd"] = {"from": r["est_value_usd"], "to": "", "reason": "value outside any plausible tender (negative or above $50bn)"}
    if r.get("link") and not url_ok(r["link"]):
        c["link"] = {"from": r["link"][:160], "to": "", "reason": "not a web address"}
    # status: a notice past its deadline is not open, whatever the source says
    if dl and dl < today.isoformat() and r.get("stage") == "tender":
        out["status"] = "closed (deadline passed)"
    if dl and pub and pub > dl:
        out["conflicts"].append(f"published {pub} after its deadline {dl}")
    lk = links.get(r.get("link", ""))
    if lk:
        bad = link_verdict(lk)
        if bad:
            out["conflicts"].append(bad)
        elif lk.get("status") == 200:
            fill(out, "link_checked", "reachable", r["link"], f"the notice page answered, {lk.get('checked')}", today)
    # contact: from the notice itself first, then the buyer's own record
    ems, phs = emails_in(r.get("contact", "")), [p.strip() for p in PHONE.findall(r.get("contact", ""))]
    if ems:
        fill(out, "contact_email", "; ".join(ems[:2]), r.get("link", ""), "contact printed in the notice", today)
    ph_ok = clean_phone("; ".join(phs[:3]), r.get("country", ""))  # only numbers that fit the country's numbering plan
    if ph_ok:
        fill(out, "contact_phone", ph_ok, r.get("link", ""), "contact printed in the notice, checked against the numbering plan", today)
    elif phs:
        out["notes"].append("the notice's phone number does not fit the numbering plan (left out)")
    if not ems and buyer_fill.get("email"):
        fill(out, "contact_email", buyer_fill["email"]["value"], buyer_fill["email"]["source"], "the buyer's own address from its other notices", today)
    out["contact_found"] = bool(out["filled"].get("contact_email") or out["filled"].get("contact_phone"))
    gaps = out["gaps"]
    if not dl and r.get("stage") == "tender":
        gaps.append("no deadline")
    if v is None or v <= 0:
        gaps.append("no estimated value")
    if not out["contact_found"]:
        gaps.append("no contact in the notice")
    if not (r.get("title_en") or "").strip():
        gaps.append("no English title")
    if not r.get("sector"):
        gaps.append("no sector")
    if not r.get("link"):
        gaps.append("no link to the official notice")
    return out


def refine_buyer(r, key, today, tender_contacts, site, reg):
    out = base(key, "buyers", today)
    c = out["cleaned"]
    name = r.get("buyer") or r.get("account") or ""
    nc = clean_text(name)
    if nc != name:
        c["name"] = {"from": name[:150], "to": nc[:150], "reason": "HTML entities and spacing cleaned"}
    cty = country_fix(r.get("country", ""), c)
    raw = r.get("buyer_email") or r.get("contact") or ""
    ems = emails_in(raw)
    personal = [e for e in ems if FREE.search(e)]
    own = [e for e in ems if not FREE.search(e)]
    if ems:
        kind, _ = email_kind("; ".join(own or ems))
        fill(out, "email", "; ".join((own or ems)[:2]), r.get("last_notice") or r.get("latest_notice") or "", f"procurement notice contact ({kind or 'mailbox'})", today)
    elif tender_contacts:
        e, src = tender_contacts[0]
        fill(out, "email", e, src, "contact printed in one of its notices", today)
    phs = [p.strip() for p in PHONE.findall(r.get("contact", ""))]
    ph_ok = clean_phone("; ".join(phs[:3]), cty)
    if ph_ok:
        fill(out, "phone", ph_ok, r.get("latest_notice", ""), "contact printed in its notices, checked against the numbering plan", today)
    # website: the domain of its own (non-free) mailbox; a public body's domain is its official site
    mail = (out["filled"].get("email") or {}).get("value", "").split(";")[0].strip()
    if "@" in mail and not FREE.search(mail):
        d = mail.split("@")[1]
        fill(out, "website", f"https://{d}/", mail, "domain of its own procurement mailbox" + (" (public body domain)" if GOV.search(d) else ""), today)
    if site:
        if site.get("verdict") == "ok" and site.get("name_match") in ("high", "partial"):
            fill(out, "website_confirmed", site.get("website", ""), site.get("website", ""), f"the site names the buyer ({site.get('name_match')}), read {site.get('checked')}", today)
            if site.get("linkedin"):
                fill(out, "linkedin", site["linkedin"], site.get("website", ""), "linked from its own site", today)
        elif site.get("verdict") not in ("ok", "", None):
            out["gaps"].append(f"website {site.get('verdict')}")
    if reg:
        apply_register(out, reg, today)
    if personal and not own:
        out["notes"].append("only a personal mailbox on record")
    out["contact_found"] = bool(out["filled"].get("email") or out["filled"].get("phone"))
    if not out["contact_found"]:
        out["gaps"].append("no contact channel")
    if not out["filled"].get("website"):
        out["gaps"].append("no official website")
    return out


def apply_register(out, reg, today):
    if reg.get("verdict") == "verified":
        fill(out, "identity", "verified in an official register", reg.get("evidence", ""), f"GLEIF: active record, same legal name and country, {reg.get('checked')}", today)
        fill(out, "lei", reg.get("lei", ""), reg.get("evidence", ""), "GLEIF", today)
        fill(out, "registered_address", reg.get("register_address", ""), reg.get("evidence", ""), "GLEIF", today)
    elif reg.get("verdict") == "conflict":
        out["conflicts"].append("official register: " + (reg.get("why") or "the record does not match"))
    elif reg.get("verdict") == "likely":
        out["notes"].append("official register: a close name match only (not marked verified)")


def refine_project(r, today, links, open_ids):
    out = base(r["project_key"], "projects", today)
    c = out["cleaned"]
    country_fix(r.get("project_country", ""), c)
    v = num(r.get("value_usd"))
    if v is not None and (v < 0 or v > 2e11):
        c["value_usd"] = {"from": r["value_usd"], "to": "", "reason": "value outside any plausible project"}
    dates = {k: iso_date(r.get(k, "")) for k in ("plan_date", "financing_date", "board_date", "first_tender_date")}
    if dates["board_date"] and dates["financing_date"] and dates["financing_date"] < dates["board_date"]:
        out["notes"].append(f"financing date {dates['financing_date']} is before the board date {dates['board_date']}")
    ids = [x for x in (r.get("open_tender_ids") or "").replace(",", ";").split(";") if x.strip()]
    still = [x for x in ids if x.strip() in open_ids]
    if ids and len(still) != len(ids):
        c["open_tenders"] = {"from": r.get("open_tenders", ""), "to": str(len(still)), "reason": f"{len(ids) - len(still)} of its listed tenders are no longer open"}
    nd = iso_date(r.get("next_deadline", ""))
    if nd and nd < today.isoformat():
        c["next_deadline"] = {"from": nd, "to": "", "reason": "the deadline has passed"}
    if r.get("status") in ("closed", "dropped", "cancelled") and still:
        out["conflicts"].append(f"project marked {r['status']} but {len(still)} of its tenders are still open")
    lk = links.get(r.get("link", ""))
    if lk:
        bad = link_verdict(lk)
        if bad:
            out["conflicts"].append(bad)
        elif lk.get("status") == 200:
            fill(out, "link_checked", "reachable", r["link"], f"the project page answered, {lk.get('checked')}", today)
    if v is None or v <= 0:
        out["gaps"].append("no project value")
    if not r.get("buyer"):
        out["gaps"].append("no implementing agency")
    if not r.get("link"):
        out["gaps"].append("no link to the official project page")
    out["status"] = "open tenders" if still else ""
    return out


def refine_provider(r, module, today, links, site, reg):
    """Financing and logistics directories: curated rows, so the checks are of form, links, freshness and identity."""
    key = f"{r.get('name')}|{r.get('country_hq')}"
    out = base(key, module, today)
    c = out["cleaned"]
    country_fix(r.get("country_hq", ""), c)
    cats = FIN_CATS if module == "finance" else LOG_CATS
    if r.get("category") and r["category"] not in cats:
        out["conflicts"].append(f"category '{r['category']}' is not one of the fixed categories")
    if r.get("defence_ok") and r["defence_ok"] not in DEFENCE:
        out["conflicts"].append(f"defence_ok '{r['defence_ok']}' is not one of: {', '.join(sorted(DEFENCE))}")
    ver = iso_date(r.get("verified", ""))
    if not ver:
        out["gaps"].append("no verification date")
    elif ver < (today - timedelta(days=180)).isoformat():
        out["gaps"].append(f"verification older than 180 days ({ver}): due for a recheck on the official site")
    src_host = host(r.get("source_url", ""))
    for field in ("source_url", "apply_url" if module == "finance" else "contact_url"):
        u = r.get(field, "")
        if u.strip().lower() in ("not stated", "n/a", "none", "-"):
            u = ""
        if not u:
            out["gaps"].append(f"no {field}")
            continue
        if not url_ok(u):
            c[field] = {"from": u[:160], "to": "", "reason": "not a web address"}
            continue
        bad = link_verdict(links.get(u))
        if bad:
            out["conflicts"].append(f"{field}: {bad}")
        elif (links.get(u) or {}).get("status") == 200:
            fill(out, field + "_checked", "reachable", u, f"answered, {links[u].get('checked')}", today)
    other = host(r.get("apply_url") or r.get("contact_url") or "")
    if src_host and other and root(src_host) != root(other) and not (r.get("check_note") or "").count("source is not"):
        out["notes"].append(f"source page ({src_host}) and contact page ({other}) are on different domains")
    if "not confirmed" in (r.get("check_note") or ""):
        out["notes"].append("some facts not confirmed on the official page (see check_note)")
    if site and site.get("verdict") == "ok":
        if site.get("linkedin"):
            fill(out, "linkedin", site["linkedin"], site.get("website", ""), "linked from its own site", today)
        own = [x["email"] for x in site.get("emails") or [] if x.get("kind") in ("generic", "department")]
        if own:
            fill(out, "email", "; ".join(own[:2]), site.get("website", ""), "on its own domain", today)
        if site.get("whatsapp"):
            fill(out, "whatsapp", " ".join(site["whatsapp"]), site.get("website", ""), "linked from its own site", today)
    if reg:
        apply_register(out, reg, today)
    out["contact_found"] = bool(r.get("apply_url") or r.get("contact_url") or out["filled"].get("email"))
    return out


def refine_importer(r, today, reg):
    key = f"{r.get('company')}|{r.get('country')}|{r.get('hs4')}"
    out = base(key, "importers", today)
    c = out["cleaned"]
    nm = clean_text(r.get("company", ""))
    if nm != r.get("company"):
        c["company"] = {"from": r.get("company", "")[:150], "to": nm[:150], "reason": "HTML entities and spacing cleaned"}
    country_fix(r.get("country", ""), c)
    if r.get("profile") and not url_ok(r["profile"]):
        c["profile"] = {"from": r["profile"][:160], "to": "", "reason": "not a web address"}
    if reg:
        apply_register(out, reg, today)
    if r.get("website_wikidata"):
        fill(out, "website", r["website_wikidata"], "https://www.wikidata.org/", "Wikidata official website property (not checked yet)", today)
    else:
        out["gaps"].append("no official website")
    if not r.get("address"):
        out["gaps"].append("no address")
    out["gaps"].append("no contact channel (customs records carry none)")
    return out


# ---------------------------------------------------------------- network (budgeted, cached)
def check_links(urls, cache, budget, minutes=8):
    """GET each URL once per LINK_DAYS (stream, a few KB), one request at a time per host. Status kept in the cache."""
    import requests
    today = date.today().isoformat()
    stale = (date.today() - timedelta(days=LINK_DAYS)).isoformat()
    due = [u for u in dict.fromkeys(urls) if url_ok(u) and str((cache.get(u) or {}).get("checked", "")) < stale][:budget]
    by_host = defaultdict(list)
    for u in due:
        by_host[host(u)].append(u)
    deadline = time.time() + minutes * 60
    ua = {"User-Agent": "Mozilla/5.0 (compatible; SinderLinkCheck/1.0; +https://github.com/etaram/commodity-feeder)"}

    def run(us):
        s = requests.Session(); s.headers.update(ua)
        for u in us:
            if time.time() > deadline:
                return
            try:
                r = s.get(u, timeout=15, stream=True, allow_redirects=True)
                st = r.status_code; r.close()
            except requests.exceptions.ConnectionError as e:
                st = "dns" if "Name or service not known" in str(e) or "NameResolutionError" in str(e) else "unreachable"
            except Exception:  # noqa: BLE001
                st = "unreachable"
            cache[u] = {"status": st, "checked": today}
            time.sleep(1.0)

    with ThreadPoolExecutor(max_workers=24) as ex:
        list(ex.map(run, by_host.values()))
    return sum(1 for u in due if cache.get(u, {}).get("checked") == today)


def read_sites(items, cache, budget, minutes=8):
    """items: [(cache key, name, website)] -> company_check.fetch_site + analyse, once per SITE_DAYS."""
    from .company_check import analyse, fetch_site
    stale = (date.today() - timedelta(days=SITE_DAYS)).isoformat()
    due = [x for x in items if x[2] and str((cache.get(x[0]) or {}).get("checked", "")) < stale][:budget]
    deadline = time.time() + minutes * 60

    def one(x):
        k, name, site = x
        if time.time() > deadline:
            return None
        pages, why = fetch_site(site)
        res = analyse(name, "", pages) if pages else {"verdict": why.split(" (")[0]}
        return k, {**{f: res.get(f) for f in ("verdict", "name_match", "linkedin", "whatsapp", "emails", "phones", "description")}, "website": pages[0][0] if pages else site, "checked": date.today().isoformat()}

    n = 0
    with ThreadPoolExecutor(max_workers=24) as ex:
        for got in ex.map(one, due):
            if got:
                cache[got[0]] = got[1]; n += 1
    return n


def read_registers(items, cache, minutes):
    """items: [(cache key, name, iso3)] -> GLEIF lookups (about 60 a minute), once per REG_DAYS."""
    from .registry_check import _session, lei_lookup
    stale = (date.today() - timedelta(days=REG_DAYS)).isoformat()
    s, deadline, n = _session(), time.time() + minutes * 60, 0
    for k, name, cty in items:
        if time.time() > deadline:
            break
        if str((cache.get(k) or {}).get("checked", "")) >= stale or not cty:
            continue
        res = lei_lookup(s, name, cty)
        time.sleep(1.1)
        if res is None:
            continue
        cache[k] = {**res, "checked": date.today().isoformat()}; n += 1
    return n


def load_jsonl(p, key="key"):
    out = {}
    if p.exists():
        opener = gzip.open if p.suffix == ".gz" else open
        with opener(p, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line); out[d[key]] = d
                except (ValueError, KeyError):
                    pass
    return out


def save_jsonl(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if p.suffix == ".gz" else open
    with opener(p, "wt", encoding="utf-8") as f:
        for v in rows:
            f.write(json.dumps(v, ensure_ascii=False) + "\n")


def read_csv(p):
    return list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else []


# ---------------------------------------------------------------- main
def main(sample=0, link_budget=2500, site_budget=200, register_minutes=5, network=True):
    today = date.today()
    DIR.mkdir(parents=True, exist_ok=True); HIST.mkdir(parents=True, exist_ok=True); PUB.mkdir(parents=True, exist_ok=True)
    # tenders_all.csv lives with the collection runs (not in git); elsewhere the open list in the sheet chunks is read
    tenders = read_csv(LEADS / "tenders_all.csv")
    if not tenders:
        import glob
        for f in sorted(glob.glob(str(LEADS / "sheet" / "tenders_[0-9][0-9].csv"))):
            tenders += read_csv(type(LEADS)(f))
    buyers = read_csv(LEADS / "buyers.csv")
    accounts = read_csv(LEADS / "accounts.csv")
    projects = read_csv(LEADS / "project_timelines.csv")
    finance = read_csv(DATA / "finance" / "finance_providers.csv")
    logistics = read_csv(DATA / "logistics" / "logistics_providers.csv")
    importers = read_csv(LEADS / "importers_all.csv")
    pick = (lambda rows: rows[:: max(1, len(rows) // sample)][:sample]) if sample else (lambda rows: rows)  # noqa: E731

    links = json.loads(LINKS.read_text()) if LINKS.exists() else {}
    sites, regs = load_jsonl(SITES), load_jsonl(REGS)
    if network:
        # links: open notices first (they matter now), then projects and the two directories
        open_first = sorted(tenders, key=lambda r: (r.get("stage") != "tender", -(num(r.get("score")) or 0)))
        urls = [u for r in finance for u in (r.get("source_url"), r.get("apply_url"))] + [u for r in logistics for u in (r.get("source_url"), r.get("contact_url"))]
        urls += [r.get("link", "") for r in projects] + [r.get("link", "") for r in open_first]
        n_links = check_links([u for u in urls if u], links, link_budget)
        LINKS.write_text(json.dumps(links))
        # sites: the directories, then buyers with their own (non-free) mailbox domain
        items = [(f"finance|{r['name']}", r["name"], r.get("apply_url") or r.get("source_url")) for r in finance]
        items += [(f"logistics|{r['name']}", r["name"], r.get("contact_url") or r.get("source_url")) for r in logistics]
        for r in buyers:
            e = (emails_in(r.get("buyer_email", "")) or [""])[0]
            if e and not FREE.search(e):
                items.append((f"buyers|{r['buyer']}|{r['country']}", r["buyer"], "https://" + e.split("@")[1] + "/"))
        n_sites = read_sites(items, sites, site_budget)
        save_jsonl(SITES, ({"key": k, **v} for k, v in sites.items()))
        # registers: the directories (banks, insurers and forwarders carry LEIs), then non-government buyers and importers
        ritems = [(f"finance|{r['name']}", r["name"], r.get("country_hq")) for r in finance] + [(f"logistics|{r['name']}", r["name"], r.get("country_hq")) for r in logistics]
        ritems += [(f"buyers|{r['buyer']}|{r['country']}", r["buyer"], r["country"]) for r in buyers if re.search(r"\b(plc|ltd|limited|s\.?a\.?|gmbh|ag|inc|company|corporation|spa|s\.p\.a)\b", r["buyer"], re.I)]
        ritems += [(f"importers|{r['company']}|{to_iso3(r['country'])}", r["company"], to_iso3(r["country"])) for r in importers]
        n_regs = read_registers(ritems, regs, register_minutes)
        save_jsonl(REGS, ({"key": k, **v} for k, v in regs.items()))
    else:
        n_links = n_sites = n_regs = 0

    # buyer contacts seen in notices (official), by normalised buyer name and country
    tcontacts = defaultdict(list)
    for r in tenders:
        for e in emails_in(r.get("contact", ""))[:1]:
            tcontacts[(norm_name(r.get("buyer", "")), r.get("country", ""))].append((e, r.get("link", "")))
    open_ids = {r["id"].strip() for r in tenders if r.get("stage") == "tender" and (iso_date(r.get("deadline", "")) or "9999") >= today.isoformat()}

    results, progress = {}, {}
    # buyers and accounts first: tenders borrow their verified contacts
    bres = {}
    for rows, kind, namef in ((buyers, "buyers", "buyer"), (accounts, "accounts", "account")):
        for r in pick(rows):
            k = f"{r[namef]}|{r['country']}"
            res = refine_buyer(r, k, today, tcontacts.get((norm_name(r[namef]), r["country"]), []), sites.get(f"buyers|{k}"), regs.get(f"buyers|{k}"))
            res["module"] = kind
            bres[(norm_name(r[namef]), r["country"])] = res
            results.setdefault(kind, {})[k] = res
    for kind, rows, namef in (("buyers", buyers, "buyer"), ("accounts", accounts, "account")):
        dg = dup_groups(pick(rows), lambda r: f"{r[namef]}|{r['country']}",
                        lambda r: [("same name", (norm_name(r[namef]), r["country"]))],
                        lambda r: (num(r.get("awards_12m")) or 0, num(r.get("activity_score")) or 0))
        for k, (canon, size, why) in dg.items():
            if k in results[kind] and k != canon:
                results[kind][k]["duplicate"] = {"canonical": canon, "size": size, "signal": why}
    # tenders
    tres = {}
    for r in pick(tenders):
        bf = (bres.get((norm_name(r.get("buyer", "")), r.get("country", ""))) or {}).get("filled", {})
        tres[r["id"]] = refine_tender(r, today, links, bf)
    dg = tender_dups(pick(tenders))
    for k, (canon, size, why) in dg.items():
        if k in tres and k != canon:
            tres[k]["duplicate"] = {"canonical": canon, "size": size, "signal": why}
    results["tenders"] = tres
    results["projects"] = {r["project_key"]: refine_project(r, today, links, open_ids) for r in pick(projects)}
    dg = dup_groups(pick(projects), lambda r: r["project_key"], lambda r: [("same project reference", r.get("project_ref", "").strip().upper())],
                    lambda r: (num(r.get("n_events")) or 0,))
    for k, (canon, size, why) in dg.items():
        if k != canon:
            results["projects"][k]["duplicate"] = {"canonical": canon, "size": size, "signal": why}
    for module, rows in (("finance", finance), ("logistics", logistics)):
        results[module] = {}
        for r in rows:  # small directories: always whole
            res = refine_provider(r, module, today, links, sites.get(f"{module}|{r['name']}"), regs.get(f"{module}|{r['name']}"))
            results[module][res["key"]] = res
        dg = dup_groups(rows, lambda r: f"{r.get('name')}|{r.get('country_hq')}",
                        lambda r: [("same name", norm_name(r.get("name", ""))), ("same short name", (r.get("short_name") or "").strip().lower() if len(r.get("short_name") or "") > 2 else ""),
                                   ("same source page", (r.get("source_url") or "").rstrip("/").lower())],
                        lambda r: len(json.dumps(r)))
        for k, (canon, size, why) in dg.items():
            if k != canon and k in results[module]:
                results[module][k]["duplicate"] = {"canonical": canon, "size": size, "signal": why}
    results["importers"] = {}
    for r in pick(importers):
        res = refine_importer(r, today, regs.get(f"importers|{r['company']}|{to_iso3(r['country'])}"))
        results["importers"][res["key"]] = res
    dg = dup_groups(pick(importers), lambda r: f"{r.get('company')}|{r.get('country')}|{r.get('hs4')}",
                    lambda r: [("same company and heading", (norm_name(r.get("company", "")), to_iso3(r.get("country", "")), r.get("hs4", "")))],
                    lambda r: num(r.get("shipments_12m")) or 0)
    for k, (canon, size, why) in dg.items():
        if k != canon and k in results["importers"]:
            results["importers"][k]["duplicate"] = {"canonical": canon, "size": size, "signal": why}

    # a record whose inputs did not change and is still valid keeps its previous result (and its refined date)
    stale = (today - timedelta(days=VALID_DAYS)).isoformat()
    reused = Counter()
    for module, res in results.items():
        prev = load_jsonl(DIR / f"{module}.jsonl.gz")
        for k, v in res.items():
            h = sha(VERSION, json.dumps({x: v[x] for x in ("cleaned", "filled", "conflicts", "notes", "gaps", "status")}, sort_keys=True, default=str).replace(today.isoformat(), ""),
                    json.dumps(v.get("duplicate") or {}, sort_keys=True))
            v["input_hash"] = h
            p = prev.get(k)
            if p and p.get("input_hash") == h and p.get("refined", "") >= stale:
                res[k] = p; reused[module] += 1

    # backup once a day, then write; overlay and progress
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    for module, res in results.items():
        p = DIR / f"{module}.jsonl.gz"
        if p.exists() and not list(HIST.glob(f"{module}-{stamp}*.jsonl.gz")):
            shutil.copyfile(p, HIST / f"{module}-{stamp}.jsonl.gz")
            for old in sorted(HIST.glob(f"{module}-*.jsonl.gz"))[:-7]:
                old.unlink()
        if not sample:
            save_jsonl(p, res.values())
        st = Counter()
        for v in res.values():
            st["processed"] += 1
            st["completed"] += bool(v["filled"])
            st["contact_found"] += bool(v["contact_found"])
            st["with_conflicts"] += bool(v["conflicts"])
            st["with_gaps"] += bool(v["gaps"])
            st["cleaned"] += bool(v["cleaned"])
            st["duplicates"] += "duplicate" in v
            st["verified_identity"] += "identity" in v["filled"]
            st["closed_by_deadline"] += v.get("status", "").startswith("closed")
            for g in v["gaps"]:
                st["gap: " + re.sub(r"\(\d{4}-\d\d-\d\d\)", "", g).split(":")[0].strip()] += 1
            for c in v["conflicts"]:
                st["conflict: " + re.sub(r"\d{4}-\d\d-\d\d|\d+", "#", c)[:70]] += 1
            for f in v["cleaned"]:
                st["cleaned: " + f] += 1
        progress[module] = {**{k: v for k, v in st.items() if ":" not in k}, "reused_unchanged": reused[module],
                            "gaps": {k[5:]: v for k, v in st.most_common() if k.startswith("gap: ")},
                            "conflicts": {k[10:]: v for k, v in st.most_common(12) if k.startswith("conflict: ")},
                            "cleaned_fields": {k[9:]: v for k, v in st.most_common() if k.startswith("cleaned: ")}}
        if not sample:
            overlay(module, res)
    pp = LEADS / "refine_progress.json"
    prog = json.loads(pp.read_text()) if pp.exists() else {}
    prog["modules"] = {"version": VERSION, "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "sample": sample or None,
                       "links_checked_this_run": n_links, "links_on_record": len(links), "sites_read_this_run": n_sites, "registers_this_run": n_regs, **progress}
    pp.write_text(json.dumps(prog, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info("refine modules: %s", json.dumps({m: {k: v for k, v in p.items() if not isinstance(v, dict)} for m, p in progress.items()}))
    return prog["modules"]


def load_overlay(module):
    """{key: overlay row} for the pipeline to apply; empty when REFINE_MODULES=off (rollback) or not built yet."""
    import os
    if os.environ.get("REFINE_MODULES", "on") == "off":
        return {}
    p = PUB / f"{module}.csv"
    return {r["key"]: r for r in read_csv(p)} if p.exists() else {}


def overlay(module, res):
    """Public overlay of what the index must apply: duplicates, closed notices, conflicts, fixes and official fills."""
    cols = ["key", "status", "dup_of", "dup_signal", "conflicts", "cleaned", "contact_email", "contact_phone", "website", "linkedin", "lei", "identity", "gaps", "refined"]
    rows = []
    for v in res.values():
        f = v["filled"]
        if module == "tenders":
            # the open list already drops notices past their deadline, and a contact printed in the notice is already in it:
            # the overlay carries only what the index does not know (duplicates, conflicts, fixes, a contact from the buyer's record)
            borrowed = (f.get("contact_email") or {}).get("basis", "").startswith("the buyer's own")
            if not (v.get("duplicate") or v["conflicts"] or v["cleaned"] or borrowed):
                continue
        elif not (v.get("duplicate") or v.get("status") or v["conflicts"] or v["cleaned"] or f.get("identity") or f.get("website") or f.get("contact_email") or f.get("email")):
            continue
        rows.append({"key": v["key"], "status": v.get("status", ""), "dup_of": (v.get("duplicate") or {}).get("canonical", ""), "dup_signal": (v.get("duplicate") or {}).get("signal", ""),
                     "conflicts": "; ".join(v["conflicts"])[:300], "cleaned": "; ".join(f"{k}: {c.get('reason')}" for k, c in v["cleaned"].items())[:300],
                     "contact_email": (f.get("contact_email") or f.get("email") or {}).get("value", ""), "contact_phone": (f.get("contact_phone") or f.get("phone") or {}).get("value", ""),
                     "website": (f.get("website_confirmed") or f.get("website") or {}).get("value", ""), "linkedin": (f.get("linkedin") or {}).get("value", ""),
                     "lei": (f.get("lei") or {}).get("value", ""), "identity": (f.get("identity") or {}).get("basis", ""), "gaps": "; ".join(v["gaps"])[:200], "refined": v["refined"]})
    with open(PUB / f"{module}.csv", "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=cols); w.writeheader(); w.writerows(rows)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    a = sys.argv[1:]
    g = lambda f, d: int(a[a.index(f) + 1]) if f in a else d  # noqa: E731
    print(json.dumps(main(g("--sample", 0), g("--links", 2500), g("--sites", 200), g("--registers", 5), network="--offline" not in a), indent=1)[:3000])
