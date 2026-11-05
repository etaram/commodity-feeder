# Rollback runbook (Deal Desk upgrade, November 2026)

What a rollback must restore: compatible behaviour across code, configuration, sheet schema, processing versions and derived data, not only an old screen. `/api/panel/manifest` shows what the running build uses.

1. Code: in Vercel, promote the previous production deployment (instant), or `git revert <commit>` and redeploy. panel.html is served from raw GitHub main, so a UI-only revert takes effect within about 5 minutes without a deploy.
2. Supplier matching: every result row carries `match_version`; reverting `dealdesk/lib/supmatch.ts` restores the earlier buckets. `SUPPLIER_STRICT=off` and `SUPPLIER_EXPAND=off` switch search behaviour without code. Verified capabilities can be ignored with `SUPPLIER_VERIFIED=off`.
3. Sheet schema: all changes were additive (Users column M, Deal Records column K, new tabs). Old code ignores the extra columns; blank workspace values read as the original workspace. Nothing to migrate back.
4. Derived data: the supplier index and tender lists are rebuilt by the scheduled workflows from raw sources; to rebuild with older rules, revert `leads/universe.py`, `leads/sectors.py`, `leads/dealfit.py` and dispatch `suppliers.yml` (only=universe) and `leads.yml`.
5. Agents and crons: remove the entry from `dealdesk/vercel.json` (verify, brief, digest) and redeploy; `VERIFY_PER_RUN=0` stops verification without a deploy. Outreach sending stays off unless `OUTREACH_ENABLED` is set.
6. User work is never deleted by a rollback: deal records, labels, verified facts and dossiers are append-only rows.

Rehearsal: promote the previous deployment in a preview, open the panel, run one supplier search and one tender detail, then promote back.

## Data refinement (leads/refine.py)

- The raw supplier rows are never changed by the refinement; the refined layer is `data/checks/refine/refined.jsonl.gz` (Actions cache `checks-*`), applied by `leads/universe.py` while `REFINE` is not `off`.
- Switch off: set `REFINE: "off"` in the `suppliers` workflow env and run it with `only=universe`; the next build has no refined values.
- Go back to an earlier refined layer: the last 7 daily copies are in `data/checks/refine/history/`; copy one over `refined.jsonl.gz` in a workflow step, then rebuild the universe.
- A replaced website is kept in the `website_rejected` column with the reason; duplicate rows stay in the universe with `dup_of` (only the search index shows the canonical record).
