"""Transnet eTenders (South Africa, state-owned freight rail, ports and pipelines): the public list of advertised
tenders (https://transnetetenders.azurewebsites.net/Home/AdvertisedTenders), read from the JSON the page itself
loads (/Home/GetAdvertisedTenders): tender number, name, description, institution (TFR, TNPA, TPT, TE, TCC...),
category, location, published and closing dates, briefing details. 101 open on 13 Nov 2026 (Grok, checked).

Access (checked 2026-11-13 from the server): public, no sign-in, one request per run returns the whole list.
Bidding needs Transnet supplier registration and CSD; reading the list does not."""
import datetime as dt
import re

from .common import clean, log, quarantine_future, session, snapshot, today, valid_date
from .sectors import classify

PAGE = "https://transnetetenders.azurewebsites.net/Home/AdvertisedTenders"
URL = "https://transnetetenders.azurewebsites.net/Home/GetAdvertisedTenders"
INST = {"TFR": "Transnet Freight Rail", "TNPA": "Transnet National Ports Authority", "TPT": "Transnet Port Terminals",
        "TE": "Transnet Engineering", "TCC": "Transnet Corporate Centre", "TPL": "Transnet Pipelines", "TG": "Transnet Group"}


def _date(s):
    s = clean(str(s or ""))
    for cand, f in ((s, "%m/%d/%Y %I:%M:%S %p"), (s[:19], "%Y-%m-%dT%H:%M:%S"), (s[:19], "%Y-%m-%d %H:%M:%S"),
                    (s.split(" ")[0], "%m/%d/%Y"), (s[:10], "%Y-%m-%d")):
        try:
            return str(dt.datetime.strptime(cand, f).date())
        except ValueError:
            continue
    return ""


def _pick(rec, *subs):
    for k, v in rec.items():
        kl = k.lower()
        if all(s in kl for s in subs) and v not in (None, ""):
            return v
    return ""


def parse(js, fetched):
    if not isinstance(js, dict) or not isinstance(js.get("result"), list):
        raise ValueError("Transnet: response has no 'result' list (schema changed or error page)")
    rows = []
    for r in js["result"]:
        no = clean(r.get("tenderNumber") or _pick(r, "number"))
        title = clean(r.get("nameOfTender") or _pick(r, "name"))
        if not no or not title:
            continue
        status = clean(str(_pick(r, "status")))
        if status and re.search(r"cancel|award|closed", status, re.I):
            continue
        desc = clean(r.get("descriptionOfTender") or "")
        inst = clean(str(_pick(r, "institution")))
        buyer = INST.get(inst.upper(), f"Transnet ({inst})" if inst else "Transnet SOC Ltd")
        if buyer != "Transnet SOC Ltd" and not buyer.startswith("Transnet"):
            buyer = "Transnet " + buyer
        sector, how = classify(title + " " + desc[:200])
        att = clean(str(_pick(r, "attach")))
        rows.append({"id": "TRANSNET-" + re.sub(r"[^A-Za-z0-9]+", "-", no).strip("-")[:80], "source": "Transnet eTenders (South Africa)",
                     "group": "", "sector": sector, "nature": clean(str(_pick(r, "category"))), "cpv": "", "classification": how,
                     "country": "ZAF", "buyer": buyer, "title": title[:300],
                     "notice_type": clean(str(_pick(r, "type"))) or "Advertised tender", "stage": "tender",
                     "access": "Transnet supplier registration and CSD number required to bid",
                     "published": valid_date(_date(_pick(r, "publish"))), "deadline": valid_date(_date(_pick(r, "closing"))), "value": "", "currency": "",
                     "link": att if att.startswith("http") else PAGE, "source_url": PAGE, "fetched": fetched, "contact": "", "lang": "en"})
    return rows


def fetch():
    s = session()
    r = s.get(URL, timeout=60, headers={"X-Requested-With": "XMLHttpRequest", "Accept": "application/json"})
    r.raise_for_status()
    t = str(today())
    rows, q = quarantine_future(parse(r.json(), t), "transnet")
    rows = [x for x in rows if x["deadline"] and x["deadline"] >= t]    # OPEN = a future closing date
    keep, _ = snapshot("transnet", rows)          # complete list: cancelled / removed notices drop out
    log.info("Transnet: %d open with a future closing date, %d kept, %d quarantined", len(rows), len(keep), q)
    return keep, {"new": len(rows), "quarantined": q}
