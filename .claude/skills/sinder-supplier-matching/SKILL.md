---
name: sinder-supplier-matching
description: "Match Sinder product requirements to capable manufacturers, merchants, distributors and EPCs. Use for supplier shortlists, tender matching and product compatibility; distinguish entity reputation from exact product fit."
---

# Match suppliers to requirements
Read references/operating-contract.md and references/matching.md.

1. Parse mandatory specifications and flexible preferences; preserve unknowns and original-language terms.
2. Retrieve through indexed product assertions, properly attributed award line items and trade evidence. Separate company-name retrieval from product evidence.
3. Apply scripts/match_guard.py to supplied candidate evidence as a conservative English regression guard. It is not a full multilingual matching engine or a substitute for technical review.
4. Classify supported, plausible, related or incompatible. Supported requires evidence for all supplied mandatory distinctions; absence is a gap. Established mismatch is not a plausible exact match.
5. Distinguish product, component, installation, transport context and buyer/operator role. Do not let HS chapter, aggregate awards or a prestigious group override the requirement.
6. Rank within compatibility states using evidence strength, fulfillment role, destination/export suitability, freshness and contact readiness. Do not always prioritize manufacturers over commodity merchants.
7. Keep group/subsidiary/plant relationships visible and deduplicate by evidenced identity.
8. Return requirement-specific evidence and gaps, not merely a global Tier. Explain which specification is supported and which needs confirmation.

Regression families: white maize vs yellow, cornmeal, snacks and Corning; fertilizer urea vs cosmetics/peroxide/medical testing/DEF; flat hot rolled coil vs wire rod/cold rolled/plate; power transformers vs instrument transformers/EPC; PE pipes vs steel/rails; generators sold vs reefer shipping context; RO systems vs automotive filters.

A poor snippet is insufficient to blacklist a company. Reclassify this match and request the right evidence.
