"""Private data drops: supplier files the user hands over (research exports, directories) enter the supplier universe
without ever being readable in the public repository.

  Keys:  `python -m leads.importer init` runs in GitHub Actions. It makes an RSA key pair once; the private key goes
         straight to the private Supplier Universe sheet (hidden tab Config, row IMPORT_PRIVATE_KEY, readable only by
         the service account) and only the public key is committed (data/import/import_public_key.pem).
  Seal:  `python -m leads.importer seal <rows.jsonl> <name>` (anywhere, with the public key only): AES-256-GCM with a
         random key, wrapped with RSA-OAEP, written to data/import/<name>.enc.
  Read:  rows() opens every data/import/*.enc with the private key and returns the rows for leads/universe.py.

Row format (one JSON object per line): supplier, name_local, country (ISO3), province, city, industry, products,
website, email, phone, address, source, source_url, notable (bool), basis, plus any extra keys. Rows keep their
provenance; nothing here is marked verified."""
import base64
import gzip
import json
import os
import sys

from .common import DATA, log

DIR = DATA / "import"
PUB = DIR / "import_public_key.pem"
ROW = "IMPORT_PRIVATE_KEY"


def _config():
    from .push import UNIVERSE_SHEET, Sheets
    s = Sheets()
    return s, UNIVERSE_SHEET, s.values(UNIVERSE_SHEET, "Config!A1:B60")


def init():
    """Once: key pair; the private half only ever lives in the private sheet."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    s, sid, rows = _config()
    have = next((r for r in rows if r and r[0] == ROW and len(r) > 1 and r[1]), None)
    if have and PUB.exists():
        log.info("import keys: already set"); return
    if have and not PUB.exists():
        priv = serialization.load_pem_private_key(base64.b64decode(have[1]), None)
    else:
        priv = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        pem = priv.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        n = len(rows) + 1
        s._req("PUT", f"https://sheets.googleapis.com/v4/spreadsheets/{sid}/values/Config!A{n}:B{n}", params={"valueInputOption": "RAW"},
               json={"values": [[ROW, base64.b64encode(pem).decode()]]})
    DIR.mkdir(parents=True, exist_ok=True)
    PUB.write_bytes(priv.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    log.info("import keys: public key written to %s", PUB)


def seal(src, name):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    pub = serialization.load_pem_public_key(PUB.read_bytes())
    key, nonce = AESGCM.generate_key(256), os.urandom(12)
    data = gzip.compress(open(src, "rb").read(), 9)
    blob = {"v": 1, "name": name, "wrapped": base64.b64encode(pub.encrypt(key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))).decode(),
            "nonce": base64.b64encode(nonce).decode(), "data": base64.b64encode(AESGCM(key).encrypt(nonce, data, name.encode())).decode()}
    out = DIR / f"{name}.enc"
    out.write_text(json.dumps(blob))
    return out


def rows():
    """Every sealed drop, decrypted (empty when the key cannot be read: no credentials)."""
    files = sorted(DIR.glob("*.enc"))
    if not files:
        return []
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        _, _, cfg = _config()
        pk = next(r[1] for r in cfg if r and r[0] == ROW and len(r) > 1)
        priv = serialization.load_pem_private_key(base64.b64decode(pk), None)
    except (Exception, SystemExit, StopIteration) as e:  # noqa: BLE001
        log.info("imports not read (%s)", str(e)[:100]); return []
    out = []
    for f in files:
        try:
            b = json.loads(f.read_text())
            key = priv.decrypt(base64.b64decode(b["wrapped"]), padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
            raw = gzip.decompress(AESGCM(key).decrypt(base64.b64decode(b["nonce"]), base64.b64decode(b["data"]), b["name"].encode()))
            n = 0
            for line in raw.decode("utf-8").splitlines():
                if line.strip():
                    r = json.loads(line); r["_drop"] = b["name"]; out.append(r); n += 1
            log.info("import %s: %d rows", b["name"], n)
        except Exception as e:  # noqa: BLE001
            log.warning("import %s not read: %s", f.name, str(e)[:120])
    return out


# ---------------------------------------------------------------- adapters (run locally on the user's file)
def china_directory(path):
    """China business directory (candidate universe, partial enrichment) -> rows. Only what the file states, with its
    own status labels; secondary-directory SMEs are candidates, Fortune China 500 entries are notable."""
    d = json.load(open(path, encoding="utf-8"))
    out = []
    for c in d["companies"]:
        loc, ind, ct = c.get("location") or {}, c.get("industry") or {}, c.get("contacts") or {}
        ev = (c.get("selection_evidence") or [{}])[0]
        fortune = ev.get("type") == "Fortune_China_500"
        emails = [e["value"] for e in ct.get("emails") or [] if e.get("value") and e.get("commercial") is not False]
        phones = [p["value"] for p in ct.get("phones") or [] if p.get("value")]
        prods = [p.get("description") for p in c.get("products") or [] if p.get("description")]
        fin = c.get("financials") or {}
        out.append({
            "supplier": c.get("company_name_en") or c["company_name_zh"], "name_local": c["company_name_zh"], "country": "CHN",
            "province": loc.get("province_en") or "", "city": loc.get("city_zh") or "", "industry": ind.get("en") or "",
            "products": ", ".join(prods)[:300], "website": c.get("website") or "", "email": "; ".join(emails[:2]), "phone": "; ".join(phones[:2]),
            "address": ct.get("address") or "", "source": "Fortune China 500 (2026)" if fortune else "China specialised SME directory (secondary, unverified)",
            "source_url": ev.get("source_url") or (c.get("source_urls") or [""])[0], "notable": fortune,
            "basis": f"rank {ev.get('rank')} by revenue" if fortune else f"reported national specialised SME, {ev.get('year', '')} {ev.get('batch_zh', '')}".strip(),
            "revenue_musd": fin.get("revenue") if fortune else None, "employees": fin.get("employees") if fortune else None,
            "id": c.get("company_id"), "flags": "; ".join(c.get("quality_flags") or [])[:200]})
    # contact candidates whose current page was read and still shows the address (the rest stay out)
    for s in d.get("supplemental_contact_candidates") or []:
        chk = s.get("current_page_check") or {}
        if chk.get("outcome") != "page_read" or not s.get("company_name_en_as_reported"):
            continue
        em = s.get("email_as_reported") if s.get("email_as_reported") in (chk.get("previous_email_present") or []) else ""
        out.append({"supplier": s["company_name_en_as_reported"], "name_local": "", "country": "CHN" if s.get("country_as_reported") == "China" else s.get("country_as_reported", ""),
                    "products": s.get("products_as_reported") or "", "website": s.get("website_as_reported") or "", "email": em,
                    "phone": s.get("phone_as_reported") or "", "source": "Contact page re-read 2026-11-05", "source_url": chk.get("final_url") or s.get("source_url") or "",
                    "notable": False, "basis": f"contact page read {chk.get('checked_date')}", "id": s.get("source_supplier_id")})
    return out


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    a = sys.argv[1:]
    if a[:1] == ["init"]:
        init()
    elif a[:1] == ["seal"]:
        print(seal(a[1], a[2]))
    elif a[:1] == ["china"]:
        rows_ = china_directory(a[1])
        with open(a[2], "w", encoding="utf-8") as f:
            for r in rows_:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(len(rows_), "rows")
