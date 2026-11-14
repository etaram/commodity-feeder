"""Business trends worldwide: what China's financial press and big platforms are pushing, plus each major country's
trending searches with their news headline (Google Trends daily RSS, 40 countries), all filtered to business and trade, for the Today panel (owner, 14 Nov 2026: a trends module from TrendRadar with a business and
commercial focus).

Source: the hot lists TrendRadar itself reads, through the open-source newsnow API (github.com/ourongxing/newsnow, MIT;
public instance newsnow.busiyi.world/api/s?id=<platform>): titles, rank and link only. Read once per run, one call per
platform. Financial wires (CLS, Wallstreetcn, Gelonghui, Jin10, Xueqiu) are kept whole; general platforms (Weibo,
Baidu, Toutiao, Zhihu, Douyin, Bilibili, The Paper) keep only items that hit the business vocabulary below, and
entertainment is dropped. Each item gets business tags (commodities, energy, projects and tenders, trade and
sanctions, shipping, policy and macro, companies and markets), a Sinder sector, and an English title (offline
translation) and Hebrew title. Momentum = how many consecutive runs the item has stayed on a list; spread = how many
platforms carry the same story. Output: data/leads/biz_trends.csv (pushed to the 'Biz Trends' tab). Signals, not facts: every
row links to its source; nothing here is verified."""
import csv
import math
import json
import re
import time

from .common import CACHE, LEADS, clean, log, session, today
from .sectors import SECTORS, classify

API = "https://newsnow.busiyi.world/api/s"
PLATFORMS = [  # id, label, business wire (kept whole)
    ("cls-hot", "CLS (财联社) hot", True), ("cls-telegraph", "CLS telegraph", True),
    ("wallstreetcn-hot", "Wallstreetcn hot", True), ("wallstreetcn-quick", "Wallstreetcn live", True),
    ("gelonghui", "Gelonghui", True), ("jin10", "Jin10", True), ("xueqiu-hotstock", "Xueqiu hot stocks", True),
    ("36kr-quick", "36Kr", True), ("toutiao", "Toutiao", False), ("baidu", "Baidu hot search", False),
    ("weibo", "Weibo", False), ("zhihu", "Zhihu", False), ("thepaper", "The Paper", False),
    ("douyin", "Douyin", False), ("bilibili-hot-search", "Bilibili", False),
]
TAGS = [
    ("commodities", r"铜|铝|锌|镍|锂|钴|钢|铁矿|煤|焦炭|黄金|白银|稀土|大豆|玉米|小麦|大米|糖|棉|化肥|尿素|钾|水泥|橡胶|原材料|大宗|copper|alumin|lithium|steel|iron ore|coal|gold|urea|fertili|grain|wheat|soy"),
    ("energy", r"石油|原油|天然气|LNG|电力|电网|储能|光伏|风电|核电|氢能|新能源|充电|电池|OPEC|oil|gas|power|solar|wind|nuclear|battery|grid"),
    ("projects & tenders", r"招标|中标|采购|项目|工程|基建|铁路|高铁|公路|桥|港口建设|机场|水利|签约|合同|订单|一带一路|EPC|tender|contract|project|infrastructure"),
    ("trade & sanctions", r"出口|进口|关税|贸易|制裁|反倾销|管制|禁令|配额|WTO|自贸|tariff|export|import|sanction|trade war"),
    ("shipping & logistics", r"航运|海运|运费|集装箱|港口|红海|苏伊士|巴拿马|物流|船|freight|shipping|container|port"),
    ("policy & macro", r"央行|利率|降准|降息|汇率|人民币|美元|美联储|PPI|CPI|GDP|PMI|财政|国务院|发改委|商务部|工信部|政策|方案|规划|补贴|专项债|stimulus|central bank|rate|inflation"),
    ("companies & markets", r"并购|收购|IPO|上市|融资|增持|减持|股价|涨停|跌停|市值|财报|业绩|营收|利润|产能|扩产|停产|减产|复产|涨价|降价|价格|短缺|供应|merger|acquisition|earnings|shortage|price"),
]
EN_EXTRA = {
    "commodities": r"|\b(?:silver|nickel|zinc|cocoa|coffee|corn|maize|rice|sugar|cotton|palm oil|cement|rubber|commodit\w*|grain|food prices?)\b",
    "energy": r"|\b(?:electricity|fuel|petrol|diesel|blackout|load.?shedding|refinery|pipeline|energy|opec|crude)\b",
    "projects & tenders": r"|\b(?:construction|railway|highway|airport|bridge|dam|metro|megaproject|procurement|bid|awarded|investment deal)\b",
    "trade & sanctions": r"|\b(?:customs|duties|embargo|trade deal|free trade|quota|dumping)\b",
    "shipping & logistics": r"|\b(?:logistics|cargo|vessel|suez|red sea|panama canal|strike at port|supply chain)\b",
    "policy & macro": r"|\b(?:interest rates?|inflation|budget|tax|imf|world bank|recession|economy|gdp|currency|dollar|euro|devaluation|minister of finance)\b",
    "companies & markets": r"|\b(?:stock|shares|market|ipo|merger|layoffs?|bankrupt\w*|profit|revenue|ceo|takeover|prices?|shortage)\b",
}
TAGS = [(n, p + EN_EXTRA.get(n, "")) for n, p in TAGS]
TAG_RX = [(n, re.compile(p, re.I)) for n, p in TAGS]
SPORT = re.compile(r"\b(vs\.?|match|league|cup|goal|score|fc|united|real madrid|barcelona|nba|nfl|cricket|ipl|tennis|f1|grand prix|film|movie|series|actor|actress|singer|album|concert|wedding|dies|death|weather|horoscope|lottery)\b", re.I)
TRENDS_RSS = "https://trends.google.com/trending/rss"
GEOS = ["US", "CA", "MX", "BR", "AR", "CL", "CO", "PE", "GB", "DE", "FR", "IT", "ES", "PL", "NL", "TR", "IL", "SA", "AE", "EG", "MA", "NG",
        "KE", "ZA", "GH", "IN", "PK", "ID", "VN", "TH", "MY", "PH", "SG", "JP", "KR", "TW", "HK", "AU", "KZ", "UA",
        # added 14 Nov 2026 (owner: more countries): Gulf, Africa, Europe, South Asia; a country Google does not serve just logs a failure
        "QA", "KW", "OM", "BH", "JO", "DZ", "TN", "ET", "TZ", "UG", "SN", "CI", "CM", "AO", "BD", "LK", "NZ",
        "PT", "BE", "SE", "CH", "AT", "IE", "DK", "NO", "FI", "CZ", "RO", "HU", "GR", "VE", "EC", "DO", "GT"]
NOISE = re.compile(r"明星|综艺|电影|电视剧|演唱会|恋情|离婚|塌房|网红|偶像|球赛|进球|游戏|动漫|八卦|官宣恋|结婚|热舞|颜值|cp")
WORLD = re.compile(r"非洲|中东|沙特|阿联酋|以色列|伊朗|印度|东南亚|越南|印尼|巴西|墨西哥|俄罗斯|乌克兰|欧盟|欧洲|美国|日本|韩国|土耳其|埃及|尼日利亚|南非|肯尼亚|埃塞俄比亚|巴基斯坦|哈萨克")
HIST = CACHE / "biz_trends_history.json"


def _norm(s):
    return re.sub(r"[\W_]+", "", s.lower())[:40]


def collect(s):
    items, meta = [], {}
    for pid, label, wire in PLATFORMS:
        try:
            r = s.get(API, params={"id": pid}, timeout=30, headers={"Accept": "application/json"})
            r.raise_for_status()
            got = (r.json() or {}).get("items") or []
        except Exception as e:  # noqa: BLE001
            meta[pid] = "failed"; log.warning("trends %s: %s", pid, str(e)[:80]); continue
        kept = 0
        for rank, x in enumerate(got[:50], 1):
            title = clean(str(x.get("title") or ""))
            if len(title) < 6 or NOISE.search(title):
                continue
            tags = [n for n, rx in TAG_RX if rx.search(title)]
            if not wire and not tags:
                continue
            items.append({"platform": label, "platform_id": pid, "rank": rank, "title": title, "url": x.get("url") or x.get("mobileUrl") or "",
                          "tags": tags, "world": ",".join(sorted(set(WORLD.findall(title))))})
            kept += 1
        meta[pid] = kept
        time.sleep(1)
    return items, meta


def collect_global(s):
    """Google Trends daily trending searches per country (official RSS; robots.txt allows it): the search and the
    news headline attached to it. Kept only when the English translation hits the business vocabulary."""
    import xml.etree.ElementTree as ET
    ns = {"ht": "https://trends.google.com/trending/rss"}
    items, meta = [], {}
    for g in GEOS:
        try:
            r = s.get(TRENDS_RSS, params={"geo": g}, timeout=30)
            r.raise_for_status()
            root = ET.fromstring(r.content)
        except Exception as e:  # noqa: BLE001
            meta["gt-" + g] = "failed"; log.warning("trends rss %s: %s", g, str(e)[:60]); continue
        n = 0
        for rank, it in enumerate(root.iter("item"), 1):
            term = clean(it.findtext("title") or "")
            news = it.find("ht:news_item", ns)
            head = clean((news.findtext("ht:news_item_title", default="", namespaces=ns) if news is not None else "") or "")
            url = (news.findtext("ht:news_item_url", default="", namespaces=ns) if news is not None else "") or ""
            traffic = clean(it.findtext("ht:approx_traffic", default="", namespaces=ns) or "")
            tn = re.sub(r"[^\d]", "", traffic.replace("K", "000").replace("M", "000000"))
            if term:
                items.append({"platform": f"Google Trends {g}", "platform_id": "gt-" + g, "rank": rank, "title": f"{term}: {head}" if head else term,
                              "url": url, "tags": [], "world": g, "geo": g, "term": term, "traffic": traffic, "traffic_n": int(tn) if tn else 0, "_global": True})
                n += 1
        meta["gt-" + g] = n
        time.sleep(1)
    return items, meta


CURATE_MODEL = "claude-haiku-5-5"   # the web app's cheapest model (dealdesk/lib/anthropic.ts)


def curate(rows, top=140):
    """One small model call per refresh (owner, 14 Nov 2026: the module must help understand what is happening): keeps
    only items that matter for business, trade, markets or the economy, rewrites each title in clean English and
    Hebrew, adds one line on why it matters for a cross-border trading firm, and fixes the theme tags. Uses only the
    item text given; nothing is added. Without ANTHROPIC_API_KEY the machine-translated rows are kept as they are."""
    import os
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key or not rows:
        return rows, False
    cn = [r for r in rows if not str(r.get("platform", "")).startswith("Google Trends")][:90]
    per, gl = {}, []
    for r in rows:
        if str(r.get("platform", "")).startswith("Google Trends"):
            g = r.get("platform")[-2:]
            if per.get(g, 0) < 5:
                per[g] = per.get(g, 0) + 1; gl.append(r)
    cand = cn + gl
    items = [{"id": r["id"], "source": r["platform"], "country": r.get("world", ""), "text": r["title"][:220],
              "machine_en": (r.get("title_en") or "")[:220]} for r in cand]
    tags = [n for n, _ in TAGS]
    prompt = ("You curate a business trends feed for Sinder, an Israeli cross-border sourcing and trading firm (commodities, "
              "infrastructure, energy, defence and health equipment; suppliers in China, India, Turkey; buyers in Africa, the Gulf, Asia, "
              "Latin America). Below are trending items from Chinese financial wires and hot lists and from Google trending searches in "
              "many countries, each with its original text and a rough machine translation.\n"
              "For EACH item return one JSON object: {\"id\", \"keep\": true only if it is about business, trade, markets, prices, the "
              "economy, companies, projects, energy, commodities, shipping, sanctions or economic policy (not sport, entertainment, "
              "crime, celebrities, weather, lotteries or generic tech gossip), \"title_en\": a clear English headline, \"title_he\": the "
              "same headline in natural Hebrew, \"why_en\" and \"why_he\": one short line on why it matters for a trading firm "
              "(empty if nothing concrete), \"tags\": a subset of " + json.dumps(tags) + "}. Use only what the item says; do not add "
              "facts, numbers or names. No emojis, no em-dashes. Return ONLY a JSON array.\n\nItems:\n" + json.dumps(items, ensure_ascii=False))
    import requests
    tool = {"name": "curated", "description": "The curated items", "input_schema": {"type": "object", "properties": {"items": {"type": "array", "items": {
        "type": "object", "properties": {"id": {"type": "string"}, "keep": {"type": "boolean"}, "title_en": {"type": "string"}, "title_he": {"type": "string"},
                                         "why_en": {"type": "string"}, "why_he": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}},
        "required": ["id", "keep"]}}}, "required": ["items"]}}
    arr = []
    for i in range(0, len(items), 35):   # batches keep each answer small and complete
        part = prompt.replace(json.dumps(items, ensure_ascii=False), json.dumps(items[i:i + 35], ensure_ascii=False)).replace("Return ONLY a JSON array.", "Answer with the curated tool.")
        try:
            r = requests.post("https://api.anthropic.com/v1/messages", timeout=180,
                              headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                              json={"model": os.environ.get("BIZ_TRENDS_MODEL", CURATE_MODEL), "max_tokens": 8000, "tools": [tool],
                                    "tool_choice": {"type": "tool", "name": "curated"}, "messages": [{"role": "user", "content": part}]})
            r.raise_for_status()
            arr += next((b.get("input", {}) for b in r.json().get("content", []) if b.get("type") == "tool_use"), {}).get("items", [])
        except Exception as e:  # noqa: BLE001
            log.warning("trends curation batch %d failed: %s", i // 35, str(e)[:160])
    if not arr:
        log.warning("trends curation failed, machine translations kept")
        return rows, False
    by = {a.get("id"): a for a in arr if isinstance(a, dict)}
    out = []
    for r in cand:
        a = by.get(r["id"])
        if not a or not a.get("keep"):
            continue
        r = dict(r)
        r["title_en"] = (a.get("title_en") or r.get("title_en") or "")[:220]
        r["title_he"] = (a.get("title_he") or "")[:220]
        r["why_en"], r["why_he"] = (a.get("why_en") or "")[:200], (a.get("why_he") or "")[:200]
        t = [x for x in (a.get("tags") or []) if x in tags]
        if t:
            r["tags"] = ", ".join(t)
        r["score"] = round(float(r["score"]) + (2 if r["why_en"] else 0), 1)
        out.append(r)
    log.info("trends curation: %d of %d kept", len(out), len(cand))
    return sorted(out, key=lambda x: -x["score"]), True


def fetch_trends():
    s, t = session(), str(today())
    items, meta = collect(s)
    gl, gmeta = collect_global(s)
    meta.update(gmeta)
    if gl:
        try:
            from .translate import translate_rows
            translate_rows(gl, field="title", budget_sec=300)
        except Exception as e:  # noqa: BLE001
            log.warning("trends global translation: %s", e)
        per = {}
        for x in sorted(gl, key=lambda x: x["rank"]):
            en = x.get("title_en") or x["title"]
            x["tags"] = [n for n, rx in TAG_RX if rx.search(en)]
            if SPORT.search(en) or per.get(x["geo"], 0) >= 8:
                continue
            per[x["geo"]] = per.get(x["geo"], 0) + 1
            items.append(x)   # the curator decides what is business; the regex alone kept only 5 countries (14 Nov)
    if not items:
        log.warning("trends: nothing read (%s)", meta)
        return 0
    hist = {}
    try:
        hist = json.loads(HIST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    now = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
    spread, geos = {}, {}
    for x in items:
        spread.setdefault(_norm(x["title"])[:14], set()).add(x["platform_id"])
        if x.get("term"):
            geos.setdefault(_norm(x["term"]), set()).add(x["geo"])
    rows, seen = [], set()
    for x in items:
        k = _norm(x["title"])
        if k in seen:
            continue
        seen.add(k)
        h = hist.get(k) or {"first": now, "runs": 0}
        h["runs"] += 1; h["last"] = now
        hist[k] = h
        sp = max(len(spread.get(k[:14], ())), len(geos.get(_norm(x.get("term", "")), ())) if x.get("term") else 0)
        if x.get("term"):
            x["spread_geo"] = " ".join(sorted(geos.get(_norm(x["term"]), ())))
        tn = x.get("traffic_n") or 0
        score = (3 if x["tags"] else 0) + len(x["tags"]) + min(h["runs"], 6) + 2 * (sp - 1) + max(0, 10 - x["rank"]) / 3 + (2 if x["world"] else 0) + (math.log10(tn) - 2 if tn >= 100 else 0)
        # strength 0-100 (owner, 14 Nov: show how strong a trend is): position on its list, how long it has stayed,
        # how many countries or platforms carry it, and for Google searches the approximate search volume
        P = max(0.0, 1 - (x["rank"] - 1) / 25); R = min(h["runs"], 6) / 6; S = min(sp - 1, 4) / 4
        V = min(1.0, max(0.0, (math.log10(tn) - 2) / 4)) if tn else 0.45
        x["strength"] = round(100 * (0.3 * P + 0.25 * R + 0.25 * V + 0.2 * S))
        if x.get("_global"):
            try:
                import pycountry
                x["world"] = pycountry.countries.get(alpha_2=x["world"]).name
            except Exception:  # noqa: BLE001
                pass
        rows.append({**{k: v for k, v in x.items() if k != "_global"}, "tags": ", ".join(x["tags"]), "first_seen": h["first"], "runs": h["runs"], "spread": sp,
                     "score": round(score, 1), "lang": "" if x.get("platform_id", "").startswith("gt-") else "zh", "id": "BT-" + k[:24]})
    # forget stories not seen for 3 days
    cut = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 3 * 86400))
    hist = {k: v for k, v in hist.items() if v.get("last", "") >= cut}
    HIST.parent.mkdir(parents=True, exist_ok=True)
    HIST.write_text(json.dumps(hist, ensure_ascii=False), encoding="utf-8")
    rows.sort(key=lambda r: -r["score"])
    rows = rows[:650]   # up to 8 searches from each of ~74 countries plus the Chinese lists
    try:
        from .translate import to_hebrew, translate_rows
        translate_rows([r for r in rows if not r.get("title_en")], field="title", budget_sec=300)
        he = to_hebrew(rows, limit=250, budget_sec=240)
        for r in rows:
            r["title_he"] = he.get(r["id"], "")
    except Exception as e:  # noqa: BLE001
        log.warning("trends translation: %s", e)
    rows = [r for r in rows if "\u2047" not in (r.get("title_en") or "") and "\u2047" not in (r.get("title_he") or "")]   # "⁇": failed translation
    rows, curated = curate(rows)
    if not curated:
        rows = [r for r in rows if not r.get("platform", "").startswith("Google Trends") or len([t for t in r.get("tags", "").split(", ") if t]) >= 1]
    for r in rows:
        sec, _ = classify(r.get("title_en") or r["title"])
        r["sector"] = SECTORS.get(sec, "") if sec else ""
    cols = ["score", "platform", "rank", "tags", "sector", "world", "title_en", "title_he", "why_en", "why_he", "title", "url", "first_seen", "runs", "spread",
            "strength", "traffic", "traffic_n", "spread_geo"]
    with open(LEADS / "biz_trends.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    log.info("Business trends: %d items from %d platforms (%s); %s, as of %s", len(rows), sum(1 for v in meta.values() if v != "failed"),
             ", ".join(f"{k} {v}" for k, v in meta.items()), t, now)
    return len(rows)


def build():
    """Called from the merge step of leads.run with the other signals."""
    return fetch_trends()


if __name__ == "__main__":
    fetch_trends()
