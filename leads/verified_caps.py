"""Verified capabilities: one row per (company, country, product) checked on an authoritative source, kept in the
private Supplier Universe sheet, tab 'Verified capabilities'. The Deal Desk supplier search reuses these facts for a
year (lib/panel.ts verifiedCaps): 'yes' makes the company a verified fit for that product, 'no' removes it for that
product only (never for others), 'related' moves it to related. 'unknown' rows are kept as research history and
change nothing.

  python -m leads.verified_caps batch_1_result.csv [more.csv ...]   (columns: query, supplier, country, label,
                                                                    evidence_url, evidence_note, checked)
Method is recorded per row; a model reviewer with web evidence is not a human adjudication and says so.
"""
import csv
import sys

from .push import UNIVERSE_SHEET, Sheets

TAB = "Verified capabilities"
HEAD = ["supplier", "country", "product", "label", "evidence_url", "evidence_note", "checked", "method", "source_query"]


def main(paths, method="web check by an independent model reviewer (not human)"):
    s = Sheets()
    try:
        old = s.values(UNIVERSE_SHEET, f"'{TAB}'!A1:I20000")
    except Exception:  # noqa: BLE001
        old = []
    rows = {}
    if old and old[0][:3] == HEAD[:3]:
        for r in old[1:]:
            r = (r + [""] * len(HEAD))[:len(HEAD)]
            rows[(r[0].lower(), r[1], r[2].lower())] = r
    n_new = 0
    for p in paths:
        for x in csv.DictReader(open(p, encoding="utf-8")):
            lab = (x.get("label") or "").strip().lower()
            if lab not in ("yes", "no", "related", "unknown") or not x.get("supplier"):
                continue
            if lab != "unknown" and not (x.get("evidence_url") or "").startswith("http"):
                lab = "unknown"  # a verdict without a source is not a verified fact
            k = (x["supplier"].lower(), x.get("country", ""), x["query"].lower())
            rows[k] = [x["supplier"], x.get("country", ""), x["query"], lab, x.get("evidence_url", ""), (x.get("evidence_note") or "")[:300],
                       x.get("checked") or "", method, x["query"]]
            n_new += 1
    out = [HEAD] + sorted(rows.values(), key=lambda r: (r[2].lower(), r[0].lower()))
    s.replace_tab(UNIVERSE_SHEET, TAB, out, raw=True)
    print(f"verified capabilities: {n_new} rows merged, {len(rows)} in the tab")


if __name__ == "__main__":
    main(sys.argv[1:])
