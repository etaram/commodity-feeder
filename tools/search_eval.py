"""Search evaluation set (brief: 30 labeled Hebrew/English cases against the real indexes).

Mirrors the panel's search rules: Hebrew is translated with the panel's own dictionary (dealdesk/lib/qtranslate.ts;
words not in it are reported as "needs AI translation" and run untranslated, as they would fail without the AI),
words of 2+ letters must each start a word in the record; suppliers: <=3 words all, 4+ words 75% (strict mode).
Each case carries a relevance label: a result counts as relevant when its text matches `rel` and not `bad`.
The labels are the engine builder's, not a human reviewer's: they are a first pass for review, not ground truth.

Run: python tools/search_eval.py   (suppliers need WEB_INDEX_KEY or the service account; tenders work anywhere)
Output: data/probe/search_eval.md and .json
"""
import base64
import gzip
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
K = 10

# (id, scope, query, relevant-if regex, not-relevant-if regex)
CASES = [
    ("T01", "t", "diesel generator", r"generat", r"ozone|steam generator"),
    ("T02", "t", "גנרטור דיזל", r"generat", r"ozone|steam generator"),
    ("T03", "t", "desalination plant", r"desalin", ""),
    ("T04", "t", "מתקן התפלה", r"desalin", ""),
    ("T05", "t", "transformer", r"transformer", r"digital transformation"),
    ("T06", "t", "שנאים", r"transformer", r"digital transformation"),
    ("T07", "t", "solar panels", r"solar|photovolt|\bpv\b", ""),
    ("T08", "t", "פאנלים סולאריים", r"solar|photovolt|\bpv\b", ""),
    ("T09", "t", "medical equipment", r"medic|hospital|clinic|surg|diagnos", ""),
    ("T10", "t", "ציוד רפואי", r"medic|hospital|clinic|surg|diagnos", ""),
    ("T11", "t", "ductile iron pipes", r"pipe", ""),
    ("T12", "t", "צינורות", r"pipe|tub", ""),
    ("T13", "t", "fertilizer urea", r"urea|fertili", ""),
    ("T14", "t", "street lights", r"light|lamp|luminair", ""),
    ("T15", "t", "פנסי רחוב", r"light|lamp|luminair", ""),
    ("T16", "t", "data center", r"data cent|datacent|server", ""),
    ("S01", "s", "diesel generator", r"generat", r"ozone|fuel trad"),
    ("S02", "s", "גנרטור דיזל", r"generat", r"ozone"),
    ("S03", "s", "ductile iron pipes", r"pipe", ""),
    ("S04", "s", "transformers", r"transformer", ""),
    ("S05", "s", "שנאים", r"transformer", ""),
    ("S06", "s", "maize", r"maize|corn|grain|cereal", ""),
    ("S07", "s", "תירס", r"maize|corn|grain|cereal", ""),
    ("S08", "s", "sunflower oil", r"sunflower|vegetable oil|edible oil", ""),
    ("S09", "s", "שמן חמניות", r"sunflower|vegetable oil|edible oil", ""),
    ("S10", "s", "robot vacuum cleaners", r"vacuum|robot|clean", ""),
    ("S11", "s", "שואבי אבק רובוטיים", r"vacuum|robot|clean", ""),
    ("S12", "s", "solar panels", r"solar|photovolt", ""),
    ("S13", "s", "medical equipment", r"medic|hospital|surg|diagnos", ""),
    ("S14", "s", "מוצרי חשמל", r"electric|applianc", ""),
]


def load_dict():
    src = (ROOT / "dealdesk/lib/qtranslate.ts").read_text(encoding="utf-8")
    body = src[src.index("const DICT"):src.index("};", src.index("const DICT"))]
    return dict(re.findall(r'"([^"]+)":\s*"([^"]+)"', body))


HEB = re.compile(r"[֐-׿]")


def translate(q, d):
    k = q.strip().lower()
    if not HEB.search(k):
        return k, "none"
    if k in d:
        return d[k], "dict"
    w = k.split()
    if all(x in d or not HEB.search(x) for x in w):
        return " ".join(d.get(x, x) for x in w), "dict"
    return k, "needs AI translation"


def words(q):  # the panel's stem: a final "s" is dropped so plural and singular match
    w = [x for x in dict.fromkeys(re.split(r"[^\w]+", q.lower())) if len(x) >= 2][:6]
    return [x[:-1] if len(x) > 4 and x.endswith("s") and not x.endswith("ss") else x for x in w]


def hits(text, ws):
    t = text.lower()
    return sum(1 for x in ws if re.search(r"(?:^|[^\w])" + re.escape(x), t))


def tenders():
    return json.load(gzip.open(ROOT / "data/web/tenders.json.gz"))


def suppliers():
    key = os.environ.get("WEB_INDEX_KEY", "")
    if not key:
        try:
            from leads.push import UNIVERSE_SHEET, Sheets
            key = next((r[1] for r in Sheets().values(UNIVERSE_SHEET, "Config!A1:B5") if len(r) > 1 and r[0] == "WEB_INDEX_KEY"), "")
        except (Exception, SystemExit) as e:  # noqa: BLE001
            print("supplier key unavailable:", type(e).__name__)
    if not key:
        return None
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    enc = (ROOT / "data/web/suppliers.enc").read_bytes()
    return json.loads(gzip.decompress(AESGCM(base64.b64decode(key)).decrypt(enc[:12], enc[12:], None)))


def run():
    d = load_dict()
    T, Sx = tenders(), suppliers()
    out = []
    for cid, scope, q, rel, bad in CASES:
        en, how = translate(q, d)
        ws = words(en)
        if scope == "t":
            rows = [(r, f"{r.get('t', '')} {r.get('s', '')}") for r in T]
            need = len(ws)
            key = lambda r: -(r.get("sc") or 0)
        else:
            if Sx is None:
                out.append({"id": cid, "scope": scope, "q": q, "en": en, "how": how, "skipped": "supplier index key not available here"}); continue
            rows = [(r, " ".join(str(r.get(k, "")) for k in ("n", "p", "cm", "lg", "hs", "hd", "in", "wt", "sp"))) for r in Sx]
            need = len(ws) if len(ws) <= 3 else -(-len(ws) * 3 // 4)
            own = lambda r: hits(" ".join(str(r.get(k, "")) for k in ("n", "p", "cm", "lg", "hs", "hd", "in", "wt")), ws)
            key = lambda r: (-own(r), r.get("tr", "9"), -(float(r.get("sh") or 0)), -(float(r.get("w") or 0)))
        m = [(r, txt) for r, txt in rows if ws and hits(txt, ws) >= need]
        m.sort(key=lambda x: key(x[0]))
        top = m[:K]
        good = [bool(re.search(rel, txt, re.I)) and not (bad and re.search(bad, txt, re.I)) for _, txt in top]
        out.append({"id": cid, "scope": scope, "q": q, "en": en, "how": how, "results": len(m), "top": len(top),
                    "p_at_10": round(sum(good) / len(top), 2) if top else None,
                    "sample": [txt[:110] for _, txt in top[:3]],
                    "misses": [txt[:110] for (_, txt), g in zip(top, good) if not g][:3]})
    return out


def report(out):
    scored = [x for x in out if x.get("p_at_10") is not None]
    zero = [x for x in out if x.get("results") == 0]
    lines = ["# Search evaluation (first pass, labels pending human review)", "",
             f"Cases: {len(out)} ({sum(1 for x in out if x['scope'] == 't')} tenders, {sum(1 for x in out if x['scope'] == 's')} suppliers); "
             f"scored: {len(scored)}; skipped: {sum(1 for x in out if x.get('skipped'))}; zero results: {len(zero)}.",
             f"Mean precision@{K}: {sum(x['p_at_10'] for x in scored) / len(scored):.2f}" if scored else "No scored cases.", "",
             "| Case | Query | Searched as | Translation | Results | P@10 | Not relevant in top 10 |", "|---|---|---|---|---|---|---|"]
    for x in out:
        lines.append(f"| {x['id']} | {x['q']} | {x['en']} | {x['how']} | {x.get('results', x.get('skipped', ''))} | "
                     f"{'' if x.get('p_at_10') is None else x['p_at_10']} | {'; '.join(x.get('misses') or [])[:220].replace('|', '/')} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    res = run()
    p = ROOT / "data/probe"
    p.mkdir(parents=True, exist_ok=True)
    (p / "search_eval.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    (p / "search_eval.md").write_text(report(res), encoding="utf-8")
    print(report(res))
