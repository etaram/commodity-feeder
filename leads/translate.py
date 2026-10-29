"""English titles and one-line English summaries for every tender.

Translation runs offline inside the pipeline with Argos Translate (open-source neural MT, no external service, no
quota). Language comes from the source when known, otherwise it is detected with langid. Translations are cached in
data/leads/cache/translations.jsonl so each title is translated once.
"""
import hashlib
import json
import logging
import re
import time

from .common import CACHE

log = logging.getLogger("leads")
for _n in ("argostranslate", "argostranslate.utils", "stanza", "ctranslate2"):
    logging.getLogger(_n).setLevel(logging.WARNING)
P = CACHE / "translations.jsonl"
SUPPORTED = {"ar", "de", "es", "fr", "pt", "uk", "ru", "he", "it", "pl", "nl", "ro", "cs", "tr", "id", "zh", "ja",
             "ko", "el", "hu", "sv", "da", "fi", "bg", "sk", "sl", "lt", "lv", "et", "ca", "ga", "hi", "fa", "az"}
LATIN_EN = re.compile(r"\b(the|and|of|for|supply|services?|works?|construction|procurement|provision|delivery)\b", re.I)


def _key(text):
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def load():
    out = {}
    if P.exists():
        for line in P.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line); out[d["k"]] = d["en"]
    return out


def save(cache):
    CACHE.mkdir(parents=True, exist_ok=True)
    P.write_text("\n".join(json.dumps({"k": k, "en": v}, ensure_ascii=False) for k, v in sorted(cache.items())) + "\n",
                 encoding="utf-8")


def detect(text, hint=""):
    if hint:
        return hint
    if not re.search(r"[A-Za-zÀ-ÿЀ-ۿ֐-׿]", text):
        return "en"
    if re.search(r"[؀-ۿ]", text):
        return "ar"
    if re.search(r"[֐-׿]", text):
        return "he"
    if re.search(r"[Ѐ-ӿ]", text):
        return "uk" if re.search(r"[ієїґ]", text, re.I) else "ru"
    if len(LATIN_EN.findall(text)) >= 2:
        return "en"
    try:
        import langid
        lang, _ = langid.classify(text)
        return lang
    except Exception:  # noqa: BLE001
        return "en"


_models = {}


def _model(lang, to="en"):
    """(ctranslate2.Translator, sentencepiece processor) for lang->to from the Argos package, or None.
    Titles are single short sentences, so they are translated in large batches without sentence splitting."""
    if (lang, to) in _models:
        return _models[(lang, to)]
    m = None
    try:
        import ctranslate2
        import sentencepiece
        import argostranslate.package as pk
        pkg = next((p for p in pk.get_installed_packages() if p.from_code == lang and p.to_code == to), None)
        if not pkg:
            if not getattr(_model, "index", None):
                pk.update_package_index(); _model.index = pk.get_available_packages()
            avail = next((p for p in _model.index if p.from_code == lang and p.to_code == to), None)
            if avail:
                pk.install_from_path(avail.download())
                pkg = next((p for p in pk.get_installed_packages() if p.from_code == lang and p.to_code == to), None)
        if pkg:
            path = pkg.package_path
            spf = next(iter(sorted(path.rglob("*.model"), key=lambda x: ("sentencepiece" not in x.name, len(str(x))))), None) \
                or next(iter(path.rglob("*.spm")), None)
            mb = next(iter(path.rglob("model.bin")), None)
            if not spf or not mb:
                raise FileNotFoundError(f"package layout not recognised in {path}")
            try:
                sp = sentencepiece.SentencePieceProcessor(model_file=str(spf))
                tr = ctranslate2.Translator(str(mb.parent), device="cpu", inter_threads=2, intra_threads=2)
            except Exception:  # noqa: BLE001  newer packages use a BPE tokenizer: let Argos do the whole pipeline
                import argostranslate.translate as at
                m = ("argos", at.get_translation_from_codes(lang, to))
                _models[(lang, to)] = m
                return m
            m = (tr, sp)
    except Exception as e:  # noqa: BLE001
        log.warning("translator %s: %s", lang, e)
    _models[(lang, to)] = m
    return m


REPEAT = re.compile(r"(.{3,15}?)\1{3,}")


def sane(src, out):
    """Machine translation sometimes loops ("mainstremainstremain..."). Reject such output."""
    if not out:
        return False
    if REPEAT.search(out) or len(out) > 2.5 * len(src) + 40:
        return False
    w = out.split()
    return not (len(w) > 8 and len(set(w)) / len(w) < 0.35)


def _translate_batch(lang, texts, to="en"):
    m = _model(lang, to)
    if not m:
        return [""] * len(texts)
    if m[0] == "argos":
        return [m[1].translate(x[:400]) for x in texts]
    tr, sp = m
    toks = sp.encode([t[:400] for t in texts], out_type=str)
    res = tr.translate_batch(toks, beam_size=2, max_batch_size=64, max_decoding_length=160,
                             no_repeat_ngram_size=4, repetition_penalty=1.15)
    return [sp.decode(r.hypotheses[0]).replace("\u2581", " ").strip() for r in res]


def translate_rows(rows, field="title", budget_sec=1500):
    """Adds title_en to each row (in place), highest score first, until the time budget runs out."""
    cache = load(); t0 = time.time(); done = 0
    pending = {}
    for r in rows:
        text = (r.get(field) or "").strip()
        if not text:
            r["title_en"] = ""; continue
        lang = detect(text, r.get("lang") or "")
        r["lang"] = lang if lang != "en" else ""
        if lang == "en" or lang not in SUPPORTED:
            r["title_en"] = text; continue
        k = _key(text)
        if k in cache and sane(text, cache[k]):
            r["title_en"] = cache[k]; continue
        r["title_en"] = ""
        pending.setdefault(lang, []).append((k, text, r))
    for lang, items in sorted(pending.items(), key=lambda x: -len(x[1])):
        for i in range(0, len(items), 256):
            if time.time() - t0 > budget_sec:
                break
            chunk = items[i:i + 256]
            try:
                outs = _translate_batch(lang, [x[1] for x in chunk])
            except Exception as e:  # noqa: BLE001
                log.warning("translate %s: %s", lang, e); break
            for (k, src, r), en in zip(chunk, outs):
                if sane(src, en):
                    cache[k] = en; r["title_en"] = en; done += 1
                else:
                    r["title_en"] = src  # keep the original rather than a broken translation
    save(cache)
    left = sum(1 for items in pending.values() for x in items if not x[2]["title_en"])
    log.info("translations: %d new, %d pending, cache %d, %.0fs", done, left, len(cache), time.time() - t0)


def summary(r, sector_name):
    v = f"est. USD {r['est_value_usd']:,}" if r.get("est_value_usd") not in ("", None) else "value not stated"
    dl = f"closes {r['deadline']}" if r.get("deadline") else ("planned / early notice" if r.get("stage") == "planned" else "no deadline stated")
    t = r.get("title_en") or r.get("title") or ""
    return f"{t[:220]} | Buyer: {r.get('buyer', '')[:80]} ({r.get('country', '')}) | {sector_name} | {v} | {dl}"


PHE = CACHE / "translations_he.jsonl"
HEB = re.compile(r"[\u0590-\u05FF]")


def to_hebrew(rows, limit=6000, budget_sec=900):
    """Hebrew titles for the top `limit` tenders (rows already ranked) and for every Hebrew-language notice.
    English titles are translated offline (Argos en->he); results are cached by text. Returns {id: title_he}."""
    cache = {}
    if PHE.exists():
        for line in PHE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line); cache[d["k"]] = d["he"]
    out, todo, t0 = {}, [], time.time()
    for i, r in enumerate(rows):
        orig = r.get("title") or ""
        if HEB.search(orig):
            out[r["id"]] = orig[:220]; continue
        if i >= limit:
            continue
        en = re.sub(r"^[^–]{2,40} – [^–]{2,80} – ", "", (r.get("title_en") or orig).strip())[:300]  # drop "Country – CPV – "
        if not en:
            continue
        k = _key(en)
        if k in cache and sane(en, cache[k]):
            out[r["id"]] = cache[k]
        else:
            todo.append((r["id"], k, en))
    done = 0
    for i in range(0, len(todo), 256):
        if time.time() - t0 > budget_sec:
            break
        chunk = todo[i:i + 256]
        try:
            res = _translate_batch("en", [x[2] for x in chunk], to="he")
        except Exception as e:  # noqa: BLE001
            log.warning("hebrew titles: %s", e); break
        for (rid, k, src), he in zip(chunk, res):
            if sane(src, he):
                cache[k] = he; out[rid] = he; done += 1
    PHE.write_text("\n".join(json.dumps({"k": k, "he": v}, ensure_ascii=False) for k, v in sorted(cache.items())) + "\n",
                   encoding="utf-8")
    log.info("hebrew titles: %d new, %d total, %d pending, %.0fs", done, len(out), len(todo) - done, time.time() - t0)
    return out
