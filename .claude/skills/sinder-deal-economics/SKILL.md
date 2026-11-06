---
name: sinder-deal-economics
description: "Calculate transparent deal scenarios, profit, financing cost and cash exposure for principal or agency routes. Use for landed cost, supplier quote comparison and bid economics with explicit supplied assumptions; not investment advice or financing approval."
---

# Calculate deal economics
Read references/operating-contract.md and references/economics.md.
Run scripts/deal_math.py with validated JSON; do not do financial arithmetic in prose.

1. Identify principal/resale versus agency model and the currency/quantity/unit basis.
2. Normalize quotes to the same requirements, delivery scope and timing. List included/excluded costs; do not add freight already included in a delivered quote.
3. Separate contract value, addressable supply, sale revenue, purchase cost, commission, operating costs, financing and expected contribution.
4. Use explicit base/downside/upside inputs from quotes or labeled assumptions. Do not invent win odds or expected margins.
5. Build dated cash events for deposits, supplier payments, transport, buyer receipts and other known flows. Check financing costs are not duplicated in both costs and ledger.
6. Compute funding gap and peak exposure with the actual timing. Distinguish profit from liquidity. A profitable deal can be unfinanceable.
7. Report unknowns and conditional viability. A directory bank is not approved credit; an indicative price is not a firm quote.
8. Attach input provenance and versions; re-run only affected scenarios.

The bundled model uses a single currency and simple stated financing assumptions. It does not estimate duties, FX, bank eligibility, tax, letter-of-credit fees or legal requirements. Supply verified/labeled inputs or leave them unresolved.
