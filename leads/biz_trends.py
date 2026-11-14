"""Business trends: what China's financial press and the big Chinese platforms are pushing right now, filtered to
business and trade, for the Today panel (owner, 14 Nov 2026: a trends module from TrendRadar with a business and
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
TAG_RX = [(n, re.compile(p, re.I)) for n, p in TAGS]
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


def fetch_trends():
    s, t = session(), str(today())
    items, meta = collect(s)
    if not items:
        log.warning("trends: nothing read (%s)", meta)
        return 0
    hist = {}
    try:
        hist = json.loads(HIST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    now = time.strftime("%Y-%m-%d %H:%M", time.gmtime())
    spread = {}
    for x in items:
        spread.setdefault(_norm(x["title"])[:14], set()).add(x["platform_id"])
    rows, seen = [], set()
    for x in items:
        k = _norm(x["title"])
        if k in seen:
            continue
        seen.add(k)
        h = hist.get(k) or {"first": now, "runs": 0}
        h["runs"] += 1; h["last"] = now
        hist[k] = h
        sp = len(spread.get(k[:14], ()))
        score = (3 if x["tags"] else 0) + len(x["tags"]) + min(h["runs"], 6) + 2 * (sp - 1) + max(0, 10 - x["rank"]) / 3 + (2 if x["world"] else 0)
        rows.append({**x, "tags": ", ".join(x["tags"]), "first_seen": h["first"], "runs": h["runs"], "spread": sp,
                     "score": round(score, 1), "lang": "zh", "id": "BT-" + k[:24]})
    # forget stories not seen for 3 days
    cut = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 3 * 86400))
    hist = {k: v for k, v in hist.items() if v.get("last", "") >= cut}
    HIST.parent.mkdir(parents=True, exist_ok=True)
    HIST.write_text(json.dumps(hist, ensure_ascii=False), encoding="utf-8")
    rows.sort(key=lambda r: -r["score"])
    rows = rows[:250]
    try:
        from .translate import to_hebrew, translate_rows
        translate_rows(rows, field="title", budget_sec=300)
        he = to_hebrew(rows, limit=250, budget_sec=240)
        for r in rows:
            r["title_he"] = he.get(r["id"], "")
    except Exception as e:  # noqa: BLE001
        log.warning("trends translation: %s", e)
    for r in rows:
        sec, _ = classify(r.get("title_en") or r["title"])
        r["sector"] = SECTORS.get(sec, "") if sec else ""
    cols = ["score", "platform", "rank", "tags", "sector", "world", "title_en", "title_he", "title", "url", "first_seen", "runs", "spread"]
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
