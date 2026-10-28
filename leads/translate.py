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


def _translator(lang):
    if lang in _models:
        return _models[lang]
    tr = None
    try:
        import argostranslate.utils as au
        au.logger.setLevel(logging.WARNING)
        import argostranslate.package as pk
        import argostranslate.translate as at
        installed = {(p.from_code, p.to_code) for p in pk.get_installed_packages()}
        if (lang, "en") not in installed:
            if not getattr(_translator, "index", None):
                pk.update_package_index(); _translator.index = pk.get_available_packages()
            pkg = next((p for p in _translator.index if p.from_code == lang and p.to_code == "en"), None)
            if pkg:
                pk.install_from_path(pkg.download())
        langs = {lang_.code: lang_ for lang_ in at.get_installed_languages()}
        if lang in langs and "en" in langs:
            tr = langs[lang].get_translation(langs["en"])
    except Exception as e:  # noqa: BLE001
        log.warning("argos %s: %s", lang, e)
    _models[lang] = tr
    return tr


def translate_rows(rows, field="title", budget_sec=1500):
    """Adds title_en to each row (in place). Rows are processed in the given order (highest score first) until the
    time budget runs out; untranslated rows keep the original text."""
    cache = load(); t0 = time.time(); done = skipped = 0
    for r in rows:
        text = (r.get(field) or "").strip()
        if not text:
            r["title_en"] = ""; continue
        lang = detect(text, r.get("lang") or "")
        r["lang"] = lang if lang != "en" else ""
        if lang == "en" or lang not in SUPPORTED:
            r["title_en"] = text; continue
        k = _key(text)
        if k in cache:
            r["title_en"] = cache[k]; continue
        if time.time() - t0 > budget_sec:
            r["title_en"] = ""; skipped += 1; continue
        tr = _translator(lang)
        if not tr:
            r["title_en"] = ""; skipped += 1; continue
        try:
            en = tr.translate(text[:400])
        except Exception:  # noqa: BLE001
            en = ""
        cache[k] = en; r["title_en"] = en; done += 1
    save(cache)
    log.info("translations: %d new, %d pending (budget), cache %d", done, skipped, len(cache))


def summary(r, sector_name):
    v = f"est. USD {r['est_value_usd']:,}" if r.get("est_value_usd") not in ("", None) else "value not stated"
    dl = f"closes {r['deadline']}" if r.get("deadline") else ("planned / early notice" if r.get("stage") == "planned" else "no deadline stated")
    t = r.get("title_en") or r.get("title") or ""
    return f"{t[:220]} | Buyer: {r.get('buyer', '')[:80]} ({r.get('country', '')}) | {sector_name} | {v} | {dl}"
