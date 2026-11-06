---
name: sinder-deal-orchestrator
description: "Coordinate Sinder deal building from a tender, project, buyer request or product need. Use to assemble a deal dossier, choose research steps, compare routes and update the existing deal builder; not for generic research or autonomous commitments."
---

# Build a Sinder deal
Read references/operating-contract.md first and references/integration.md before connecting to a host application.

1. Resolve the authorized workspace, actor, represented client and current strategy. Locate the existing deal record; update it rather than making a parallel CRM.
2. Create a requirement snapshot: product/material/form/grade, quantity/unit, destination, timeline, standards and unknowns. Record buyer-demand evidence separately from inferred opportunity.
3. Choose only the needed specialist workflows by their skill names. Resolve sibling skills by frontmatter name if installation directories differ. Do not spawn a fleet of agents by default.
4. Evaluate direct, agency, local-partner and EPC/sub-supply routes. A restriction on one route is not a blanket rejection; an unverified partner is not a workaround.
5. Build an evidence-backed supplier shortlist, retrieve permitted contacts, draft RFQs and collect execution candidates.
6. Run deterministic economics on comparable supplied inputs. Keep directory providers, indicative estimates and real offers distinct.
7. Write one dossier: buyer/need, requirements, routes, suppliers, logistics/finance, scenarios, blockers, owner and next actions. Include evidence and version lineage.
8. Use scripts/deal_state.py to check dossier progression. The script validates data, not host authorization. Never treat its output as permission to send or transact.
9. Re-evaluate only affected parts when a quote, specification, deadline, partner or evidence changes.

Stages: research, ready_for_rfq, quoted, reviewed. Execution approval belongs to the host application and human authorization, outside this helper.
Maintain three outputs: world intelligence, research candidate and commercial opportunity. Do not force every event into a deal.

Return a concise decision packet and the lowest-cost next step that could change the decision. Report an unavailable integration rather than inventing tool names, prices or results.
