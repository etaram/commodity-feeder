"""English for what each supplier delivered under public contracts (the "supplied" field), by open-source translation.

Most suppliers have no website on record, so the contract items they won are the only statement of what they do, and
those are in the buyer's language (Ukrainian, Polish, French, Romanian ...): unreadable in the app and not found by an
English search. This layer translates the items of the searchable suppliers (tiers 1-3) with Argos Translate on the
runner, once per distinct text, into a cache keyed by the text's hash (data/describe/supplied_en.json.gz). The index
builder (leads/webindex.py) then shows and searches the English; the original stays in the universe file.

Time-boxed and resumable; the strongest tiers first. Counts only are published.

  python -m leads.describe_supplied --minutes 12
"""
import argparse
import csv
import gzip
import hashlib
import json
import re
import time

from .common import DATA, PRIVATE, log

CACHE = DATA / "describe" / "supplied_en.json.gz"
PROGRESS = DATA / "leads" / "describe_supplied_progress.json"


def key(text):
    return hashlib.sha1(text.strip().lower().encode("utf-8")).hexdigest()[:14]


def items_of(supplied):
    return [i.strip() for i in re.split(r"\s*;\s*", supplied or "") if len(i.strip()) >= 4][:3]


def load():
    if CACHE.exists():
        try:
            return json.loads(gzip.open(CACHE, "rt", encoding="utf-8").read())
        except (OSError, ValueError):
            pass
    return {}


def english(supplied, cache):
    """The field with every translated item in English (untranslated items stay as they are)."""
    return "; ".join(cache.get(key(i)) or i for i in items_of(supplied))


def main(minutes=12.0):
    from .translate import _translate_batch, detect, sane
    src = PRIVATE / "universe.csv"
    if not src.exists():
        log.warning("describe supplied: %s missing", src); return
    cache, t0, budget = load(), time.time(), minutes * 60
    todo, total, have = {}, 0, 0   # lang -> {key: (tier, text)}
    csv.field_size_limit(10 ** 9)
    for r in csv.DictReader(open(src, encoding="utf-8")):
        if r.get("tier") not in ("1", "2", "3"):
            continue
        for it in items_of(r.get("supplied", "")):
            total += 1
            k = key(it)
            if k in cache:
                have += 1; continue
            lang = detect(it[:200])
            if lang == "en":
                cache[k] = ""   # already English: nothing to add
                have += 1; continue
            todo.setdefault(lang, {}).setdefault(k, (r["tier"], it))
    done, nomodel = 0, []
    for lang, rows in sorted(todo.items(), key=lambda x: -len(x[1])):
        batch = sorted(rows.items(), key=lambda x: x[1][0])   # tier 1 first
        for b in range(0, len(batch), 64):
            if time.time() - t0 > budget:
                break
            chunk = batch[b:b + 64]
            try:
                res = _translate_batch(lang, [t for _, (_, t) in chunk])
            except Exception as e:  # noqa: BLE001
                log.warning("describe supplied: %s: %s", lang, str(e)[:120]); break
            if not any(res):
                nomodel.append(lang); break
            for (k, (_, srctext)), en in zip(chunk, res):
                cache[k] = en.strip()[:240] if en and sane(srctext, en) else ""
                done += 1
        if time.time() - t0 > budget:
            break
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(CACHE, "wt", encoding="utf-8") as f:
        f.write(json.dumps(cache, ensure_ascii=False, separators=(",", ":")))
    left = sum(1 for rows in todo.values() for k in rows if k not in cache)
    rep = {"at": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), "contract_items_in_index": total, "already_handled": have, "translated_now": done,
           "left": left, "with_english": sum(1 for v in cache.values() if v), "languages_waiting": {k: len(v) for k, v in sorted(todo.items(), key=lambda x: -len(x[1]))[:10]},
           "no_model_for": nomodel[:10], "seconds": round(time.time() - t0)}
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print("describe supplied:", json.dumps(rep))


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    ap = argparse.ArgumentParser(); ap.add_argument("--minutes", type=float, default=12)
    main(ap.parse_args().minutes)
