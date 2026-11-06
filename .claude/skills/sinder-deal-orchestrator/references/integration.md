# Host integration
Skills are instructions and offline helpers, not a deployed autonomous service. Inspect the real repository, schema, tools, permissions, queues and model entitlements first. Do not invent endpoints or assume this chat's connectors are available inside Sinder.

## Required adapter capabilities
- read authorized records with pagination and stable IDs;
- retrieve source documents and evidence excerpts with content hashes;
- search requirements/suppliers/prospects using server-side access control;
- propose versioned assertions and resolve conflicts with expected_revision;
- create/update existing deal dossiers with idempotency keys;
- create/poll/cancel persisted research jobs;
- draft RFQs and outreach without sending;
- retrieve actual offers and execution terms;
- meter model/retrieval cost and enforce tenant/job limits;
- send only via separately authorized campaign actions.

Maintain a tool registry recording actual name, input/output schema, read/write/send classification, auth scope, cost, timeout, idempotency, pagination and failure handling. Mark absent capabilities unavailable and emit a task for integration. Read-only access does not grant sending access.

## Minimal dossier
workspace_id, actor_id, client_id?, deal_id, revision, stage, requirements, buyer_evidence, route_options, suppliers, execution_options, economics, claims, gaps, tasks, source_versions, profile_version.
Each claim carries evidence_id, source, time and status; each task has owner, due date, dependency and status.

Use normal backend policy for workspace membership, object access, private indexes/caches, exports and attachments. A prompt instruction or the bundled validation helper cannot implement RBAC. Do not retrieve unauthorized private data and then ask the model to omit it.

Map stages to the existing application; avoid a new parallel database. Persist structured outputs and pending job IDs. Retry only documented transient errors, with bounded backoff. Never treat a started call as finished.
Use source-level cached extraction and code filtering. Load relevant skills only, not the whole collection. Start sequentially; parallelize only independent bounded reads when useful. No multi-agent requirement.

## Rollout
Inventory → offline fixtures → adapter mapping → sandbox end-to-end → shadow comparison → authorized rollout. Keep feature flags and prior derived versions. The package does not itself deploy, schedule crawls, verify a real mailbox or execute financial transactions.
