"""Italy: open calls for tender from ANAC's national legal-publicity platform (Pubblicita a Valore Legale, PVL,
pubblicitalegale.anticorruzione.it), where since 1 Jan 2024 every Italian contracting authority must publish its
notices, including those below the EU thresholds that TED does not carry. Public JSON API (/api/v0/avvisi), no key:
buyer, object, lots with CIG, nature, place, estimated value, submission deadline, link to the official notice.

About 4,700 notices of every kind are published per day (most are direct awards and contract changes, which are not
open calls), so each run reads only the last few publication days and keeps a rolling cache; the first run reads
FIRST_DAYS. Access (checked 2026-11-14): public JSON, no WAF, no robots.txt (the path returns the web app).
OPEN = an active, non-obscured 'avviso' with no awardee and a submission deadline today or later."""
import datetime as dt
import re
import time

from .common import cache_empty, clean, log, quarantine_future, rolling, session, today
from .sectors import classify

API = "https://pubblicitalegale.anticorruzione.it/api/v0/avvisi"
WEB = "https://pubblicitalegale.anticorruzione.it/bandi/{}"
FIRST_DAYS, DAYS = 30, 4
SIZE = 100
NATURE = {"lavori": "works", "forniture": "goods", "servizi": "services"}
VALUE_KEYS = ("valore_complessivo_stimato", "importo_complessivo", "valore_stimato", "importo_base_asta", "importo_lotto")


def _template(p):
    t = p.get("templates") or p.get("template") or []
    return (t[0].get("template") or {}) if t else {}


def _sections(p):
    return _template(p).get("sections") or []


def _lots(p):
    out = []
    for s in _sections(p):
        if str(s.get("name", "")).startswith("SEZ. C"):
            out += s.get("items") or []
    return out


def _deadline(p, lots):
    d = (p.get("dataScadenza") or "")[:10]
    if d:
        return d
    ds = [str(l.get("termine_ricezione") or l.get("termine_invito") or "")[:10] for l in lots]
    ds = [x for x in ds if re.fullmatch(r"\d{4}-\d{2}-\d{2}", x)]
    return min(ds) if ds else ""


def parse(items, fetched, t):
    rows = []
    for p in items:
        if p.get("tipo") != "avviso" or not p.get("attivo") or p.get("oscurato"):
            continue
        lots = _lots(p)
        if any(l.get("aggiudicatari_ad") or l.get("aggiudicatari") or l.get("tipo_oggetto") == "aggiudicazione" for l in lots):
            continue
        dl = _deadline(p, lots)
        if not dl or dl < t:
            continue
        meta = _template(p).get("metadata") or {}
        title = clean(meta.get("titolo") or meta.get("descrizione") or (lots[0].get("descrizione") if lots else "") or "")
        buyer = ""
        link = ""
        for s in _sections(p):
            f = s.get("fields") or {}
            if f.get("soggetti_sa"):
                buyer = buyer or clean(f["soggetti_sa"][0].get("denominazione_amministrazione") or "")
            link = link or f.get("documenti_di_gara_link") or ""
        if not title or not buyer:
            continue
        val = 0.0
        for l in lots:
            for k in VALUE_KEYS:
                try:
                    if l.get(k):
                        val += float(l[k]); break
                except (TypeError, ValueError):
                    pass
        nat = (lots[0].get("natura_principale") or "").lower() if lots else ""
        place = (lots[0].get("luogo_istat") or lots[0].get("luogo_nuts") or "") if lots else ""
        cigs = ",".join(str(l["cig"]) for l in lots if l.get("cig"))[:120]
        sector, how = classify(title)
        rows.append({"id": "IT-PVL-" + p["idAvviso"], "source": "ANAC PVL (Italy, national)", "group": "", "sector": sector,
                     "nature": NATURE.get(nat, ""), "cpv": "", "classification": how, "country": "ITA",
                     "buyer": (buyer + (f", {clean(place).title()}" if place and place != "ITALIA" else ""))[:120],
                     "title": title[:300],
                     "notice_type": f"{(p.get('tipologia') or 'Bando').replace('_', ' ').lower()} | {len(lots)} lot(s)" + (f" | CIG {cigs}" if cigs else ""),
                     "stage": "tender", "access": "Italian public procurement (EU firms may bid; Italian-language documents)",
                     "published": (p.get("dataPubblicazione") or "")[:10], "deadline": dl, "deadline_basis": "submission",
                     "value": round(val) if val else "", "currency": "EUR" if val else "",
                     "link": WEB.format(p["idAvviso"]), "source_url": link or API, "fetched": fetched, "contact": "", "lang": "it"})
    return rows


def fetch():
    s, t = session(), today()
    ts = str(t)
    days = FIRST_DAYS if cache_empty("italy") else DAYS
    new, calls, failed = [], 0, 0
    for back in range(days, -1, -1):
        d = (t - dt.timedelta(days=back)).strftime("%d/%m/%Y")
        page = 0
        while True:
            try:
                r = s.get(API, params={"page": page, "size": SIZE, "sortField": "dataPubblicazione", "sortDirection": "DESC",
                                       "dataPubblicazioneStart": d, "dataPubblicazioneEnd": d}, timeout=90)
                calls += 1
                r.raise_for_status()
                j = r.json()
            except Exception as e:  # noqa: BLE001
                log.warning("Italy PVL %s page %d: %s", d, page, str(e)[:100]); failed += 1; break
            new += parse(j.get("content") or [], ts, ts)
            if j.get("last", True) or page >= 200:
                break
            page += 1
            time.sleep(0.3)
    if not new and failed:
        raise RuntimeError("Italy PVL: nothing read; previous rows kept")
    new, q = quarantine_future(new, "italy")
    rows, _ = rolling("italy", new, max_age_days=180)
    log.info("Italy PVL: %d open calls (%d new from %d days, %d calls, %d failed pages)", len(rows), len(new), days + 1, calls, failed)
    return rows, {"new": len(new), "calls": calls, "quarantined": q, "parts_failed": failed}
