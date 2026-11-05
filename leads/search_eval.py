"""Writes the supplier-search benchmark (dealdesk/tools/eval-suppliers.ts output) to the private Supplier Universe
sheet, tab 'Search eval', next to the baseline run, and keeps the human labels already entered there.

  python -m leads.search_eval eval_new.json [eval_base.json]

Label column: 'yes' = can supply this requirement, 'no' = cannot, 'related' = related product or role, blank = not
reviewed. Supported precision@5/@10 is computed only from reviewed rows, with the number reviewed shown, so a
number never hides how small its sample is. Labels are human: the matcher never grades itself.
"""
import json
import sys
from collections import defaultdict

from .push import UNIVERSE_SHEET, Sheets

TAB = "Search eval"


def main(new_path, base_path=None):
    new = json.load(open(new_path))
    base = json.load(open(base_path)) if base_path else []
    s = Sheets()
    labels = {}
    try:
        old = s.values(UNIVERSE_SHEET, f"'{TAB}'!A1:Q3000")
        h = next((i for i, r in enumerate(old) if r[:2] == ["query", "rank"]), None)
        if h is not None:
            hd = old[h]
            for r in old[h + 1:]:
                r = r + [""] * len(hd)
                if r[hd.index("label")]:
                    labels[(r[0], r[hd.index("supplier")])] = r[hd.index("label")]
    except Exception:  # noqa: BLE001  first run: no tab yet
        pass
    b_by = defaultdict(dict)
    for r in base:
        b_by[r["query"]][r.get("rank", 0)] = r
    summ, by_q = [], defaultdict(list)
    for r in new:
        by_q[r["query"]].append(r)
    for q, rows in by_q.items():
        top = [r for r in rows if r.get("rank")]
        b = defaultdict(int)
        for r in top[:10]:
            b[r.get("match") or "-"] += 1

        def prec(k):
            rev = [x for x in (labels.get((q, r["supplier"])) for r in top[:k]) if x]
            return f"{sum(1 for x in rev if x == 'yes')}/{len(rev)}" if rev else "not reviewed"
        bt = next(iter(b_by.get(q, {}).values()), {}).get("total", "")
        summ.append([q, rows[0].get("total", 0), bt, b["supported"], b["plausible"], b["related"], prec(5), prec(10), rows[0].get("ms", "")])
    out = [["Supplier search benchmark: live search code on the real index, no model calls. Fill 'label' (yes / no / related); precision counts reviewed rows only."],
           ["query", "results now", "results baseline", "top10 supported", "top10 plausible", "top10 related", "precision@5 (yes/reviewed)", "precision@10", "ms"], *summ, [""],
           ["query", "rank", "supplier", "country", "tier", "kind", "match", "evidence", "conflicts", "gaps", "products", "label", "baseline at this rank", "baseline products"]]
    for r in new:
        if not r.get("rank"):
            continue
        br = b_by.get(r["query"], {}).get(r["rank"], {})
        out.append([r["query"], r["rank"], r.get("supplier", ""), r.get("country", ""), r.get("tier", ""), r.get("kind", ""), r.get("match", ""),
                    r.get("evidence", ""), r.get("conflicts", ""), r.get("gaps", ""), r.get("products", ""), labels.get((r["query"], r.get("supplier", "")), ""),
                    br.get("supplier", ""), br.get("products", "")])
    s.replace_tab(UNIVERSE_SHEET, TAB, out, raw=True)
    print(f"search eval: {len(by_q)} queries, {len(new)} rows, {len(labels)} labels kept")


if __name__ == "__main__":
    main(*sys.argv[1:3])
