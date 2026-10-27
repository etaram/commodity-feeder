"""Market signals for the BD agent: which countries import a commodity, how fast imports grow, and what unit
price they pay versus the tracker benchmark. Source: UN Comtrade public preview API (annual, no key).
Rotates through SIGNAL_HS (PER_RUN codes per run); cache in data/leads/markets/<hs6>.json."""
import datetime as dt
import json

from .common import LEADS, log, polite, session, today

PREVIEW = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
REPORTERS = "https://comtradeapi.un.org/files/v1/app/reference/Reporters.json"
CACHE = LEADS / "markets"
PER_RUN = 8
REFRESH_DAYS = 30
SIGNAL_HS = {
    "MEAT": ["020230", "020714"], "FISH": ["030617", "030487"], "DAIRY": ["040221", "040510"],
    "FRUITVEG": ["070310", "080131"], "GRAIN": ["100630", "100199", "110100"],
    "OILSEED": ["120740", "151190", "151211"], "SOFTS": ["090111", "170199", "090411"], "FEED": ["230400"],
    "BEVTOB": ["240120"], "FUEL": ["271019", "270112", "271320"], "MINERAL": ["252329", "250100"],
    "CHEM": ["281512", "280700", "290511"], "FERT": ["310210", "310530"], "PLASTIC": ["390110", "390410", "400122"],
    "WOODPAPER": ["440711", "470321"], "TEXTILE": ["520100", "520512"], "STEEL": ["720839", "721420", "720449"],
    "NONFERROUS": ["740311", "760110"], "PRECIOUS": ["710812"],
}


def _years():
    y = today().year
    return [y - 2, y - 1] if today().month >= 9 else [y - 3, y - 2]


def _get(s, hs, year):
    r = s.get(PREVIEW, params={"cmdCode": hs, "flowCode": "M", "period": year, "partnerCode": 0,
                               "customsCode": "C00", "motCode": 0}, timeout=90)
    if r.status_code != 200:
        log.warning("comtrade %s %s: %s", hs, year, r.status_code); return None
    out = {}
    for d in r.json().get("data", []):
        if d.get("partnerCode") not in (0, None):
            continue
        out[str(d["reporterCode"])] = {"v": d.get("primaryValue") or 0, "kg": d.get("netWgt") or 0}
    return out


def fetch():
    CACHE.mkdir(parents=True, exist_ok=True)
    s = session(); t = today()
    try:
        names = {str(r["id"]): r["text"] for r in s.get(REPORTERS, timeout=60).json().get("results", [])}
        (CACHE / "_reporters.json").write_text(json.dumps(names, ensure_ascii=False))
    except Exception as e:  # noqa: BLE001
        log.warning("reporters: %s", e)
    codes = [(g, h) for g, hs in SIGNAL_HS.items() for h in hs]
    def age(h):
        f = CACHE / f"{h}.json"
        return json.loads(f.read_text()).get("fetched", "") if f.exists() else ""
    due = [c for c in codes if not age(c[1]) or (t - dt.date.fromisoformat(age(c[1]))).days >= REFRESH_DAYS]
    due.sort(key=lambda c: age(c[1]))
    done = 0
    for g, h in due[:PER_RUN]:
        y0, y1 = _years()
        a = _get(s, h, y0); polite(1.5)
        b = _get(s, h, y1); polite(1.5)
        if a is None or b is None:
            continue
        (CACHE / f"{h}.json").write_text(json.dumps({"hs6": h, "group": g, "years": [y0, y1], "prev": a, "last": b,
                                                     "fetched": str(t)}))
        done += 1
    log.info("market signals: %d codes refreshed, %d due", done, len(due))
    return [], {"refreshed": done, "due": len(due)}
