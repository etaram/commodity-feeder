"""Seed companies from the brief (C01-C28): match each against the supplier index and report duplicates.

A seed is a starting point, not a verified supplier: the report says whether the index already holds the company
(and under which names, country, tier, website), so no duplicate is created; EPC contractors go to the partner
workflow, not the supplier list. Nothing is written to the supplier universe here.
Run in Actions (needs the index key): python tools/seed_check.py  ->  data/probe/seed_check.md
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.search_eval import suppliers  # noqa: E402

# id, name, official site (from the brief), match words (all must appear in the indexed name), role
SEEDS = [
    ("C01", "COFCO International", "cofcointernational.com", "cofco", "supplier"),
    ("C02", "Olam Agri", "olamagri.com", "olam", "supplier"),
    ("C03", "ADM", "adm.com", "archer daniels|^adm\\b", "supplier"),
    ("C04", "Cargill Agriculture", "cargill.com", "cargill", "supplier"),
    ("C05", "ETG Pulses", "etgworld.com", "^etg\\b|export trading group", "supplier"),
    ("C06", "Wilmar", "wilmar-international.com", "wilmar", "supplier"),
    ("C07", "Apical", "apicalgroup.com", "apical", "supplier"),
    ("C08", "Mitr Phol", "mitrphol.com", "mitr ?phol", "supplier"),
    ("C09", "OCP / OCP Nutricrops", "ocpnutricrops.com", "^ocp\\b|office cherifien", "supplier"),
    ("C10", "Fertiglobe", "fertiglobe.com", "fertiglobe", "supplier"),
    ("C11", "Maaden", "maaden.com", "ma.?aden", "supplier"),
    ("C12", "OQ8", "oq8.om", "^oq8\\b|duqm refinery", "supplier"),
    ("C13", "POSCO International", "poscointl.com", "posco", "supplier"),
    ("C14", "Vale", "vale.com", "^vale\\b", "supplier"),
    ("C15", "Suzano", "suzano.com.br", "suzano", "supplier"),
    ("C16", "Indorama Ventures", "indoramaventures.com", "indorama", "supplier"),
    ("C17", "WEG", "weg.net", "^weg\\b", "supplier"),
    ("C18", "TBEA", "tbea.com", "tbea", "supplier"),
    ("C19", "Hengtong", "hengtonggroup.com", "hengtong", "supplier"),
    ("C20", "Trinasolar", "trinasolar.com", "trina ?solar", "supplier"),
    ("C21", "CATL", "catl.com", "^catl\\b|contemporary amperex", "supplier"),
    ("C22", "Xylem", "xylem.com", "xylem", "supplier"),
    ("C23", "Toray Membrane", "water.toray", "toray", "supplier"),
    ("C24", "Vertiv", "vertiv.com", "vertiv", "supplier"),
    ("C25", "Mindray", "mindray.com", "mindray", "supplier"),
    ("C26", "SANY", "sanyglobal.com", "^sany\\b", "supplier"),
    ("C27", "POWERCHINA", "powerchina.cn", "powerchina|power construction corporation of china|sinohydro", "EPC partner"),
    ("C28", "CSCEC", "cscec.com", "cscec|china state construction", "EPC partner"),
]


def main():
    S = suppliers()
    out = ["# Seed companies vs the supplier index", ""]
    if S is None:
        out.append("Supplier index key not available here: run in Actions.")
    else:
        out += [f"Index: {len(S):,} tier 1-2 suppliers. Matching on the company name; a match is a likely duplicate to merge, not a verification.", "",
                "| Seed | Company | Role | In index | Indexed as (country, tier, website) | Website matches official site |", "|---|---|---|---|---|---|"]
        for cid, name, site, rx, role in SEEDS:
            r = re.compile(rx, re.I)
            m = [x for x in S if r.search(x.get("n", ""))]
            m.sort(key=lambda x: (x.get("tr", "9"), -float(x.get("w") or 0)))
            dom = [x for x in m if site.split(".")[0] in str(x.get("web", "")).lower()]
            shown = "; ".join(f"{x['n'][:40]} ({x.get('c', '?')}, t{x.get('tr', '?')}{', ' + x['web'][:30] if x.get('web') else ''})" for x in m[:3])
            out.append(f"| {cid} | {name} | {role} | {len(m)} | {shown or '-'} | {'yes' if dom else 'no' if m else '-'} |")
        out += ["", "Next: matched seeds are merged into the existing records (no new rows); unmatched seeds are added only after the official",
                "site and an operating entity are confirmed; EPC partners go to the partner workflow."]
    p = ROOT / "data/probe"
    p.mkdir(parents=True, exist_ok=True)
    (p / "seed_check.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(out))


if __name__ == "__main__":
    main()
