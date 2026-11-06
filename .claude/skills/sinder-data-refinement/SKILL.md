---
name: sinder-data-refinement
description: "Refine and enrich all Sinder supplier, buyer, tender, project, logistics and finance records. Use for full-database backfills, contact cleanup, entity classification, conflicts and incremental refreshes, not merely a small curated shortlist."
---

# Refine the complete dataset
Read references/operating-contract.md and references/refinement.md.

1. Inventory each dataset, its exact denominator, scope, source versions and the indexed subset. Do not conflate raw rows, canonical entities and searchable records.
2. Schedule every record for processing with checkpointed idempotent batches. Use a sample to validate changes, then continue across the full dataset; a sample is not the requested scope.
3. Run scripts/refine_records.py on NDJSON for offline checks, candidate normalization and coverage summaries. It does not crawl websites, verify legal identity, test delivery or write production.
4. Use authorized retrieval adapters to resolve the official entity/domain, parse permitted product/contact pages and retain field-level evidence. Cache reusable extraction; revisit changed/stale pages.
5. Separate manufacturer, merchant, distributor, EPC, operator and buyer roles. Preserve unknown and multiple roles. A group capability does not automatically apply to a division or subsidiary.
6. Validate emails/phones structurally before saving. A syntactically plausible number or a form URL is not proof of responsiveness. Never infer WhatsApp availability from a phone number.
7. Detect duplicates and conflicts without destructive merging. Route uncertain identities and product contradictions for review.
8. Apply corrections as proposed/versioned assertions, then read back authorized writes through the actual host adapter.
9. Report attempted, processed, reused, enriched, conflicted, unresolved and contact-supported separately, by dataset. Completion means every in-scope record attempted or validly reused, not every fact verified.

Prioritize commercially useful records first while retaining the full-dataset completion queue. Do not skip low-priority rows permanently. Meter actual workloads; no hard-coded promise of 500 or 50,000 verified records.
