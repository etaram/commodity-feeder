"""Company and buyer footprints from every public award record the engine holds (idea taken from TenderAlpha's
company and agency profiles, built here from our own data at no cost).

company footprint: awards won, total value, by year, top project countries, top buyers, last awards
buyer profile:     awards made, total value, by year, top suppliers with their share, concentration (top-3 share)

Input: the same award rows as leads/winners.py (World Bank, TED, USAspending, open-contracting publishers).
Output: data/web/footprints.enc, encrypted with WEB_INDEX_KEY like the supplier index (the repository is public).
Names are grouped by a normalised name (legal suffixes removed); that is a first entity step, not full resolution.
"""
import base64
import gzip
import json
import os
import re
from collections import Counter, defaultdict

from .common import DATA, log
from .winners import _fx, _rows

OUT = DATA / "web"
STOP = {"co", "ltd", "limited", "llc", "inc", "plc", "sa", "sas", "srl", "spa", "gmbh", "ag", "bv", "pvt", "private", "the", "and", "of", "corp",
        "corporation", "company", "sdn", "bhd", "pte", "jsc", "ojsc", "pjsc", "cjsc", "pty", "sarl", "ltda", "cia", "sac", "eirl", "llp", "lp", "nv", "oy", "ab", "as"}
MAX_COMPANIES, MAX_BUYERS = 60_000, 25_000


def norm(name):
    t = [x for x in re.findall(r"[a-z0-9]+", (name or "").lower()) if x not in STOP and len(x) > 1]
    return " ".join(t)[:80]


def build():
    fx, fx_col = _fx()
    comp = defaultdict(lambda: {"n": "", "a": 0, "u": 0.0, "y": Counter(), "c": Counter(), "b": Counter(), "wc": Counter(), "last": []})
    buy = defaultdict(lambda: {"n": "", "c": "", "a": 0, "u": 0.0, "y": Counter(), "s": Counter(), "su": Counter()})
    n = 0
    for r in _rows():
        n += 1
        winners = r.get("winners") or []
        if isinstance(winners, str):
            winners = [w.strip() for w in winners.split(";") if w.strip()]
        if not winners:
            continue
        try:
            cur, val = (r.get("currency") or "USD").upper(), float(r.get("value") or 0)
            usd = float(r.get("value_usd") or 0) or (val if cur == "USD" else 0)
            if not usd and val and fx.get(cur):
                usd = val * fx[cur] if fx_col == "usd_per_unit" else val / fx[cur]
        except (TypeError, ValueError):
            usd = 0.0
        usd = usd if 0 < usd < 5e9 else 0.0
        share = usd / len(winners) if usd else 0.0
        year = (r.get("published") or "")[:4]
        ctry = (r.get("country") or "")[:3]
        buyer = (r.get("buyer") or "").strip()
        bk = f"{norm(buyer)}|{ctry}" if buyer else ""
        for w in winners[:6]:
            k = norm(w)
            if not k:
                continue
            c = comp[k]
            c["n"] = c["n"] or w.strip()[:90]
            c["a"] += 1; c["u"] += share
            if year: c["y"][year] += 1
            if ctry: c["c"][ctry] += 1
            if buyer: c["b"][buyer[:80]] += 1
            if r.get("winner_country"): c["wc"][str(r["winner_country"])[:3]] += 1
            if len(c["last"]) < 40:
                c["last"].append((r.get("published") or "")[:10] + "\t" + (r.get("title") or "")[:120] + "\t" + str(round(share)) + "\t" + ctry)
            if bk:
                b = buy[bk]
                b["n"] = b["n"] or buyer[:110]; b["c"] = ctry
                b["s"][c["n"]] += 1; b["su"][c["n"]] += share
        if bk:
            b = buy[bk]
            b["a"] += 1; b["u"] += usd
            if year: b["y"][year] += 1
    log.info("footprints: %d award rows, %d companies, %d buyers before cuts", n, len(comp), len(buy))
    # keep the companies and buyers that carry information: two awards or more, largest value first
    cs = sorted((k for k, v in comp.items() if v["a"] >= 2), key=lambda k: -comp[k]["u"])[:MAX_COMPANIES]
    bs = sorted((k for k, v in buy.items() if v["a"] >= 3), key=lambda k: -buy[k]["u"])[:MAX_BUYERS]
    companies = {}
    for k in cs:
        v = comp[k]
        last = sorted(v["last"], reverse=True)[:5]
        companies[k] = {"n": v["n"], "a": v["a"], "u": round(v["u"]), "y": dict(sorted(v["y"].items())[-8:]), "c": dict(v["c"].most_common(6)),
                        "b": [x for x, _ in v["b"].most_common(5)], "wc": (v["wc"].most_common(1) or [("", 0)])[0][0],
                        "l": [dict(zip(("d", "t", "u", "c"), x.split("\t"))) for x in last]}
    buyers = {}
    for k in bs:
        v = buy[k]
        tot = sum(v["su"].values()) or 0
        top = v["s"].most_common(8)
        top3 = sum(v["su"][x] for x, _ in top[:3])
        buyers[k] = {"n": v["n"], "c": v["c"], "a": v["a"], "u": round(v["u"]), "y": dict(sorted(v["y"].items())[-8:]),
                     "s": [{"n": x, "a": a, "sh": round(100 * v["su"][x] / tot, 1) if tot else None} for x, a in top],
                     "t3": round(100 * top3 / tot, 1) if tot else None}
    log.info("footprints: kept %d companies, %d buyers", len(companies), len(buyers))
    return {"companies": companies, "buyers": buyers}


def main():
    key = os.environ.get("WEB_INDEX_KEY", "")
    if not key:
        try:   # same fallback as the supplier index and the winners feed: the key kept in the universe sheet's Config tab
            from .push import UNIVERSE_SHEET, Sheets
            key = next((r[1] for r in Sheets().values(UNIVERSE_SHEET, "Config!A1:B5") if len(r) > 1 and r[0] == "WEB_INDEX_KEY"), "")
        except Exception as e:  # noqa: BLE001
            log.warning("footprints key from sheet: %s", e)
    if not key:
        log.warning("footprints: WEB_INDEX_KEY not set - nothing written"); return
    data = build()
    if not data["companies"]:
        log.warning("footprints: nothing built - previous file kept"); return
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import datetime as dt
    raw = gzip.compress(json.dumps({"at": dt.date.today().isoformat(), **data}, ensure_ascii=False, separators=(",", ":")).encode(), 9)
    nonce = os.urandom(12)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "footprints.enc").write_bytes(nonce + AESGCM(base64.b64decode(key)).encrypt(nonce, raw, None))
    log.info("footprints: %.1f MB encrypted", (OUT / "footprints.enc").stat().st_size / 1e6)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    main()
