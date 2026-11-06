# Refinement contract
Maintain original rows and canonical entity references. Track exact dataset denominator and snapshot. Separate processed, reused, enriched, source-supported, independently checked, conflicted and unresolved. A valid reuse requires unchanged relevant input and non-expired evidence/method versions.

Store contacts with type (email, business phone, contact form, social company page), exact value, source URL, date and attribution. A LinkedIn company page is a research channel, not an email or proof messages can be sent. Syntax tests do not confirm deliverability or WhatsApp support. A form may be an adequate channel.

Use bounded retrieval, permitted pages, public-network checks, redirects checked at each hop, timeouts and byte limits. Never join company facts solely by a broad group name or common keyword. Keep each country-specific legal entity and plant identifiable.

For large datasets stream/checkpoint instead of placing the entire database in prompts. Index IDs/names/domains locally. Batch requests to the real data store to avoid read quota exhaustion. Run a full backfill after validating a sample; keep the remaining queue until every in-scope row has been processed/reused. No fixed daily verified-count promises.

The bundled script reads NDJSON and proposes checks only. It is not web enrichment or legal identity verification. Production enrichment requires the adapters described in the orchestrator skill.
