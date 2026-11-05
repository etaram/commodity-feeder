"""Opportunity hypotheses from project timelines (spec phase 4). Code only, no model.

Reads data/leads/project_timelines.csv and data/leads/events.csv (written by leads.events) and writes
data/leads/hypotheses.csv. Every row is a HYPOTHESIS, never a recommendation:
  - status "research candidate": a plausible commercial mechanism with gaps (no live tender yet);
  - status "actionable": the same, but a current open tender exists on the project (its id is given).
Each row states the commercial mechanism, the likely procurement package, evidence-backed actors (from records only),
a timing range with its basis, alternative explanations, counter-evidence, missing information and the next
validation action. World intelligence without a deal stays in events.csv; it is not forced into a hypothesis.
Rules (one primary rule per project, picked by the timeline's state):
  tender_open        open tender on a project with financing / plan / lender record      -> actionable
  financed_no_tender financing approved, no tender and no goods/works award yet          -> expected package
  plan_no_tender     procurement plan / GPN published, no open tender                    -> first tender expected
  pipeline           lender project in preparation, board date ahead                     -> shape before the plan
  supply_winner      big recent goods/works award in a focus market                      -> sub-supply to the winner
  news_unconfirmed   project / EPC / financing news with no official record linked        -> find the record first
Run after leads.events: python -m leads.hypotheses
"""
import csv
import datetime as dt
import hashlib
import json
import re
from collections import Counter, defaultdict
from statistics import quantiles

from .common import LEADS, log, today
from .dealfit import EMERGING
from .regions import region

csv.field_size_limit(10_000_000)
COLS = ["hyp_id", "status", "label", "rule", "project_key", "project_ref", "project_name", "project_country", "region", "buyer", "sector",
        "value_usd", "stage", "mechanism", "likely_package", "actors", "timing_from", "timing_to", "timing_basis", "evidence",
        "alternatives", "counter_evidence", "missing_info", "next_action", "confidence", "tender_id", "tender_deadline", "tender_link",
        "link", "created", "updated"]
PACKAGE = {
    "Power & electrical equipment": "transformers, switchgear, cables and conductors, meters; substation, mini-grid, solar or BESS supply-and-install lots",
    "Energy, fuels & utilities": "fuel supply, LPG or gas equipment, utility network materials and metering",
    "Healthcare & pharmaceuticals": "medical and laboratory equipment, cold-chain, hospital furniture and consumables lots",
    "ICT & telecom": "network and data-center equipment, end-user devices, software and integration lots",
    "Water & wastewater": "pipes, pumps, valves, meters and treatment-plant equipment; network works lots",
    "Transport & civil infrastructure works": "civil works lots; bitumen, cement, steel and road or rail equipment for the contractors",
    "Building construction works": "building works lots; construction materials and MEP equipment for the contractors",
    "Agriculture & food": "irrigation equipment, storage and processing equipment, agri inputs",
    "Industrial & construction machinery": "machinery and spare-parts supply lots",
    "Vehicles, rolling stock, ships & aircraft": "vehicles, rolling stock or vessels and their spares",
    "Scientific & measuring instruments": "instruments, laboratory and monitoring equipment",
    "Defence & security": "security equipment and systems (check end-user and export rules)",
    "Consulting, business & financial services": "mostly consultancy services; little goods supply expected",
    "Education": "school furniture, ICT and teaching equipment",
}
SOFT = re.compile(r"consult|financial services|social|education|governance|public administration", re.I)
DPF = re.compile(r"\b(dpf|dpo|development policy|budget support|policy-based|cat ddo|pforr|program-for-results|programme for results)\b", re.I)
CONSULT = re.compile(r"\b(consult\w*|supervision|technical assistance|audit\w*|stud(y|ies)|individual|expression of interest|capacity building|"
                     r"training|survey|evaluation|assessment|advisory|recrutement|consultor\w*|consultoria)\b", re.I)
DEFAULT_LAG = (90, 365)  # days from approval to the first goods/works notice when the data give too few cases


def num(v):
    try:
        f = float(str(v).replace(",", ""))
        return f if f == f else 0.0
    except (TypeError, ValueError):
        return 0.0


def _rows(name):
    p = LEADS / name
    return list(csv.DictReader(open(p, encoding="utf-8"))) if p.exists() else []


def _date(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def lag_window(timelines):
    """Empirical approval -> first notice lag (p25..p75 days) from timelines that have both dates."""
    lags = []
    for x in timelines:
        a, b = _date(x.get("financing_date")), _date(x.get("first_tender_date") or x.get("plan_date"))
        if a and b and 0 < (b - a).days < 1100:
            lags.append((b - a).days)
    if len(lags) >= 8:
        q = quantiles(lags, n=4)
        return (int(q[0]), int(q[2])), f"empirical p25-p75 of approval -> first plan/notice over {len(lags)} projects in this data (recent approvals only, so biased short)"
    return DEFAULT_LAG, f"default 3-12 months (only {len(lags)} projects with both dates in the data)"


def past_winners(wb_awards, t):
    """country -> top goods/works winners in World Bank awards of the last 24 months (record evidence)."""
    cut = str(t - dt.timedelta(days=730))
    c = defaultdict(Counter)
    for a in wb_awards:
        if a.get("category") in ("Goods", "Works") and (a.get("signed") or "") >= cut and a.get("country"):
            c[a["country"]][f"{a.get('supplier', '')[:50]} ({a.get('supplier_country', '') or '?'})"] += 1
    return {k: [w for w, _ in v.most_common(3)] for k, v in c.items()}


def build(write=True):
    t = today()
    ts = str(t)
    tls = _rows("project_timelines.csv")
    evs = _rows("events.csv")
    by_id = {e["event_id"]: e for e in evs}
    tenders = {e["tender_id"]: e for e in evs if e.get("tender_id") and e["type"] in ("tender_publication", "tender_amendment")}
    (lo, hi), lag_basis = lag_window(tls)
    winners = past_winners(_rows("wb_awards.csv"), t)
    prev = {h["hyp_id"]: h for h in _rows("hypotheses.csv")}
    gw_awards = defaultdict(list)  # project -> goods/works award events (consultancy awards do not buy materials)
    for e in evs:
        if e["type"] == "award" and e.get("project_key") and not re.search(r"consult", e.get("tags", ""), re.I):
            gw_awards[e["project_key"]].append(e)
    out = []

    def add(rule, x, **kw):
        hid = "hy-" + hashlib.sha1(f"{rule}|{x.get('project_key') or kw.get('evidence', '')}".encode()).hexdigest()[:12]
        # actionable = a live goods/works notice; a consultancy-only notice is a research candidate (it buys no goods)
        status = "actionable" if kw.get("tender_id") and not kw.pop("consultancy_only", False) else "research candidate"
        kw.pop("consultancy_only", None)
        h = {c: "" for c in COLS}
        h.update(hyp_id=hid, status=status, label=f"HYPOTHESIS ({status})", rule=rule, project_key=x.get("project_key", ""),
                 project_ref=x.get("project_ref", ""), project_name=x.get("name", "")[:160], project_country=x.get("project_country", ""),
                 region=region(x.get("project_country", "")) if x.get("project_country") else "", buyer=x.get("buyer", "")[:120],
                 sector=x.get("sector", ""), value_usd=x.get("value_usd", ""), stage=x.get("stage", ""), link=x.get("link", ""),
                 created=(prev.get(hid) or {}).get("created") or ts, updated=ts)
        h.update(kw)
        out.append(h)

    for x in tls:
        if x.get("stage") == "dropped" or x.get("status") in ("dropped", "closed"):
            continue
        name, sector, c = x.get("name", ""), x.get("sector", ""), x.get("project_country", "")
        reg = region(c) if c else ""
        val = num(x.get("value_usd"))
        open_ids = [i for i in (x.get("open_tender_ids") or "").split(";") if i]
        fin, plan, board = x.get("financing_date", ""), x.get("plan_date", ""), x.get("board_date", "")
        gw = int(num(x.get("goods_works_awards")))
        lender = x["project_key"].split(":")[0] in ("WB", "WBN", "AIIB", "IDB", "AFDB", "ISDB")
        package = PACKAGE.get(sector, f"goods and works lots in {sector or 'the project sector'} (unspecified until the plan is read)")
        actors = [f"buyer / implementing agency: {x['buyer']} (record)"] if x.get("buyer") else []
        if x.get("top_winners"):
            actors.append(f"winners on this project: {x['top_winners']} (award records)")
        if winners.get(c):
            actors.append(f"recent World Bank goods/works winners in {c}: {'; '.join(winners[c])} (award records; competitors or partners)")
        counter, alts, missing = [], [], []
        if DPF.search(name):
            counter.append("budget-support or results-based instrument: often no international goods packages")
        if SOFT.search(sector or ""):
            counter.append("sector is mainly services; goods share may be small")
        if not val:
            missing.append("project value")
        conf = "medium" if (lender and val >= 2e7 and not counter) else "low"
        ev_ids = [m.get("e") for m in json.loads(x.get("milestones") or "[]")][-6:]
        evidence = "; ".join(f"{(by_id.get(i) or {}).get('type', '')} {(by_id.get(i) or {}).get('event_date', '')} [{i}]" for i in ev_ids if i)

        if open_ids and (fin or plan or lender):
            cands = [tenders[i] for i in open_ids if tenders.get(i)]
            best = min(cands, key=lambda e: (bool(CONSULT.search(e["title"])), e.get("tender_deadline") or "9999"), default=None)
            if not best:
                continue
            consultancy_only = bool(CONSULT.search(best["title"]))
            if consultancy_only:
                counter.append("the open notice is consultancy or supervision, not goods/works")
                conf = "low"
            elif conf == "low" and not counter:
                conf = "medium"  # a live goods/works notice is direct evidence of a package, whatever the project size
            add("tender_open", x, mechanism="bid directly or as the supplier / sub-supplier to a bidder on a live notice of a financed project",
                likely_package=best["title"][:200], actors=" | ".join(actors), timing_from=ts, timing_to=best.get("tender_deadline") or "",
                timing_basis="the notice's own deadline" if best.get("tender_deadline") else "no deadline stated on the notice",
                evidence=evidence, alternatives="the lot may be reserved for national bidders or already prequalified; read the access rules",
                counter_evidence="; ".join(counter), missing_info="; ".join(missing + ["eligibility and local-content rules", "bid security and payment terms",
                                                                                      "whether Asian-sourced goods meet the origin rules"]),
                next_action=f"Open notice {best['tender_id']}, read eligibility and the BoQ, then line up two supplier quotes before the deadline.",
                confidence=conf, tender_id=best["tender_id"], tender_deadline=best.get("tender_deadline", ""), tender_link=best.get("url", ""),
                consultancy_only=consultancy_only)
            continue
        if fin and not open_ids and gw == 0:
            a = _date(fin)
            if not a or (t - a).days > 540:
                continue
            f_, to_ = max(a + dt.timedelta(days=lo), t), max(a + dt.timedelta(days=hi), t + dt.timedelta(days=30))
            if not plan:
                missing.append("procurement plan (STEP) with the package list and dates")
            add("financed_no_tender", x, mechanism="financing is approved, so the implementing agency will tender goods/works packages; supply them or partner a bidder",
                likely_package=package, actors=" | ".join(actors), timing_from=str(f_), timing_to=str(to_), timing_basis=lag_basis,
                evidence=evidence, alternatives="funds may go to consultancy, grants or national-competition lots; packages may slip past the window",
                counter_evidence="; ".join(counter), missing_info="; ".join(missing + ["package sizes and procurement methods (ICB vs national)"]),
                next_action="Read the project's procurement tab or STEP plan on the lender site; if none, ask the PIU for the GPN date and goods lines.",
                confidence=conf)
            continue
        if plan and not open_ids:
            a = _date(plan)
            if not a or (t - a).days > 365:
                continue
            add("plan_no_tender", x, mechanism="a procurement plan or general notice lists the packages; the first specific notices follow",
                likely_package=package + " (confirm against the plan's lines)", actors=" | ".join(actors), timing_from=str(max(a + dt.timedelta(days=30), t)),
                timing_to=str(max(a + dt.timedelta(days=270), t + dt.timedelta(days=60))), timing_basis="typical 1-9 months from plan to the first notice (rule of thumb, not measured)",
                evidence=evidence, alternatives="the plan may hold only consultancy or small shopping lots",
                counter_evidence="; ".join(counter), missing_info="; ".join(missing + ["which plan lines are goods/works and their estimated amounts"]),
                next_action="Open the plan document, list the goods/works lines above $1M with their planned dates, and set a watch on the buyer.",
                confidence=conf)
            continue
        if x.get("status") == "pipeline" and val >= 2e7:
            b = _date(board)
            if b and b < t - dt.timedelta(days=30):
                continue
            base = b or t
            add("pipeline", x, mechanism="the project is in preparation; packages and specs are being shaped before the board date",
                likely_package=package, actors=" | ".join(actors), timing_from=str(max(base + dt.timedelta(days=lo), t)), timing_to=str(base + dt.timedelta(days=hi + 90)),
                timing_basis=f"board date {board or 'unknown'} + approval-to-notice lag ({lag_basis})", evidence=evidence,
                alternatives="the project can be dropped, resized or restructured before approval",
                counter_evidence="; ".join(counter), missing_info="; ".join(missing + ["board approval", "procurement plan", "component split"]),
                next_action="Read the project information document (PID) for the components; watch for approval and the GPN.",
                confidence="low")
            continue
        gwa = [e for e in gw_awards.get(x["project_key"], []) if (_date(e["event_date"]) or t) >= t - dt.timedelta(days=180)]
        if x.get("stage") == "awarded" and reg in EMERGING and gwa and sum(num(e["value_usd"]) for e in gwa) >= 5e6:
            last = max(_date(e["event_date"]) for e in gwa)
            wn = Counter(w.strip()[:60] for e in gwa for w in (e.get("supplier") or "").split(";")[:3] if w.strip())
            actors = [a_ for a_ in actors if not a_.startswith("winners on this project")]
            actors.insert(0, f"goods/works winners on this project (last 180 days): {'; '.join(w for w, _ in wn.most_common(3))} (award records)")
            add("supply_winner", x, mechanism="the contractor now buys inputs; offer them sourcing for the largest material or equipment lines",
                likely_package=package, actors=" | ".join(actors), timing_from=str(last), timing_to=str(last + dt.timedelta(days=240)),
                timing_basis="rule of thumb: contractors place most orders in the first 8 months after signing", evidence=evidence,
                alternatives="the winner may self-supply or hold group framework suppliers", counter_evidence="; ".join(counter),
                missing_info="; ".join(missing + ["the winner's bill of materials and its current suppliers"]),
                next_action="Read the award notice, name the input bought most, and get two supplier quotes before contacting the winner.",
                confidence="low")

    # news signals that no official record confirms yet
    for e in evs:
        if e.get("origin") != "news" or e.get("project_key") or e["type"] not in ("epc_selection", "construction_start", "financing_approval", "award", "project_announcement"):
            continue
        c = e.get("project_country", "")
        if region(c) not in EMERGING if c else True:
            continue
        if e["type"] == "project_announcement" and num(e.get("value_usd")) < 5e7:
            continue
        x = {"project_key": "", "name": e["title"], "project_country": c, "buyer": "", "sector": e.get("sector", ""), "value_usd": e.get("value_usd", ""),
             "stage": e["type"], "link": e.get("url", "")}
        add("news_unconfirmed", x, mechanism="a reported project step that may open packages; unconfirmed until an official record is found",
            likely_package=PACKAGE.get(e.get("sector", ""), "unknown until the project record is found"),
            actors=f"named in the report: {e['actors']} (news, not verified)" if e.get("actors") else "",
            timing_from=e["event_date"], timing_to=str(_date(e["event_date"]) + dt.timedelta(days=365)) if _date(e["event_date"]) else "",
            timing_basis="unknown: no record; one year window", evidence=f"{e['type']} {e['event_date']} [{e['event_id']}]; {e.get('verified', '')}",
            alternatives="headline may overstate (MoU or intent, not a contract); may be a republished older story",
            counter_evidence="" if int(num(e.get("independent_sources"))) >= 2 else "single source",
            missing_info="official record; buyer; value; package list", next_action="Find the buyer's or lender's official notice; until then keep it as world intelligence.",
            confidence="low")

    rank = {"actionable": 0, "research candidate": 1}
    out.sort(key=lambda h: (rank[h["status"]], h["confidence"] != "medium", -num(h["value_usd"])))
    if write:
        with open(LEADS / "hypotheses.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(out)
    stats = {"hypotheses": len(out), "by_status": dict(Counter(h["status"] for h in out)), "by_rule": dict(Counter(h["rule"] for h in out)),
             "by_confidence": dict(Counter(h["confidence"] for h in out)), "lag": [lo, hi], "lag_basis": lag_basis}
    log.info("hypotheses: %s", json.dumps(stats))
    return out, stats


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(build()[1], indent=1))
