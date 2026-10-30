"""Compact search indexes for the Deal Desk web app (filters by country, sector, value, deadline ...).

  python -m leads.webindex tenders     -> data/web/tenders.json.gz   (public data: every open notice, short fields)
  python -m leads.webindex suppliers   -> data/web/suppliers.enc     (Supplier Universe, ENCRYPTED with WEB_INDEX_KEY;
                                          contact fields - e-mail, phone, address, legal id - are never included)

Encryption: AES-256-GCM, file = 12-byte nonce + ciphertext+tag, plaintext = gzip(JSON). The key lives only in the
GitHub secret and the Vercel environment (WEB_INDEX_KEY, base64 of 32 bytes), so the public repo holds no readable
supplier data.
"""
import base64
import csv
import glob
import gzip
import json
import os
import sys

from .common import DATA, LEADS, PRIVATE, log

OUT = DATA / "web"


def _f(x):
    try:
        return round(float(x))
    except (TypeError, ValueError):
        return None


def tenders():
    rows = []
    for f in sorted(glob.glob(str(LEADS / "sheet" / "tenders_[0-9][0-9].csv"))):
        rows += list(csv.DictReader(open(f, encoding="utf-8")))
    gov = {}
    gv = LEADS / "governance.csv"
    if gv.exists():
        for r in csv.DictReader(open(gv, encoding="utf-8")):
            gov[r["country"]] = (r["integrity_score"], r["flag"])
    deal = {}
    dc = LEADS / "deal_calc.csv"
    if dc.exists():
        for r in csv.DictReader(open(dc, encoding="utf-8")):
            deal[r["id"]] = r
    out = []
    for r in rows:
        if not r.get("id"):
            continue
        d = deal.get(r["id"], {})
        acc = (r.get("access") or "").lower()
        out.append({
            "id": r["id"], "c": r.get("country", ""), "rg": r.get("region", ""), "s": r.get("sector", ""),
            "g": r.get("commodity", ""), "t": (r.get("title_en") or "")[:160], "b": (r.get("buyer") or "")[:80],
            "v": _f(r.get("est_value_usd")), "dl": r.get("deadline", ""), "dd": _f(r.get("days_left")),
            "d": r.get("decision", ""), "ev": _f(d.get("priority_ev_usd") or r.get("ev_usd")), "sc": _f(r.get("score")),
            "src": r.get("source", ""), "st": r.get("stage", ""), "l": r.get("link", ""), "n": 1 if r.get("new") else 0,
            "acc": "set-aside" if "set-aside" in acc else "intl" if acc.startswith("international") else "",
            "rt": d.get("route", ""),
            "ig": _f(gov.get(r.get("country", ""), ("", ""))[0]), "if": gov.get(r.get("country", ""), ("", ""))[1],
        })
    OUT.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(out, ensure_ascii=False, separators=(",", ":")).encode()
    (OUT / "tenders.json.gz").write_bytes(gzip.compress(raw, 9))
    log.info("web index: %d tenders, %.1f MB raw, %.1f MB gz", len(out), len(raw) / 1e6, (OUT / "tenders.json.gz").stat().st_size / 1e6)


SUP_FIELDS = {"quality": "q", "supplier": "n", "country": "c", "region": "rg", "tier": "tr", "main_sector": "s",
              "other_sectors": "s2", "type": "ty", "trader": "td", "epc": "epc", "logistics_role": "lg",
              "products": "p", "commodities": "cm", "exports": "x", "wins": "w", "won_usd_est": "u",
              "buyer_countries": "bc", "website": "web", "last_win": "lw",
              "tier_reason": "why"}
CUT = {"why": 90, "p": 90, "cm": 70, "s2": 70, "n": 90, "bc": 40, "web": 80}


def suppliers(limit=90_000):
    key = os.environ.get("WEB_INDEX_KEY", "")
    if not key:  # kept in the private Supplier Universe sheet (hidden tab Config), readable by the service account
        try:
            from .push import UNIVERSE_SHEET, Sheets
            key = next((r[1] for r in Sheets().values(UNIVERSE_SHEET, "Config!A1:B5") if len(r) > 1 and r[0] == "WEB_INDEX_KEY"), "")
        except Exception as e:  # noqa: BLE001
            log.warning("web index key from sheet: %s", e)
    if not key:
        log.warning("web index suppliers: WEB_INDEX_KEY not set - skipped"); return
    src = PRIVATE / "universe.csv"
    if not src.exists():
        log.warning("web index suppliers: %s missing", src); return
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    out = []
    for i, r in enumerate(csv.DictReader(open(src, encoding="utf-8"))):
        if i >= limit:
            break
        x = {}
        for k, short in SUP_FIELDS.items():
            v = (r.get(k) or "").strip()
            if not v:
                continue
            if short in ("q", "w", "u"):
                v = _f(v)
                if v is None:
                    continue
            elif short in CUT:
                v = v[:CUT[short]]
            x[short] = v
        if x.get("n"):
            out.append(x)
    raw = gzip.compress(json.dumps(out, ensure_ascii=False, separators=(",", ":")).encode(), 9)
    nonce = os.urandom(12)
    enc = nonce + AESGCM(base64.b64decode(key)).encrypt(nonce, raw, None)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "suppliers.enc").write_bytes(enc)
    log.info("web index: %d suppliers, %.1f MB encrypted", len(out), len(enc) / 1e6)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    what = sys.argv[1:] or ["tenders", "suppliers"]
    if "tenders" in what:
        tenders()
    if "suppliers" in what:
        suppliers()
