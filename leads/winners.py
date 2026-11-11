"""Fresh contract winners as sales leads: who just won a public contract, what they now have to buy to deliver it,
and what Sinder can offer them (project 4: selling to the winner instead of bidding).

Input, all public award records already collected by the engine:
  data/private/awards_ext/*.jsonl   World Bank financed contracts, USAspending, open-contracting publishers
  data/leads/awards/*.json          TED and national portals (monthly files)
Output: data/web/winners.enc (encrypted like the supplier index: the award facts are public, the reading of what to
sell to whom is ours) and a short count in the log. Only awards signed in the last WINDOW days are kept.

Two kinds of lead:
  commodity   the contract is itself a supply of a commodity we trade (rice, wheat, fertiliser, fuel...): the winner
              has to source it now, so we offer supply or back-to-back cover
  contractor  a works contract: the contractor needs materials and equipment (cement, steel, pipes, cables...); the
              needs are inferred from the contract title by plain rules and are a hypothesis until the contractor
              confirms them, never a fact
"""
import base64
import datetime as dt
import glob
import gzip
import json
import os
import re

from .common import DATA, LEADS, PRIVATE, log

OUT = DATA / "web"
WINDOW = 150   # days back from today
KEEP = 8000

# what a works contract makes the contractor buy; first matching rules win, several may apply
NEEDS = [
    (r"bridge|pont\b|puente|viaduct|flyover", ["structural steel", "steel rebar", "cement", "bearings and expansion joints", "prestressing strand"]),
    (r"\broads?\b|highway|pavement|asphalt|carriageway|\broute\b|bitumage|carretera|estrada|rodovia|voirie", ["bitumen", "cement", "steel rebar", "aggregates", "guardrails", "road marking paint"]),
    (r"water supply|water treatment|pipeline|sewer|sewage|sanitation|wastewater|drainage|adduction|eau potable|agua potable|saneamiento|borehole", ["HDPE and ductile iron pipes", "valves and fittings", "pumps", "water treatment chemicals", "water meters"]),
    (r"irrigation|canal|dam\b|barrage|riego|irrigac", ["pipes", "pumps", "gates and valves", "cement", "geomembrane"]),
    (r"transmission line|substation|distribution network|electrification|grid|power line|poste|sous-station|subestaci|kv\b|electrica", ["conductors and power cables", "transformers", "steel towers and poles", "insulators", "switchgear"]),
    (r"solar|photovolta|pv plant|mini.?grid", ["solar modules", "inverters", "batteries", "mounting structures", "DC and AC cables"]),
    (r"hospital|clinic|health cent|centre de sant|school|classroom|escuela|ecole|école|dormitor|housing|building|construction of|edificio|batiment|bâtiment|rehabilitation of", ["cement", "steel rebar", "roofing sheets", "tiles and sanitary ware", "electrical cables", "doors and windows"]),
    (r"railway|rail\b|track|ferrovi", ["rails", "sleepers", "ballast", "signalling cable"]),
    (r"\bports?\b|jetty|quay|harbour|harbor|dredg", ["sheet piles", "structural steel", "cement", "fenders and bollards"]),
    (r"airport|\brunways?\b(?! and| ,)|air terminal", ["bitumen", "cement", "airfield lighting", "structural steel"]),
    (r"fibre|fiber|optic|telecom|broadband", ["fibre optic cable", "ducts and accessories", "network equipment"]),
    (r"storage|warehouse|silo|cold chain|market infrastructure", ["steel structures", "silos", "cold room panels", "cement"]),
]
# supply contracts for goods we trade: label -> words in the contract title (several languages)
COMMODITY = [
    ("rice", r"\brice\b|\briz\b|arroz"), ("wheat and flour", r"\bwheat\b|\bbl[ée]\b|\btrigo\b|\bflour\b|\bfarine\b|\bharina\b"), ("maize", r"maize|\bcorn\b|ma[ií]z|ma[ïi]s"),
    ("sugar", r"\bsugar\b|\bsucre\b|\baz[uú]car\b"), ("vegetable oil", r"vegetable oil|cooking oil|palm oil|sunflower oil|huile v[ée]g|aceite"),
    ("pulses", r"beans|lentil|pulses|chickpea|haricot|frijol|legumin"), ("milk powder", r"milk powder|powdered milk|lait en poudre|leche en polvo"),
    ("food supply", r"food (items|commodit|suppl|ration|basket)|foodstuff|denr[ée]es|\bvivres\b|\balimentos\b|food aid|school feeding|fruit, vegetables|cereals|meat\b|dairy products"),
    ("fertiliser", r"fertili[sz]er|engrais|fertilizante|\burea\b|\bnpk\b|\bdap\b"), ("seeds", r"\bseeds?\b|semences|semillas"),
    ("fuel", r"\bdiesel\b|\bgas ?oils?\b|\bpetrol\b|petroleum|gasoline|\bfuels?\b|carburant|combustibles?\b|lubricant|lubricating|jet a-?1"), ("bitumen", r"bitumen|bitume|asphalt binder"),
    ("cement", r"\bcement\b|\bciment\b|\bcemento\b"), ("steel", r"steel (bars|pipes|sheets|products)|rebar|reinforcement bars|fer [àa] b[ée]ton|acero"),
    ("coal", r"\bcoal\b|\bhouille\b|carb[oó]n mineral"), ("cotton and textiles", r"\bcotton\b|coton|algod[oó]n|uniforms|blankets|textile"),
    ("salt and chemicals", r"\bsalt\b|chlorine|sulphates?\b|\balum\b|caustic soda|chemicals for water|activated carbon"),
    ("pipes", r"\bpipes?\b|tuyaux|tuber[ií]a"), ("cables", r"\bcables?\b|conductors?\b"), ("transformers", r"transformers?|transformateur"),
    ("solar equipment", r"solar (panel|module|home|lantern|pump|street)|photovolta"), ("vehicles", r"\bvehicles?\b|\btrucks?\b|\bambulances?\b|\bmotorcycles?\b|\btractors?\b"),
    ("medical supplies", r"medical (equipment|supplies|consumables)|pharmaceutical|medicines|drugs\b|m[ée]dicaments|laboratory (equipment|reagent)"),
]
SERVICES = re.compile(r"consult|supervis|audit|study|studies|design of|training|technical assistance|advisory|assessment|survey|[ée]tude|asistencia t[ée]cnica|software|licen[cs]e|insurance", re.I)


def _rows():
    for f in sorted((PRIVATE / "awards_ext").glob("*.jsonl")):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue
    for f in sorted(glob.glob(str(LEADS / "awards" / "*.json")))[-6:]:
        try:
            for r in json.load(open(f, encoding="utf-8")):
                yield r
        except (ValueError, OSError):
            continue


def read(title, nature=""):
    """(kind, needs, commodity) for one award title."""
    t = (title or "").lower()
    parts = [x.strip() for x in re.split(r" [–-] ", t)]
    head = parts[1] if len(parts) >= 3 else ""   # TED notices: "Country – classification – title"; the classification is the reliable part
    goods = [lab for lab, pat in COMMODITY if head and re.search(pat, head)] or [lab for lab, pat in COMMODITY if re.search(pat, t)]
    works = []
    for pat, items in NEEDS:
        if re.search(pat, t):
            works += [i for i in items if i not in works]
    if not goods and re.search(r"supply (and|&) (installation|delivery)|supply of|equipment|fourniture|suministro|adquisici", t):
        return "", [], ""   # an equipment supply we cannot name is not a materials lead
    is_works = "work" in (nature or "").lower() or bool(works) and not goods
    if goods and not is_works:
        return "commodity", goods[:4], goods[0]
    if works and (is_works or not goods):
        return "contractor", works[:7], ""
    if goods:
        return "commodity", goods[:4], goods[0]
    return "", [], ""


def _fx():
    import csv
    try:
        rows = list(csv.DictReader(open(LEADS / "fx.csv", encoding="utf-8")))
        k = [c for c in rows[0] if c.lower() in ("currency", "code", "cur")][0]
        v = [c for c in rows[0] if "usd" in c.lower() or c.lower() in ("rate", "per_usd")][0]
        return {r[k].upper(): float(r[v]) for r in rows if r.get(v)}, v.lower()
    except Exception:  # noqa: BLE001
        return {}, ""


def build():
    fx, fx_col = _fx()
    since = (dt.date.today() - dt.timedelta(days=WINDOW)).isoformat()
    today = dt.date.today().isoformat()
    out, seen, n_all = [], set(), 0
    for r in _rows():
        n_all += 1
        d = (r.get("published") or "")[:10]
        if not (since <= d <= today):
            continue
        title = r.get("title") or ""
        winners = r.get("winners") or []
        if isinstance(winners, str):
            winners = [w.strip() for w in winners.split(";") if w.strip()]
        if not winners or not title or SERVICES.search(title):
            continue
        kind, needs, commodity = read(title, r.get("nature") or r.get("sector") or "")
        if not kind:
            continue
        try:
            cur, val = (r.get("currency") or "USD").upper(), float(r.get("value") or 0)
            usd = float(r.get("value_usd") or 0) or (val if cur == "USD" else 0)
            if not usd and val and fx.get(cur):
                usd = val * fx[cur] if fx_col == "usd_per_unit" else val / fx[cur]   # fx.csv holds USD per one unit of the currency
        except (TypeError, ValueError):
            usd = 0
        if usd and usd < 100_000 or usd > 5e9:   # tiny orders are not worth a call; absurd totals are framework ceilings
            continue
        key = (winners[0].lower()[:60], title.lower()[:80])
        if key in seen:
            continue
        seen.add(key)
        age = (dt.date.today() - dt.date.fromisoformat(d)).days
        # fresher is better (the contractor buys in the first months), then size, then a foreign winner (imports anyway)
        score = max(0, 60 - age * 0.4) + min(25, (usd or 0) ** 0.5 / 400) + (10 if (r.get("winner_country") or "") not in ("", r.get("country") or "") else 0) + (5 if kind == "contractor" else 0) + (15 if "World Bank" in (r.get("source") or "") or "bank" in (r.get("source") or "").lower() else 0)
        out.append({"d": d, "w": winners[:4], "wc": (r.get("winner_country") or "")[:20], "c": (r.get("country") or "")[:3], "b": (r.get("buyer") or "")[:120], "t": title[:220],
                    "v": round(usd), "k": kind, "n": needs, "cm": commodity, "s": (r.get("source") or ("TED" if r.get("pn") else ""))[:40], "l": (r.get("link") or (f"https://ted.europa.eu/en/notice/-/detail/{r['pn']}" if r.get("pn") else ""))[:200], "e": (r.get("email") or "")[:80], "id": str(r.get("id") or "")[:60], "sc": round(score, 1)})
    out.sort(key=lambda x: -x["sc"])
    per, capped = {}, []
    for x in out:
        cap = 2500 if "World Bank" in x["s"] else 350
        per[x["s"]] = per.get(x["s"], 0) + 1
        if per[x["s"]] <= cap:
            capped.append(x)
    out = capped[:KEEP]
    kinds = {}
    for x in out:
        kinds[x["k"]] = kinds.get(x["k"], 0) + 1
    srcs = {}
    for x in out:
        srcs[x["s"]] = srcs.get(x["s"], 0) + 1
    log.info("winners: %d award rows read, %d leads kept since %s: %s; sources %s", n_all, len(out), since, json.dumps(kinds), json.dumps(dict(sorted(srcs.items(), key=lambda kv: -kv[1])[:8])))
    for x in out[:12]:
        log.info("winners top: %s | %s (%s) -> %s | %s | USD %s | needs: %s", x["d"], x["w"][0][:40], x["wc"], x["c"], x["t"][:70], f"{x['v']:,}", ", ".join(x["n"][:4]))
    return out


def main():
    out = build()
    key = os.environ.get("WEB_INDEX_KEY", "")
    if not key:
        try:
            from .push import UNIVERSE_SHEET, Sheets
            key = next((r[1] for r in Sheets().values(UNIVERSE_SHEET, "Config!A1:B5") if len(r) > 1 and r[0] == "WEB_INDEX_KEY"), "")
        except Exception as e:  # noqa: BLE001
            log.warning("winners key from sheet: %s", e)
    if not key:
        log.warning("winners: WEB_INDEX_KEY not set - nothing written"); return
    try:
        from .winner_dossier import enrich
        enrich(out, key)
    except Exception as e:  # noqa: BLE001
        log.warning("winner dossier skipped: %s", e)
    if not out:
        log.warning("winners: no leads - previous file kept"); return
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = gzip.compress(json.dumps({"at": dt.date.today().isoformat(), "window_days": WINDOW, "rows": out}, ensure_ascii=False, separators=(",", ":")).encode(), 9)
    nonce = os.urandom(12)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "winners.enc").write_bytes(nonce + AESGCM(base64.b64decode(key)).encrypt(nonce, raw, None))
    log.info("winners: %d leads, %.2f MB encrypted", len(out), (OUT / "winners.enc").stat().st_size / 1e6)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    main()
