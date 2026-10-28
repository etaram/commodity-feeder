"""Supplier Universe (A-tier): every company that won a public tender in the last 24 months, across all award
sources, with what it won, where, for whom, and the contact details published in the notices.
Output is private: data/private/universe.csv (git-ignored), pushed to the private Supplier Universe sheet."""
import csv
import json
import re
from collections import defaultdict

from .common import AWARDS, PRIVATE, log, today
from .regions import iso3, region
from .sectors import SECTORS

LEGAL = re.compile(r"\b(gmbh|ag|kg|sa|s\.a\.|sas|sarl|srl|s\.r\.l\.|spa|s\.p\.a\.|bv|nv|ltd|limited|llc|inc|plc|oy|ab|as|a/s|"
                   r"sp\. z o\.o\.|s\.r\.o\.|kft|d\.o\.o\.|ooo|tov|co\.?|corp|corporation|company|group|holding)\b")
GOODS = {"AGRI_FOOD", "ENERGY", "POWER", "MINING_METALS", "CHEMICALS", "TEXTILES", "CONSTR_MAT", "MACHINERY",
         "TRANSPORT_EQ", "DEFENCE", "HEALTH", "LAB", "ICT", "CONSUMER", "WATER"}
NAME2ID = {v: k for k, v in SECTORS.items()}


def norm(n):
    n = re.sub(r"[^\w ]", " ", (n or "").lower())
    n = LEGAL.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip()[:80]


def _rates():
    try:
        from .run import _rates as r
        return r()
    except Exception:  # noqa: BLE001
        return {"USD": 1, "EUR": 1.08, "GBP": 1.27}


def build():
    rates = _rates()
    sup = defaultdict(lambda: {"names": defaultdict(int), "country": defaultdict(int), "wins": 0, "usd": 0.0,
                               "sectors": defaultdict(int), "cpv": defaultdict(int), "buyer_c": set(), "buyers": set(),
                               "last": "", "first": "9999", "sources": set(), "example": "", "ex_usd": 0,
                               "email": "", "phone": "", "website": "", "address": "", "legal_id": "", "goods": 0})
    files = sorted(AWARDS.glob("*.json")) + sorted(AWARDS.glob("*/*.json"))
    n_aw = 0
    for f in files:
        for a in json.loads(f.read_text()):
            if a.get("empty") or not a.get("winners"):
                continue
            n_aw += 1
            wcs = [x.strip() for x in (a.get("winner_country") or "").split(",") if x.strip()]
            v, c = a.get("value"), a.get("currency")
            usd = v * rates.get(c, 0) if isinstance(v, (int, float)) and c in rates else 0
            usd = usd if usd < 2e9 else 0
            share = usd / max(1, len(a["winners"]))
            for i, w in enumerate(a["winners"]):
                k = norm(w)
                if len(k) < 3:
                    continue
                wc = iso3(wcs[i] if i < len(wcs) else (wcs[0] if wcs else "")) or ""
                x = sup[(k, wc)]
                x["names"][w] += 1; x["country"][wc] += 1; x["wins"] += 1; x["usd"] += share
                sec = a.get("sector") or NAME2ID.get(a.get("sector_name", ""), "")
                if sec:
                    x["sectors"][sec] += 1
                    x["goods"] += 1 if sec in GOODS else 0
                for cp in (a.get("cpv") or "").split()[:1]:
                    x["cpv"][cp[:8]] += 1
                x["buyer_c"].add((a.get("country") or "").split(",")[0]); x["buyers"].add(norm(a.get("buyer")))
                p = a.get("published") or ""
                x["last"] = max(x["last"], p); x["first"] = min(x["first"], p or "9999")
                x["sources"].add(a.get("source") or f.parent.name)
                if share >= x["ex_usd"]:
                    x["ex_usd"] = share; x["example"] = f"{a.get('title', '')[:120]} ({a.get('buyer', '')[:60]}, {p})"
    # contacts captured from notices (private cache)
    n_ct = 0
    for f in PRIVATE.glob("contacts_*.jsonl"):
        uniq = {}
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                c = json.loads(line)
            except ValueError:
                continue
            uniq[(c.get("name"), c.get("email"), c.get("phone"), c.get("legal_id"))] = c
        f.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in uniq.values()), encoding="utf-8")
        for c in uniq.values():
            k = (norm(c.get("name")), iso3(c.get("country") or "") or "")
            x = sup.get(k) or next((sup[kk] for kk in ((k[0], ""),) if kk in sup), None)
            if not x:
                continue
            n_ct += 1
            for fld in ("email", "phone", "website", "address", "legal_id"):
                if c.get(fld) and not x[fld]:
                    x[fld] = c[fld]
    out = []
    for (k, wc), x in sup.items():
        name = max(x["names"].items(), key=lambda y: y[1])[0]
        secs = sorted(x["sectors"].items(), key=lambda y: -y[1])
        out.append({
            "supplier": name[:120], "country": wc, "region": region(wc) if wc else "", "tier": "A",
            "wins_24m": x["wins"], "won_usd_est": round(x["usd"]),
            "main_sector": SECTORS.get(secs[0][0], "") if secs else "",
            "other_sectors": "; ".join(SECTORS.get(s, s) for s, _ in secs[1:3]),
            "type": "goods supplier" if x["goods"] >= max(1, x["wins"] / 2) else "works/services",
            "main_cpv": max(x["cpv"].items(), key=lambda y: y[1])[0] if x["cpv"] else "",
            "buyer_countries": " ".join(sorted(c for c in x["buyer_c"] if c))[:80], "buyers": len(x["buyers"]),
            "exports": "yes" if any(c and wc and c != wc for c in x["buyer_c"]) else "",
            "first_win": x["first"] if x["first"] != "9999" else "", "last_win": x["last"],
            "email": x["email"], "phone": x["phone"], "website": x["website"], "address": x["address"],
            "legal_id": x["legal_id"], "sources": "; ".join(sorted(x["sources"])), "example_award": x["example"],
        })
    out.sort(key=lambda r: (-r["won_usd_est"], -r["wins_24m"]))
    PRIVATE.mkdir(parents=True, exist_ok=True)
    cols = list(out[0].keys()) if out else ["supplier"]
    with open(PRIVATE / "universe.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(out)
    stats = {"awards": n_aw, "suppliers": len(out), "with_email": sum(1 for r in out if r["email"]),
             "with_phone": sum(1 for r in out if r["phone"]), "exporters": sum(1 for r in out if r["exports"]),
             "goods": sum(1 for r in out if r["type"] == "goods supplier"), "contacts_matched": n_ct}
    log.info("universe %s", stats)
    (PRIVATE / "universe_stats.json").write_text(json.dumps(stats))
    return out, stats


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    build()
