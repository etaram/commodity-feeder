"""Encrypted snapshot of the Opportunity Panel's sheet tabs for the web panel on Vercel.

  python -m leads.webpanel static  -> data/web/panel_static.enc  (My Leads, Upcoming, Titles HE, Repeat Buyers,
                                       Market Signals, Meta, total count, fit per tender id)  - after each data run
  python -m leads.webpanel live    -> data/web/panel_live.enc    (BD Agent, Key Accounts, Intel, Pursuits, Panel Jobs,
                                       supplier Stats)  - hourly

Same format as suppliers.enc: AES-256-GCM with WEB_INDEX_KEY, file = 12-byte nonce + ciphertext+tag, plaintext =
gzip(JSON {key: [[header...], [row...], ...]}). A file is rewritten only when its content changed (sha of the
plaintext in a side file), so the public repo does not grow with identical snapshots. No supplier contact data is
exported (suppliers come from suppliers.enc, which never holds contacts).
"""
import base64
import gzip
import hashlib
import json
import os
import sys

from .common import DATA, log
from .push import LEADS_SHEET as LE, UNIVERSE_SHEET as SU, Sheets

OUT = DATA / "web"

PARTS = {
    "static": {
        "tenders": (LE, "'My Leads'!A1:AE1500"),
        "titles": (LE, "'Titles HE'!A1:B20000"),
        "repeat": (LE, "'Repeat Buyers'!A1:O5600"),
        "markets": (LE, "'Market Signals'!A1:O3200"),
        "meta": (LE, "'Meta'!A1:B5"),
        "upcoming": (LE, "'Upcoming'!A1:AE1500"),
        "tot_t": (LE, "'Panel Search'!A6:B6"),
        "fit_ids": (LE, "'Tenders'!S1:S60000"),
        "fit_cols": (LE, "'Tenders'!AC1:AE60000"),
    },
    "live": {
        "bd": (LE, "'BD Agent'!A1:M600"),
        "accounts": (LE, "'Key Accounts'!A1:S400"),
        "intel": (LE, "'Intel'!A1:P2000"),
        "pursuits": (LE, "'Pursuits'!A1:V600"),
        "jobs": (LE, "'Panel Jobs'!A1:L800"),
        "contacts": (LE, "'Contacts'!A1:S1500"),
        "stats": (SU, "'Stats'!A1:B60"),
    },
}


def _key():
    key = os.environ.get("WEB_INDEX_KEY", "")
    if key:
        return key
    return next((r[1] for r in Sheets().values(SU, "Config!A1:B5") if len(r) > 1 and r[0] == "WEB_INDEX_KEY"), "")


def export(part):
    sh = Sheets()
    data = {}
    for k, (sid, rng) in PARTS[part].items():
        try:
            data[k] = sh.values(sid, rng)
        except Exception as e:  # noqa: BLE001 - a missing optional tab must not stop the export
            log.warning("web panel %s: %s", k, str(e)[:160])
            data[k] = []
    if part == "static":  # one compact map id -> [fit, your_suppliers, tier_AB] for the full-database search
        ids, cols = data.pop("fit_ids"), data.pop("fit_cols")
        data["fit"] = {(ids[i] or [""])[0]: (cols[i] if i < len(cols) else []) for i in range(1, len(ids)) if ids[i] and ids[i][0]}
    plain = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    sha = hashlib.sha256(plain).hexdigest()
    shaf = OUT / f"panel_{part}.sha"
    if shaf.exists() and shaf.read_text().strip() == sha and (OUT / f"panel_{part}.enc").exists():
        log.info("web panel %s: unchanged", part); return
    key = _key()
    if not key:
        log.warning("web panel: WEB_INDEX_KEY not available - skipped"); return
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = gzip.compress(plain, 9)
    nonce = os.urandom(12)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"panel_{part}.enc").write_bytes(nonce + AESGCM(base64.b64decode(key)).encrypt(nonce, raw, None))
    shaf.write_text(sha)
    log.info("web panel %s: %s, %.1f MB encrypted", part, ", ".join(f"{k} {len(v)}" for k, v in data.items()), len(raw) / 1e6)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    for p in sys.argv[1:] or ["static", "live"]:
        export(p)
