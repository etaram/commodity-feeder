"""Israel: Government Procurement Administration tender search (mr.gov.il), open notices by category."""
import datetime as dt
import html
import re
from urllib.parse import quote

from .common import cffi_get, clean, log, polite, today
from .taxonomy import GROUPS

BASE = "https://mr.gov.il"
ACTIVE = {"פורסם", "חדש", "עודכן", "בעדכון", "עתידי", "Published"}
SERVICE = re.compile(r"שירות|יועצ|ייעוץ|חקיר|בדיק|תחזוק|הדרכ|מחקר|RFI|RFD|הארכת|הרחבת|שוברי|כיבוס")
HE_GROUP = [("DAIRY", r"חלב|גבינ|ביצ|יוגורט|חמא"), ("MEAT", r"בשר|עוף|עופות|הודו|דגים|דג "),
            ("SOFTS", r"קפה|סוכר|תה |קקאו|תבלינ"), ("GRAIN", r"קמח|לחם|אורז|דגנ|חיטה|פסטה|מאפ"),
            ("FRUITVEG", r"פירות|ירקות|פרי|ירק"), ("OILSEED", r"שמן|טחינה|שומשום|חומוס"),
            ("FUEL", r"דלק|סולר|בנזין|גז |גפ\"מ|חמצן"), ("STEEL", r"פלדה|ברזל|מתכת"),
            ("CHEM", r"כימ|כלור|חומצ"), ("WOODPAPER", r"נייר|עץ|קרטון"), ("PLASTIC", r"פלסטיק|גומי|ניילון")]
SUPPLY = re.compile(r"אספק|רכש|רכיש|לאספקת")
FIELD = {"שם המפרסם": "buyer", "מס' פרסום": "pubno", "סטטוס": "status", "מס׳ הליך": "procno",
         "תאריך פרסום": "published", "תאריך עדכון": "updated", "מועד אחרון להגשה": "deadline"}


def _d(s):
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", s or "")
    return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def parse(page):
    out = []
    parts = re.split(r'<a href="/ilgstorefront/he/p/(\d+)">', page)
    for i in range(1, len(parts), 2):
        pid, body = parts[i], parts[i + 1][:6000]
        title = re.search(r"<h2[^>]*>(.*?)</h2>", body, re.S)
        kind = re.search(r'search-result-sub-head">([^<]+)<', parts[i - 1][-800:])
        text = re.sub(r"<[^>]+>", " ", html.unescape(body))
        text = re.sub(r"\s+", " ", text)
        rec = {"pid": pid, "title": clean(html.unescape(title.group(1))) if title else "",
               "kind": clean(kind.group(1)) if kind else ""}
        for lab, key in FIELD.items():
            m = re.search(re.escape(lab) + r":\s*(.*?)(?:\s\|\s|$| (?=[^\s]+ ?[^\s]*:))", text)
            if m:
                rec[key] = clean(m.group(1), 150)
        out.append(rec)
    return out


HE_SECTOR = [("DEFENCE", r"ביטחון|צבא|צה\"ל|משטר|אבטח|נשק|תחמושת"), ("HEALTH", r"רפוא|תרופ|בית חולים|בריאות|מעבד"),
             ("WATER", r"מים|ביוב|שפכים|התפלה"), ("POWER", r"חשמל|שנאי|סולארי|תאורה|גנרטור"),
             ("INFRA", r"כביש|גשר|רכבת|נמל|תשתית|סלילה"), ("ICT", r"מחשב|תוכנ|מערכות מידע|תקשורת|סייבר|ענן|דיגיטל"),
             ("TRANSPORT_EQ", r"רכב|משאית|אוטובוס|כלי טיס|ספינ"), ("MACHINERY", r"ציוד|מכונ|משאב"),
             ("ENERGY", r"דלק|סולר|גז"), ("AGRI_FOOD", r"מזון|חלב|בשר|ירקות|פירות|לחם|קפה|הסעדה"),
             ("TEXTILES", r"מדים|ביגוד|הנעלה|טקסטיל"), ("CONSUMER", r"ריהוט|ריהוט|ציוד משרדי|נייר"),
             ("ENV_WASTE", r"פסולת|ניקיון|אשפה|סביבה"), ("BUILDING", r"בניה|בנייה|שיפוץ|הקמה|עבודות"),
             ("MAINT", r"תחזוק|תיקון|אחזקה"), ("LOGISTICS", r"הובלה|שינוע|אחסנה|נסיעות"),
             ("ENGINEERING", r"תכנון|הנדס|פיקוח"), ("SOCIAL", r"הדרכ|הכשר|חינוך|רווחה|אירוע"),
             ("CONSULTING", r"ייעוץ|יועצ|מחקר|ביקורת|שיווק|פרסום|משפט|ביטוח")]


def _sector(title):
    return next((k for k, rx in HE_SECTOR if re.search(rx, title)), "")


def fetch(max_pages=12):
    rows, seen, t = [], set(), today()
    for kind in ("TENDER", "EXEMPTION"):
        for page in range(max_pages):
            q = quote(":updateDate:archive:false", safe=":")
            url = f"{BASE}/ilgstorefront/he/search/?q={q}&s={kind}&page={page}"
            try:
                r = cffi_get(url)
            except Exception as e:  # noqa: BLE001
                log.warning("mr.gov.il %s: %s", kind, e); break
            items = parse(r.text) if r.status_code == 200 else []
            for it in items:
                st = it.get("status", "").split(" ")[0]
                if it["pid"] in seen or not any(it.get("status", "").startswith(a) for a in ACTIVE):
                    continue
                dl = _d(it.get("deadline"))
                if (dl and dl < t) or (kind == "EXEMPTION" and not dl):
                    continue
                gid = next((k for k, rx in HE_GROUP if re.search(rx, it["title"])), "")
                seen.add(it["pid"])
                rows.append({
                    "id": f"MR-{it['pid']}", "source": "mr.gov.il (Israel)" if kind == "TENDER" else "mr.gov.il exemption notice (Israel)",
                    "group": gid, "sector": _sector(it["title"]), "nature": "", "cpv": "", "stage": "tender",
                    "access": "National (Israeli registration)", "lang": "he",
                    "country": "ISR", "buyer": it.get("buyer", ""), "title": it["title"][:300],
                    "classification": "keyword (he)", "notice_type": f"{it.get('kind', '')} | {st}",
                    "published": str(_d(it.get("published")) or ""), "deadline": str(dl or ""),
                    "value": "", "currency": "", "link": f"{BASE}/ilgstorefront/he/p/{it['pid']}", "contact": "",
                })
            polite(1.5)
            if len(items) < 10:
                break
    log.info("mr.gov.il rows: %d", len(rows))
    return rows, {}
