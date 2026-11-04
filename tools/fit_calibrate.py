"""Calibrate the deal-fit ranking against the owner's own marks.

Marks come from the panel's "Relevant / Not relevant" buttons (Activity tab, action fit_feedback) and from
pursuits (a tender the owner chose to pursue counts as relevant). The report says, for every rule in the brain,
how often it fired on relevant versus not-relevant notices, and which notices the owner liked that the brain
ranked low (misses) or disliked that it ranked high (false alarms). The constants in leads/dealfit.W are then
changed by hand with this report as the evidence. Needs the service account (run in Actions):
python tools/fit_calibrate.py -> data/probe/fit_calibrate.md
"""
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def marks():
    from leads.push import LEADS_SHEET, Sheets
    sh = Sheets()
    out = {}
    for r in sh.values(LEADS_SHEET, "Activity!A2:G50000"):
        if len(r) > 6 and r[4] == "fit_feedback" and r[5]:
            out[r[5]] = 1 if str(r[6]).startswith("relevant") else 0
    for r in sh.values(LEADS_SHEET, "Pursuits!A2:V600"):
        if r and r[0] and r[0] not in out:
            out[r[0]] = 1
    return out


def main():
    m = marks()
    rows = {r["id"]: r for r in csv.DictReader(open(ROOT / "data/leads/tenders_all.csv", encoding="utf-8"))}
    lab = [(rows[i], v) for i, v in m.items() if i in rows]
    lines = ["# Deal-fit calibration", "", f"Marks: {len(m)} ({sum(m.values())} relevant), {len(lab)} matched to open notices."]
    if len(lab) < 10:
        lines.append("Fewer than 10 marks: not enough to calibrate. Mark more tenders with Relevant / Not relevant in the panel.")
    else:
        sc = lambda r: float(r.get("score") or 0)
        rel = sorted([sc(r) for r, v in lab if v], reverse=True); nrel = sorted([sc(r) for r, v in lab if not v], reverse=True)
        med = lambda a: a[len(a) // 2] if a else float("nan")
        lines += ["", f"Median score of relevant: {med(rel):.0f}; of not relevant: {med(nrel):.0f}. A gap under 15 points means the rules do not separate them yet.", ""]
        fired = defaultdict(lambda: [0, 0])
        for r, v in lab:
            for f in re.split(r";\s*", r.get("fit_flags") or ""):
                if f:
                    fired[f.split(":")[0]][v] += 1
        lines += ["| Penalty rule | on relevant | on not relevant |", "|---|---|---|"]
        for k, (a, b) in sorted(fired.items(), key=lambda y: -(y[1][0] + y[1][1])):
            lines.append(f"| {k} | {b} | {a} |")
        miss = sorted([r for r, v in lab if v and sc(r) < 40], key=sc)[:10]
        fa = sorted([r for r, v in lab if not v and sc(r) >= 60], key=lambda r: -sc(r))[:10]
        lines += ["", "## Relevant but ranked low", *[f"- {sc(r):.0f} {r['country']} {r['title_en'][:80]} | {r.get('fit_flags') or '-'}" for r in miss] or ["- none"],
                  "", "## Not relevant but ranked high", *[f"- {sc(r):.0f} {r['country']} {r['title_en'][:80]} | {r.get('fit_why') or '-'}" for r in fa] or ["- none"]]
    p = ROOT / "data/probe"; p.mkdir(parents=True, exist_ok=True)
    (p / "fit_calibrate.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
