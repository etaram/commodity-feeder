"""Morocco: open consultations on the national public procurement portal (marchespublics.gov.ma, Portail des
marches publics, Tresorerie Generale du Royaume): ministries, local authorities, public establishments.

Access (checked 2026-11-14): the public consultation list (index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons)
needs no login; robots.txt answers HTTP 403 to the runner (an unavailable robots.txt, which RFC 9309 treats as no
restriction); the portal is opened daily 07:30 to midnight Morocco time. We read the list page by page with the
page's own pager (PRADO form postback), one call at least 1.5 s after the previous, no relay. Each consultation links
to its own detail page (EntrepriseDetailsConsultation&refConsultation=...&orgAcronyme=...).

OPEN = a consultation whose 'Date limite de remise des plis' is today or later. The list holds about 100k
consultations, more than one run reads, so each run reads up to its time budget, newest pages first, and keeps the
open ones in a rolling cache; a run stops early after several pages in a row without an open consultation."""
import datetime as dt
import os
import re
import time

import requests

from .common import clean, log, quarantine_future, rolling, session, today
from .sectors import classify

BASE = "https://www.marchespublics.gov.ma"
LIST = BASE + "/index.php?page=entreprise.EntrepriseAdvancedSearch&AllCons"
DETAIL = BASE + "/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation={}&orgAcronyme={}"
BUDGET_S = int(os.environ.get("MOROCCO_BUDGET_S", "600"))
GAP = 1.5
PAGE_SIZE = "50"
EMPTY_STOP = 8
MONTHS = {"jan": 1, "fev": 2, "fév": 2, "mar": 3, "avr": 4, "mai": 5, "jui": 6, "juin": 6, "juil": 7, "aou": 8, "aoû": 8,
          "sep": 9, "oct": 10, "nov": 11, "dec": 12, "déc": 12}
PROC = {"AOO": "Appel d'offres ouvert", "AOR": "Appel d'offres restreint", "CNO": "Concours", "AMI": "Appel a manifestation d'interet",
        "BC": "Bon de commande", "AOS": "Appel d'offres sur offres de prix", "CONC": "Concours"}


def fr_date(s):
    m = re.search(r"(\d{1,2})\s+([A-Za-zéû]+)\.?\s+(\d{4})", s or "")
    if not m:
        return ""
    k = m.group(2).lower()
    mon = MONTHS.get(k) or MONTHS.get(k[:4]) or MONTHS.get(k[:3])
    if k.startswith("juil"):
        mon = 7
    elif k.startswith("juin"):
        mon = 6
    if not mon:
        return ""
    try:
        return str(dt.date(int(m.group(3)), mon, int(m.group(1))))
    except ValueError:
        return ""


def form_state(html):
    data = {}
    for m in re.finditer(r"<input([^>]*)>", html):
        a = m.group(1)
        n = re.search(r'name="([^"]+)"', a)
        if not n or re.search(r'type="(submit|image|button|checkbox|radio)"', a):
            continue
        v = re.search(r'value="([^"]*)"', a)
        data[n.group(1)] = (v.group(1) if v else "")
    for m in re.finditer(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', html, re.S):
        sel = re.search(r'<option[^>]*selected[^>]*value="([^"]*)"|<option[^>]*value="([^"]*)"[^>]*selected', m.group(2))
        data[m.group(1)] = (sel.group(1) or sel.group(2)) if sel else ""
    return data


def parse(html, ts):
    rows, n_items, n_open = [], 0, 0
    parts = re.split(r'(?=<div\s+class="contentColumn"\s+onclick=)', html)
    if len(parts) < 2:   # layout without the clickable wrapper: one part per detail link
        parts = re.split(r'(?=<[^>]*EntrepriseDetailsConsultation&(?:amp;)?refConsultation=\d+[^>]*echanges)', html)
    for p in parts[1:]:
        ref = re.search(r"refConsultation=(\d+)&(?:amp;)?orgAcronyme=([A-Za-z0-9_-]+)", p)
        if not ref:
            continue
        n_items += 1
        cid, org = ref.group(1), ref.group(2)
        text = clean(p)
        dl_m = re.search(r"Date limite de remise des plis\s+(?:[A-Za-zé]{3,4}\.?\s+)?(\d{1,2}\s+[A-Za-zéû]+\.?\s+\d{4})\s*(\d{1,2}:\d{2})?", text)
        dl = fr_date(dl_m.group(1)) if dl_m else ""
        if not dl or dl < ts:
            continue
        n_open += 1
        title = clean((re.search(r"Objet\s*:\s*(.*?)\s*(?:Détail|Estimation|Acheteur public)", text) or [None, ""])[1])
        buyer = clean((re.search(r"Acheteur public\s*:\s*(.*?)\s*(?:Date limite|$)", text) or [None, ""])[1])
        refno = clean((re.search(r"Référence\s*:\s*(\S+)", text) or [None, ""])[1])
        proc = clean((re.search(r'class="verticalText[^"]*">\s*<span[^>]*title="([^"]*)"', p) or [None, ""])[1])
        place = clean((re.search(r"Lieu d'exécution\s+(.*?)\s*(?:\.\.\.|Partager|$)", text) or [None, ""])[1])[:60]
        est = (re.search(r"Estimation TTC \(en DH\)\s*:\s*([\d\s.,]+)", text) or [None, ""])[1]
        try:
            val = round(float(re.sub(r"\s", "", est).replace(",", "."))) if est.strip() else ""
        except ValueError:
            val = ""
        if not title or not buyer:
            continue
        sector, how = classify(title)
        rows.append({"id": f"MA-PMP-{cid}", "source": "Portail des marches publics (Morocco)", "group": "", "sector": sector,
                     "nature": "works" if re.match(r"(?i)travaux", title) else "services" if re.match(r"(?i)(prestation|service|étude|etude|assistance|maintenance|entretien|gardiennage|nettoyage)", title) else "goods" if re.match(r"(?i)(achat|acquisition|fourniture)", title) else "",
                     "cpv": "", "classification": how, "country": "MAR",
                     "buyer": (buyer + (f", {place.title()}" if place else ""))[:120], "title": title[:300],
                     "notice_type": " | ".join(x for x in [proc, f"ref. {refno}" if refno else ""] if x)[:120], "stage": "tender",
                     "access": "Moroccan public procurement (foreign firms may bid; French-language documents; national preference may apply)",
                     "published": "", "deadline": dl, "deadline_basis": "date limite de remise des plis",
                     "deadline_time": (dl_m.group(2) + " Morocco time") if dl_m.group(2) else "",
                     "value": val, "currency": "MAD" if val else "", "link": DETAIL.format(cid, org), "source_url": LIST,
                     "fetched": ts, "contact": "", "lang": "fr"})
    return rows, n_items, n_open


class _Polite:
    def __init__(self):
        self.s = session()
        self.s.headers["Accept-Language"] = "fr-FR,fr;q=0.9,en;q=0.8"
        self.last, self.calls = 0.0, 0

    def _wait(self):
        d = time.time() - self.last
        if d < GAP:
            time.sleep(GAP - d)
        self.last = time.time(); self.calls += 1

    def get(self, url):
        self._wait()
        return requests.Session.get(self.s, url, timeout=90)

    def post(self, url, data):
        self._wait()
        return requests.Session.post(self.s, url, data=data, timeout=90, headers={"Referer": LIST})


def fetch():
    c, t0, ts = _Polite(), time.time(), str(today())
    r = c.get(LIST)
    if r.status_code != 200 or "PRADO_PAGESTATE" not in r.text:
        raise RuntimeError(f"Morocco: list page HTTP {r.status_code} (portal closed at night or unavailable); cache kept")
    html = r.text
    total_pages = (re.search(r'nombrePageTop">(\d+)<', html) or [None, "?"])[1]
    # 50 per page through the page's own page-size selector
    d = form_state(html)
    d.update({"PRADO_POSTBACK_TARGET": "ctl0$CONTENU_PAGE$resultSearch$listePageSizeTop", "PRADO_POSTBACK_PARAMETER": "",
              "ctl0$CONTENU_PAGE$resultSearch$listePageSizeTop": PAGE_SIZE,
              "ctl0$CONTENU_PAGE$resultSearch$listePageSizeBottom": PAGE_SIZE})
    rr = c.post(LIST, d)
    if rr.status_code == 200 and "PRADO_PAGESTATE" in rr.text:
        html = rr.text
    total_pages = (re.search(r'nombrePageTop">(\d+)<', html) or [None, total_pages])[1]
    out, pages, empty_run, seen, firsts, cut = {}, 0, 0, set(), [], False
    while True:
        got, n_items, n_open = parse(html, ts)
        pages += 1
        if pages == 1 and not n_items:
            i = html.find("refConsultation=")
            log.warning("Morocco: page 1 not parsed; around the first link: %r", " ".join(html[max(0, i - 400):i + 200].split()))
        sig = tuple(re.findall(r"refConsultation=(\d+)", html)[:5])
        if pages <= 3:
            firsts.append(re.findall(r"Date limite de remise des plis\s*</span>.*?<span[^>]*>\s*([^<]+?)\s*</span>", html, re.S)[:4])
        for x in got:
            out[x["id"]] = x
        empty_run = empty_run + 1 if n_open == 0 else 0
        if not n_items or sig in seen or empty_run >= EMPTY_STOP:
            break
        seen.add(sig)
        if time.time() - t0 > BUDGET_S:
            cut = True; break
        d = form_state(html)
        d.update({"PRADO_POSTBACK_TARGET": "ctl0$CONTENU_PAGE$resultSearch$PagerTop$ctl2", "PRADO_POSTBACK_PARAMETER": ""})
        try:
            rr = c.post(LIST, d)
        except requests.RequestException as e:
            log.warning("Morocco page %d: %s", pages + 1, type(e).__name__); cut = True; break
        if rr.status_code != 200 or "PRADO_PAGESTATE" not in rr.text:
            log.warning("Morocco page %d: HTTP %s", pages + 1, rr.status_code); cut = True; break
        html = rr.text
    log.info("Morocco: %d pages of %s read (page size %s), first deadlines %s", pages, total_pages, PAGE_SIZE, firsts)
    if not out:
        raise RuntimeError("Morocco: no open consultation read; cache kept")
    rows, q = quarantine_future(list(out.values()), "morocco")
    keep, _ = rolling("morocco", rows, max_age_days=120)
    log.info("Morocco: %d open consultations in the cache (%d read now, %d calls, %s)", len(keep), len(rows), c.calls,
             "cut at the time budget" if cut else "stopped after pages without open consultations" if empty_run >= EMPTY_STOP else "list end")
    return keep, {"new": len(rows), "pages": pages, "calls": c.calls, "quarantined": q, "deep_link": 1,
                  "complete_snapshot": 0, "note": "robots.txt answers 403 (RFC 9309: unavailable, no restriction)"}
