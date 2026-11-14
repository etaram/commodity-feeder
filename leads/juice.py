"""What the notice does not say: findings that change the bid decision, built from records we already hold.

Each finding is a pattern checked against data (never a model's guess), with the evidence, what it means for Sinder
and how strong it is (1-3). A model is not used here; the wording is fixed text in English and Hebrew.

Detectors (per open tender, top TOP by score):
  incumbent       the same company won most of this buyer's similar contracts (award history, last 36 months)
  low_competition similar awards from this buyer usually had one or two bids
  price_anchor    what this buyer paid for similar contracts (median and range, USD)
  foreign         how often this buyer's contracts went to foreign firms, and from where
  retender        the same buyer published a similar notice before and no award followed
  amended         the notice was corrected or amended
  short_window    less than 12 days between publication and deadline
  funded          run or financed by a development bank or UN agency
  cadence         a frequent buyer: losing this round is not the end
  big_vs_usual    far larger than this buyer's usual contract
  integrity       country-level procurement integrity risk (governance + award records)

Output: data/leads/juice.csv (one row per finding) and, for the panel, a compact "juice" field on each tender row.
"""
import csv
import datetime as dt
import glob
import gzip
import io
import json
import os
import re
import statistics
import time
from collections import Counter, defaultdict

from .common import LEADS, log

TOP = int(os.environ.get("JUICE_TOP", "2500"))
VERSION = "juice-1.0 (2026-11-14)"
STOP = set("""the and for with from that this into works work supply supplies services service purchase procurement
contract tender framework agreement provision delivery lot lots various other including equipment materials
products project construction under year years des les pour avec dans aux sur une del los las para por con
und der die das von für zur zum mit auf eine einer sowie dostawa usługi wykonanie della delle per con nel""".split())
FUNDERS = re.compile(r"world bank|\bida\b|ibrd|afdb|african development|ebrd|european bank for reconstruction|asian development|\badb\b|"
                     r"isdb|islamic development|inter-american|\biadb\b|\bidb\b|\beib\b|european investment bank|undp|unops|unicef|ungm|"
                     r"\bwfp\b|world food programme|\bunhcr\b|\bfao\b|global fund", re.I)
AMEND = re.compile(r"corrig|amend|modif|addend|extension|rectif|berichtig|änderung|sprostowanie|zmiana|aclaraci|enmienda", re.I)


def norm_buyer(b):
    b = re.sub(r"[^\w]+", " ", str(b or "").lower(), flags=re.U).strip()
    return re.sub(r"\s+", " ", b)[:60]


def toks(*texts):
    out = set()
    for t in texts:
        for w in re.findall(r"[^\W\d_]{4,}", str(t or "").lower(), flags=re.U):
            if w not in STOP:
                out.add(w[:9])   # crude stem: the first 9 letters
    return out


def jac(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def fx_rates():
    r = {"USD": 1.0}
    try:
        for x in csv.DictReader(open(LEADS / "fx.csv", encoding="utf-8")):
            if x.get("currency") and x.get("usd_per_unit"):
                r[x["currency"].upper()] = float(x["usd_per_unit"])
    except (OSError, ValueError):
        pass
    return r


def usd(a, rates):
    if a.get("value_usd") not in (None, ""):
        try:
            return float(a["value_usd"])
        except (TypeError, ValueError):
            return None
    try:
        v = float(a.get("value") or 0)
    except (TypeError, ValueError):
        return None
    k = rates.get(str(a.get("currency") or "").upper())
    return v * k if v > 0 and k else None


def load_awards(buyers, since):
    """award rows of the buyers we care about only (the history is several hundred MB of day and month files)"""
    out = defaultdict(list)
    files = glob.glob(str(LEADS / "awards" / "*.json")) + glob.glob(str(LEADS / "awards" / "*" / "*.json")) + glob.glob(str(LEADS / "awards" / "*" / "*.jsonl"))
    seen = 0
    for f in files:
        try:
            if f.endswith(".jsonl"):
                rows = (json.loads(x) for x in open(f, encoding="utf-8") if x.strip())
            else:
                rows = json.load(open(f, encoding="utf-8"))
                if isinstance(rows, dict):
                    rows = rows.get("rows") or rows.get("awards") or []
            for a in rows:
                if not isinstance(a, dict) or a.get("empty"):
                    continue
                seen += 1
                k = norm_buyer(a.get("buyer"))
                if k in buyers and str(a.get("published") or "") >= since:
                    out[k].append(a)
        except (OSError, ValueError):
            continue
    return out, seen


def closed_notices(buyers):
    out = defaultdict(list)
    p = LEADS / "archive" / "tenders_closed.csv.gz"
    try:
        for r in csv.DictReader(io.TextIOWrapper(gzip.open(p), encoding="utf-8")):
            k = norm_buyer(r.get("buyer"))
            if k in buyers:
                out[k].append(r)
    except (OSError, EOFError):
        pass
    return out


def cname(c):
    try:
        import pycountry
        x = pycountry.countries.get(alpha_3=c)
        return getattr(x, "common_name", None) or x.name if x else c
    except Exception:  # noqa: BLE001
        return c


def money(v):
    return f"${v / 1e6:.1f}M" if v >= 1e6 else f"${v / 1e3:.0f}K" if v >= 1e3 else f"${v:.0f}"


def F(kind, strength, en, he, so_en, so_he, evidence=""):
    return {"kind": kind, "strength": strength, "en": en, "he": he, "so_en": so_en, "so_he": so_he, "evidence": evidence}


def detect(t, aw, closed, buyer_row, gov, rates, today):
    out = []
    tt = toks(t.get("title_en"), t.get("title"), t.get("commodity"))
    country = str(t.get("country") or "")[:3].upper()
    sim = []
    for a in aw:
        s = jac(tt, toks(a.get("title"), a.get("cpv_desc")))
        if s >= 0.12:
            sim.append((s, a))
    sim.sort(key=lambda x: str(x[1].get("published") or ""), reverse=True)
    sim = [a for _, a in sim[:40]]
    # incumbent
    wins = Counter()
    for a in sim:
        for w in (a.get("winners") or [])[:3]:
            if isinstance(w, str) and w.strip():
                wins[w.strip()[:80]] += 1
    if wins and len(sim) >= 2:
        w, k = wins.most_common(1)[0]
        if k >= 2 and k / len(sim) >= 0.5:
            last = max(str(a.get("published") or "") for a in sim if w in [str(x)[:80] for x in (a.get("winners") or [])])
            out.append(F("incumbent", 3 if k >= 3 else 2,
                         f"{w} won {k} of this buyer's last {len(sim)} similar contracts (latest {last}).",
                         f"{w} זכה ב-{k} מתוך {len(sim)} החוזים הדומים האחרונים של הקונה הזה (האחרון ב-{last}).",
                         "The spec and the price level are likely set around the incumbent. Options: supply or partner with the incumbent, or ask pre-tender questions that open the spec.",
                         "המפרט ורמת המחיר כנראה נבנו סביב הספק המכהן. אפשרויות: לספק לו או לחבור אליו, או לשאול שאלות הבהרה שפותחות את המפרט.",
                         f"{len(sim)} similar awards"))
    # competition
    bids = [int(a["bids"]) for a in sim if str(a.get("bids") or "").isdigit() and int(a["bids"]) > 0]
    if len(bids) >= 3:
        one = sum(1 for b in bids if b == 1)
        med = statistics.median(bids)
        if med <= 1.5 or one / len(bids) >= 0.5:
            out.append(F("low_competition", 2, f"Little competition: {one} of {len(bids)} similar awards had a single bid (median {med:g} bids).",
                         f"תחרות חלשה: ב-{one} מתוך {len(bids)} חוזים דומים הוגשה הצעה אחת בלבד (חציון {med:g} הצעות).",
                         "A compliant bid has a real chance. Check whether the spec or the requirements keep others out.",
                         "להצעה תקינה יש סיכוי אמיתי. לבדוק אם המפרט או הדרישות מרחיקים מתחרים.", f"{len(bids)} awards with bid counts"))
        elif med >= 6:
            out.append(F("low_competition", 1, f"Crowded: similar awards drew a median of {med:g} bids.", f"צפוף: לחוזים דומים הוגשו בחציון {med:g} הצעות.",
                         "Expect price pressure; bid only with a clear cost edge.", "לצפות ללחץ מחירים; להגיש רק עם יתרון עלות ברור.", f"{len(bids)} awards"))
    # price anchor
    vals = sorted(v for v in (usd(a, rates) for a in sim) if v and v > 500)
    if len(vals) >= 2:
        med = statistics.median(vals)
        est = float(t.get("est_value_usd") or 0)
        q = est / med if est > 0 else 0
        fw = q >= 3
        ratio = (f" The estimate is {q:.1f}x that" + (" (likely several lots or years: check the split)." if fw else ".")) if q else ""
        ratio_he = (f" האומדן גבוה פי {q:.1f} מזה" + (" (כנראה כמה חלקים או שנים: לבדוק את החלוקה)." if fw else ".") if q >= 1 else f" האומדן נמוך מזה ({q:.1f} ממנו).") if q else ""
        wide = vals[-1] / max(vals[0], 1) > 50
        out.append(F("price_anchor", 1 if wide else 2, f"This buyer paid a median {money(med)} for {len(vals)} similar contracts (range {money(vals[0])} to {money(vals[-1])}).{ratio}",
                     f"הקונה הזה שילם בחציון {money(med)} על {len(vals)} חוזים דומים (טווח {money(vals[0])} עד {money(vals[-1])}).{ratio_he}",
                     "Use this as the price anchor; a bid far from it needs a reason.", "זה עוגן המחיר; הצעה רחוקה ממנו צריכה הסבר.", f"{len(vals)} awards with values"))
    # foreign winners (all of this buyer's awards, not only similar)
    wc = [str(a.get("winner_country") or "").upper()[:3] for a in aw if a.get("winner_country")]
    if len(wc) >= 5 and country:
        fo = [c for c in wc if c and c != country]
        share = len(fo) / len(wc)
        if share >= 0.15:
            top = ", ".join(cname(c) for c, _ in Counter(fo).most_common(3))
            out.append(F("foreign", 2, f"Open to foreign firms in practice: {len(fo)} of {len(wc)} of this buyer's awards went abroad ({top}).",
                         f"פתוח לחברות זרות בפועל: {len(fo)} מתוך {len(wc)} החוזים של הקונה הזה הלכו לחו\"ל ({top}).",
                         "A direct bid from abroad is realistic.", "הגשה ישירה מחו\"ל ריאלית.", f"{len(wc)} awards with winner country"))
        elif len(wc) >= 8 and not fo:
            out.append(F("foreign", 2, f"No foreign winner in this buyer's last {len(wc)} awards.", f"אף חברה זרה לא זכתה ב-{len(wc)} החוזים האחרונים של הקונה הזה.",
                         "Plan a local partner or supply a local bidder instead of bidding direct.", "לתכנן שותף מקומי, או לספק למציע מקומי במקום להגיש ישירות.", f"{len(wc)} awards"))
    # re-tender
    for c in closed:
        if c.get("id") == t.get("id"):
            continue
        if jac(tt, toks(c.get("title_en"), c.get("title"))) >= 0.5 and str(c.get("deadline") or "") < str(t.get("deadline") or "") and str(c.get("deadline") or "") >= str(today - dt.timedelta(days=540)):
            after = [a for a in sim if str(a.get("published") or "") >= str(c.get("deadline") or "")]
            if not after:
                out.append(F("retender", 3, f"Published before (deadline {c.get('deadline')}) and no award has been found since.",
                             f"פורסם כבר בעבר (הגשה ב-{c.get('deadline')}) ולא נמצאה זכייה מאז.",
                             "The last round probably failed: price above budget, a spec nobody met, or no bidders. Find out which before pricing.",
                             "הסבב הקודם כנראה נכשל: מחיר מעל התקציב, מפרט שאף אחד לא עמד בו, או שלא היו מציעים. לברר מה מהם לפני שמתמחרים.",
                             c.get("link") or ""))
                break
    # amended
    if AMEND.search(str(t.get("notice_type") or "")):
        out.append(F("amended", 2, "The notice was corrected or amended.", "המכרז תוקן או עודכן.",
                     "Read what changed: a changed spec or a moved deadline often means bidders pushed back.", "לקרוא מה השתנה: מפרט ששונה או מועד שנדחה מעידים לרוב שמציעים התלוננו."))
    # short window
    try:
        days = (dt.date.fromisoformat(str(t.get("deadline"))[:10]) - dt.date.fromisoformat(str(t.get("published"))[:10])).days
        if 0 < days < 12:
            out.append(F("short_window", 2, f"Only {days} days between publication and deadline.", f"רק {days} ימים בין הפרסום למועד ההגשה.",
                         "A short window favours bidders who knew it was coming. Bid only if the documents are ready.", "חלון קצר מיטיב עם מי שידע מראש. להגיש רק אם המסמכים מוכנים."))
    except (TypeError, ValueError):
        pass
    # funder
    if FUNDERS.search(f"{t.get('source', '')} {t.get('buyer', '')} {t.get('access', '')}"):
        out.append(F("funded", 1, "Run or financed by a development bank or UN agency.", "בניהול או במימון של בנק פיתוח או סוכנות של האו\"ם.",
                     "Payment risk is low; the funder's procurement rules and eligibility apply (nationality, sanctions, documents).",
                     "סיכון התשלום נמוך; חלים כללי הרכש והזכאות של המממן (אזרחות, סנקציות, מסמכים)."))
    # cadence and size
    if buyer_row:
        try:
            n12 = int(float(buyer_row.get("awards_12m") or 0))
        except ValueError:
            n12 = 0
        if n12 >= 8:
            out.append(F("cadence", 1, f"Frequent buyer: {n12} awards in the last 12 months{', next expected ' + buyer_row['next_expected'] if buyer_row.get('next_expected') else ''}.",
                         f"קונה תדיר: {n12} זכיות ב-12 החודשים האחרונים{', הבא צפוי ב-' + buyer_row['next_expected'] if buyer_row.get('next_expected') else ''}.",
                         "Register as a supplier with them; this round is one of many.", "להירשם אצלם כספק; הסבב הזה הוא אחד מרבים."))
        try:
            med = float(buyer_row.get("median_award_usd") or 0); est = float(t.get("est_value_usd") or 0)
            if med > 0 and est / med >= 5:
                out.append(F("big_vs_usual", 2, f"About {est / med:.0f}x this buyer's usual contract ({money(med)}).", f"גדול פי {est / med:.0f} בערך מחוזה רגיל של הקונה הזה ({money(med)}).",
                             "Big for them: expect more scrutiny, delays and possibly a split award.", "גדול עבורם: לצפות ליותר בדיקות, עיכובים ואולי חלוקה בין זוכים."))
        except (TypeError, ValueError):
            pass
    g = gov.get(country)
    if g and g.get("flag") in ("high_risk", "caution"):
        try:
            sb = f", {round(100 * float(g.get('single_bid_share') or 0))}% single-bid"
        except ValueError:
            sb = ""
        out.append(F("integrity", 2 if g.get("flag") == "high_risk" else 1, f"{country}: procurement integrity score {g.get('integrity_score')}/100{sb}.",
                     f"{country}: ציון יושרה ברכש {g.get('integrity_score')}/100{sb.replace('single-bid', 'מכרזים עם הצעה אחת')}.",
                     str(g.get("advice") or "")[:220], "לפעול רק בכתב, דרך ערוצים רשמיים, ולתעד כל פנייה.", "governance + award records"))
    out.sort(key=lambda f: -f["strength"])
    return out


def annotate(tenders):
    """adds tender["juice"] (compact JSON, up to 4 findings) to the TOP open tenders by score; writes juice.csv"""
    t0 = time.time()
    today = dt.date.today()
    open_ = [t for t in tenders if t.get("id") and str(t.get("deadline") or "") >= str(today)]
    open_.sort(key=lambda t: -(float(t.get("score") or 0)))
    target = open_[:TOP]
    buyers = {norm_buyer(t.get("buyer")) for t in target if t.get("buyer")}
    since = str(today - dt.timedelta(days=36 * 31))
    aw, seen = load_awards(buyers, since)
    closed = closed_notices(buyers)
    try:
        brows = {norm_buyer(b["buyer"]): b for b in csv.DictReader(open(LEADS / "buyers.csv", encoding="utf-8"))}
    except OSError:
        brows = {}
    try:
        gov = {g["country"]: g for g in csv.DictReader(open(LEADS / "governance.csv", encoding="utf-8"))}
    except OSError:
        gov = {}
    rates = fx_rates()
    rows, kinds, with_any = [], Counter(), 0
    for t in target:
        k = norm_buyer(t.get("buyer"))
        fs = detect(t, aw.get(k, []), closed.get(k, []), brows.get(k), gov, rates, today)
        if fs:
            with_any += 1
            t["juice"] = json.dumps([[f["kind"], f["strength"], f["he"], f["en"], f["so_he"], f["so_en"]] for f in fs[:4]], ensure_ascii=False, separators=(",", ":"))
        for f in fs:
            kinds[f["kind"]] += 1
            rows.append({"id": t["id"], **f})
    with open(LEADS / "juice.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "kind", "strength", "en", "he", "so_en", "so_he", "evidence"])
        w.writeheader(); w.writerows(rows)
    log.info("juice %s: %d of %d top tenders have findings (%s); %d award rows scanned, %d buyers with history, %.0fs",
             VERSION, with_any, len(target), ", ".join(f"{k} {v}" for k, v in kinds.most_common()), seen, len(aw), time.time() - t0)
    return with_any
