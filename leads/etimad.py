"""Saudi Arabia: Etimad government tenders (public visitor listing, JSON). Arabic titles; sector from the tender
activity name. Direct purchases are skipped; public and limited competitions are kept."""
import datetime as dt
import re

from .common import cache_empty, clean, log, polite, rolling, session, today

URL = "https://tenders.etimad.sa/Tender/AllSupplierTendersForVisitorAsync"
AR = [
    ("DEFENCE", r"عسكري|أسلحة|ذخيرة|دفاع|أمني|الأمن"), ("HEALTH", r"طبي|طبية|أدوية|صحي|الصحة|مستشفى|مختبرات طبية"),
    ("WATER", r"مياه|صرف صحي|تحلية|سدود"), ("POWER", r"كهرباء|كهربائي|طاقة شمسية|محطات توليد|إنارة"),
    ("INFRA", r"طرق|جسور|أنفاق|سكك|مطار|موانئ"), ("ICT", r"تقنية المعلومات|حاسب|اتصالات|برمجيات|شبكات|أنظمة"),
    ("TRANSPORT_EQ", r"سيارات|مركبات|حافلات|طائرات"), ("MACHINERY", r"معدات|آلات|مضخات|جهاز|أجهزة|مكيف"),
    ("ENERGY", r"وقود|نفط|ديزل|غاز"), ("CHEMICALS", r"كيميائ"), ("TEXTILES", r"ملابس|أقمشة|زي"),
    ("AGRI_FOOD", r"أغذية|مواد غذائية|زراع|أعلاف|لحوم"), ("LAB", r"مختبر|أجهزة قياس"),
    ("CONSUMER", r"أثاث|قرطاسية|مفروشات|أجهزة منزلية"), ("ENV_WASTE", r"نظافة|نفايات|مخلفات|بيئ"),
    ("BUILDING", r"إنشاء|مباني|مقاولات|ترميم|تشييد|بناء"), ("MAINT", r"صيانة|تشغيل"),
    ("LOGISTICS", r"نقل|شحن|تخزين"), ("ENGINEERING", r"هندسية|تصميم|إشراف"), ("SOCIAL", r"إعاشة|تدريب|تعليم|فعاليات"),
    ("CONSULTING", r"استشار|دراسات|تدقيق|تسويق"),
]
_AR = [(s, re.compile(rx)) for s, rx in AR]
SKIP_TYPES = re.compile(r"شراء مباشر")


def _sector(*texts):
    for txt in texts:
        for s, rx in _AR:
            if txt and rx.search(txt):
                return s
    return ""


def _d(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def fetch():
    s, t = session(), today()
    days = 14 if cache_empty("etimad") else 2
    cut, new, page = t - dt.timedelta(days=days), [], 1
    while page <= 150:
        try:
            j = s.get(URL, params={"PageSize": 100, "PageNumber": page}, timeout=60).json()
        except Exception as e:  # noqa: BLE001
            log.warning("Etimad page %d: %s", page, e); break
        batch = j.get("data") or []
        if not batch:
            break
        old = 0
        for n in batch:
            pub = _d(n.get("submitionDate"))
            if pub and pub < cut:
                old += 1; continue
            if SKIP_TYPES.search(n.get("tenderTypeName") or ""):
                continue
            dl = _d(n.get("lastOfferPresentationDate"))
            if dl and dl < t:
                continue
            act = clean(n.get("tenderActivityName"))
            name = clean(n.get("tenderName"))
            new.append({
                "id": f"ETIMAD-{n.get('tenderId')}", "source": "Etimad (Saudi Arabia)", "group": "",
                "sector": _sector(act, name, n.get("agencyName") or ""), "nature": "", "cpv": "", "classification": f"activity {n.get('tenderActivityId')}",
                "country": "SAU", "buyer": clean(f"{n.get('agencyName') or ''} - {n.get('branchName') or ''}", 120),
                "title": clean(f"{name} | {act}", 300), "notice_type": clean(n.get("tenderTypeName")), "stage": "tender",
                "access": "National (local registration; GCC/foreign via local partner)", "published": str(pub or ""),
                "deadline": str(dl or ""), "value": "", "currency": "",
                "link": f"https://tenders.etimad.sa/Tender/DetailsForVisitor?STenderId={n.get('tenderIdString')}",
                "contact": "", "lang": "ar", "booklet_sar": n.get("condetionalBookletPrice") or "",
            })
        if old >= len(batch) * 0.8:
            break
        page += 1
        polite(0.5)
    rows, _ = rolling("etimad", new, max_age_days=60)
    log.info("Etimad new %d, open %d (pages %d)", len(new), len(rows), page)
    return rows, {"new": len(new), "pages": page}
