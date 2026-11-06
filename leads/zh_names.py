"""Chinese company names: the core name a website uses, its pinyin domain candidates, and a name check for pages.

  "湖南华菱钢铁集团有限责任公司" -> cores ["华菱钢铁", "华菱"]: the region prefix and the legal and generic suffixes go,
  because a company's site title and domain use the short name. Domains are tried in pinyin (hualing.com, hualinggt.com,
  hnhl.com.cn ...) and a candidate is accepted only when the page itself shows the Chinese core name, so a guess never
  becomes a website without the page naming the company."""
import re

CJK = re.compile(r"[一-鿿]")
REGIONS = ("北京|上海|天津|重庆|河北|山西|辽宁|吉林|黑龙江|江苏|浙江|安徽|福建|江西|山东|河南|湖北|湖南|广东|海南|四川|贵州|云南|陕西|甘肃|青海|"
           "台湾|内蒙古|广西|西藏|宁夏|新疆|香港|澳门|深圳|广州|杭州|南京|苏州|无锡|常州|宁波|温州|青岛|济南|烟台|潍坊|淄博|大连|沈阳|长春|哈尔滨|"
           "郑州|武汉|长沙|成都|西安|合肥|福州|厦门|泉州|南昌|昆明|贵阳|南宁|石家庄|太原|兰州|乌鲁木齐|东莞|佛山|中山|珠海|惠州|嘉兴|绍兴|台州|金华|"
           "南通|扬州|徐州|镇江|泰州|盐城|常熟|昆山|江阴|张家港|唐山|保定|洛阳|株洲|湘潭|岳阳|宜昌|襄阳|芜湖|绵阳|柳州|桂林|鞍山|包头|呼和浩特")
REGION = re.compile(rf"^(中国)?({REGIONS})(省|市|自治区|特别行政区)?")
LEGAL = re.compile(r"(股份有限公司|有限责任公司|有限公司|集团股份|集团有限|集团|控股|股份|公司|厂|总厂)$")
GENERIC = re.compile(r"(科技|技术|实业|工业|制造|发展|国际|贸易|电子|机械|新材料|材料|化工|生物|医药|环保|能源|智能|装备|设备|电气|电器|自动化|"
                     r"精密|工程|信息|新能源|光电|电力|汽车|食品|纺织|建材|钢铁|有色|金属|塑料|橡胶|化学|制药|药业|健康|网络|软件|数据)$")


def is_cjk(name):
    return bool(CJK.search(name or ""))


def cores(name):
    """Short names a site uses, most specific first (each at least 2 characters)."""
    n = re.sub(r"[\s（）()·.,，]", "", name or "")
    n = re.sub(r"[（(].*?[)）]", "", n)
    out = []
    a = REGION.sub("", n) or n
    prev = None
    while a != prev:
        prev = a
        a = LEGAL.sub("", a)
    if len(a) >= 2:
        out.append(a)
    b = a
    for _ in range(3):  # drop generic industry words from the end: 华菱钢铁 -> 华菱
        c = GENERIC.sub("", b)
        if c == b or len(c) < 2:
            break
        b = c
        out.append(b)
    return list(dict.fromkeys(x for x in out if len(x) >= 2))


def _py(s):
    try:
        from pypinyin import lazy_pinyin
        return [p for p in lazy_pinyin(s) if p.isascii() and p.isalpha()]
    except Exception:  # noqa: BLE001
        return []


def domain_candidates(name):
    """Likely domains for a Chinese company, best first (at most 8)."""
    cs = cores(name)
    if not cs:
        return []
    m = REGION.match(re.sub(r"\s", "", name or ""))
    region = _py(m.group(2)) if m else []
    slugs = []
    for c in cs[::-1]:  # the shortest core first: sites use the short name
        p = _py(c)
        if p:
            slugs.append("".join(p))
            if len(p) >= 3:
                slugs.append("".join(x[0] for x in p))
    if cs:
        p = _py(cs[0])
        if region and p:
            slugs.append("".join(x[0] for x in region) + "".join(x[0] for x in p))
    slugs = [s for s in dict.fromkeys(slugs) if 4 <= len(s) <= 24]
    out = []
    for s in slugs[:3]:
        for tld in ("com", "com.cn", "cn"):
            out.append(f"{s}.{tld}")
    return out[:8]


def page_names(name, title, text):
    """("high" | "partial" | "none", share) for a Chinese name on a page: the full name, or a core name, shown."""
    full = re.sub(r"\s", "", name or "")
    if full and (full in title or full in text):
        return "high", 1.0
    cs = cores(name)
    for i, c in enumerate(cs):
        if c in title or text.count(c) >= 2:
            return ("high" if len(c) >= 3 or i == 0 else "partial"), round(0.9 - 0.2 * i, 2)
    return "none", 0.0
