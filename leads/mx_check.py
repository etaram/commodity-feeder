"""Contact quality: does each supplier e-mail domain accept mail? One DNS lookup set per unique domain, cached and
resumable, run at low priority in the company-check workflow.

Verdict per domain (data/checks/mx_domains.jsonl, kept in that workflow's Actions cache, never published):
  mx_ok        the domain publishes MX records that point to real mail hosts
  no_mx        no MX record (detail: "a_only" when only an A/AAAA record exists - RFC 5321 implicit MX, often not a
               mailbox; "nxdomain" when the domain does not exist; "null_mx" for an explicit "MX 0 ." refusal)
  parked       MX or NS points at a domain-parking or for-sale service
  disposable   a throwaway-mailbox provider
Plus "error" (resolver timeout or failure), which is retried on the next run. A verdict is re-checked after 90 days.

Read by: leads/universe.py (field email_mx), leads/refine.py (counts in refine_progress.json), leads/source_cycle.py
(weekly per-region count of suppliers with an mx_ok e-mail).

  python -m leads.mx_check [--minutes 8] [--workers 12]"""
import argparse
import csv
import datetime as dt
import json
import os
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from .common import DATA, PRIVATE, log

OUT = DATA / "checks" / "mx_domains.jsonl"
RECHECK_DAYS = 90
VERDICTS = ("mx_ok", "no_mx", "parked", "disposable")
# large mailbox providers: known to accept mail, no lookup spent on them
KNOWN_MAIL = {"gmail.com", "googlemail.com", "yahoo.com", "hotmail.com", "outlook.com", "live.com", "msn.com", "icloud.com",
              "me.com", "aol.com", "gmx.com", "gmx.de", "gmx.net", "web.de", "yandex.ru", "yandex.com", "mail.ru", "qq.com",
              "163.com", "126.com", "sina.com", "sohu.com", "naver.com", "daum.net", "hanmail.net", "rediffmail.com",
              "yahoo.co.in", "yahoo.co.uk", "yahoo.fr", "hotmail.fr", "orange.fr", "free.fr", "libero.it", "zoho.com",
              "protonmail.com", "proton.me", "t-online.de", "bigpond.com", "uol.com.br", "bol.com.br", "terra.com.br"}
DISPOSABLE = {"mailinator.com", "guerrillamail.com", "guerrillamail.net", "10minutemail.com", "tempmail.com", "temp-mail.org",
              "yopmail.com", "trashmail.com", "sharklasers.com", "getnada.com", "dispostable.com", "maildrop.cc",
              "throwawaymail.com", "fakeinbox.com", "mintemail.com", "mohmal.com", "emailondeck.com", "tempail.com",
              "mailnesia.com", "spamgourmet.com", "mytemp.email", "tempr.email", "discard.email", "moakt.com",
              "burnermail.io", "tmpmail.org", "33mail.com", "inboxkitten.com", "mailcatch.com", "trbvm.com"}
PARKING = re.compile(r"(sedoparking|parkingcrew|bodis\.com|above\.com|\bdan\.com|afternic|hugedomains|namebrightdns|parklogic|"
                     r"domainparking|parked\.com|uniregistrymarket|undeveloped\.com|sav\.com|smartname|ztomy|dsredirection|"
                     r"parkpage|park\.|cashparking|voodoo\.com|fabulous\.com|rookdns|epik\.com)", re.I)
DOMAIN = re.compile(r"^[a-z0-9.-]+\.[a-z]{2,24}$")


def domain_of(email):
    e = (email or "").strip().lower().strip("<>.,;: ")
    if "@" not in e:
        return ""
    d = e.rsplit("@", 1)[1].strip().rstrip(".")
    return d if DOMAIN.match(d) and ".." not in d else ""


def domains_of(field):
    """all domains in an e-mail field ('a@x.com; b@y.org')."""
    return [d for d in (domain_of(x) for x in re.split(r"[;,\s]+", field or "")) if d]


def classify(domain, mx_hosts, ns_hosts, has_a, nx=False):
    """verdict, detail from DNS answers (pure: tested without network)."""
    if domain in DISPOSABLE:
        return "disposable", ""
    if nx:
        return "no_mx", "nxdomain"
    hosts = [h.lower().rstrip(".") for h in mx_hosts]
    if any(PARKING.search(h) for h in hosts) or any(PARKING.search(h.lower()) for h in ns_hosts):
        return "parked", (hosts or list(ns_hosts) or [""])[0][:60]
    if hosts == [""] or hosts == ["."]:
        return "no_mx", "null_mx"
    if hosts:
        return "mx_ok", hosts[0][:60]
    return "no_mx", "a_only" if has_a else "no_records"


def lookup(domain, resolver=None):
    """DNS answers for one domain -> (verdict, detail). Network: MX, then NS, then A when there is no MX."""
    if domain in KNOWN_MAIL:
        return "mx_ok", "known provider"
    if domain in DISPOSABLE:
        return "disposable", ""
    import dns.exception
    import dns.resolver
    r = resolver or _resolver()
    mx, ns, has_a, nx = [], [], False, False
    try:
        ans = r.resolve(domain, "MX")
        mx = [str(x.exchange) for x in sorted(ans, key=lambda x: x.preference)]
    except dns.resolver.NXDOMAIN:
        nx = True
    except (dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        pass
    except dns.exception.Timeout:
        return "error", "timeout"
    if nx:
        return classify(domain, [], [], False, nx=True)
    try:
        ns = [str(x.target) for x in r.resolve(domain, "NS")]
    except Exception:  # noqa: BLE001
        ns = []
    if not mx:
        try:
            r.resolve(domain, "A"); has_a = True
        except Exception:  # noqa: BLE001
            has_a = False
    return classify(domain, mx, ns, has_a)


def _resolver():
    import dns.resolver
    r = dns.resolver.Resolver()
    r.timeout, r.lifetime = 4, 8
    return r


def load_results(path=OUT):
    out = {}
    if not path.exists():
        return out
    for line in open(path, encoding="utf-8"):
        try:
            d = json.loads(line)
            out[d["domain"]] = d
        except (ValueError, KeyError):
            pass
    return out


def verdict_for(field, results):
    """the verdict of the first e-mail in a field that has one ('' when unchecked)."""
    for d in domains_of(field):
        v = (results.get(d) or {}).get("verdict")
        if v in VERDICTS:
            return v
    return ""


def wanted_domains(universe=None):
    """unique e-mail domains of the supplier universe, most frequent first (a shared domain checked once)."""
    p = universe or PRIVATE / "universe.csv"
    c = Counter()
    if not p.exists():
        return []
    csv.field_size_limit(10 ** 8)
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for d in domains_of(r.get("email")):
                c[d] += 1
    return [d for d, _ in c.most_common()]


def run(minutes=8.0, workers=12, universe=None, out=OUT, lookup_fn=None):
    try:
        os.nice(10)  # low priority on the shared runner
    except OSError:
        pass
    lookup_fn = lookup_fn or lookup
    have = load_results(out)
    cut = str(dt.date.today() - dt.timedelta(days=RECHECK_DAYS))
    doms = wanted_domains(universe)
    todo = [d for d in doms if d not in have or have[d].get("verdict") == "error" or have[d].get("checked", "") < cut]
    t_end, done = time.time() + minutes * 60, 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "a", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=workers) as ex:
        for i in range(0, len(todo), workers * 20):
            if time.time() > t_end:
                break
            chunk = todo[i:i + workers * 20]
            for d, (v, det) in zip(chunk, ex.map(lambda x: _safe(lookup_fn, x), chunk)):
                rec = {"domain": d, "verdict": v, "detail": det, "checked": str(dt.date.today())}
                have[d] = rec
                f.write(json.dumps(rec) + "\n")
                done += 1
    # compact: one line per domain (the append log grows by re-checks)
    with open(out, "w", encoding="utf-8") as f:
        for rec in have.values():
            f.write(json.dumps(rec) + "\n")
    tally = Counter(v.get("verdict") for v in have.values())
    stats = {"domains": len(doms), "checked_now": done, "pending": max(0, len(todo) - done), **{k: tally.get(k, 0) for k in (*VERDICTS, "error")}}
    log.info("mx check %s", json.dumps(stats))
    return stats


def _safe(fn, d):
    try:
        return fn(d)
    except Exception as e:  # noqa: BLE001
        return "error", type(e).__name__[:40]


def summary(rows, results=None):
    """counts of suppliers by the verdict of their e-mail (for refine_progress.json)."""
    results = load_results() if results is None else results
    c = Counter()
    for r in rows:
        if r.get("email"):
            c[verdict_for(r["email"], results) or "unchecked"] += 1
    return dict(c)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=8); ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args()
    print(json.dumps(run(a.minutes, a.workers)))
