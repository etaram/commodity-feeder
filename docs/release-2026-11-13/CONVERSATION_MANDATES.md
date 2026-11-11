# Conversation mandates and the send policy

Status on 11 Nov 2026: library code and tests only. **Conversation mode is OFF by default and nothing is wired.**
Every outgoing message still waits for the owner's approval, exactly as before.

Code: `dealdesk/lib/mandate.ts` (mandate + `decideSend`), `dealdesk/lib/mission.ts` (mission object).
Tests: `dealdesk/tests/mandate.test.ts`, `dealdesk/tests/mission.test.ts` (run with `npm test`).

## What a mandate is

The owner's written permission for one conversation: one counterparty (legal name and one verified address), one
channel, the sender it is written on behalf of, a purpose and target outcome, the permitted claims, topics and
attachments, a price boundary (currency, min, max, unit), a quantity boundary, the maximum number of concessions and
messages, an expiry time and the owner's stop reasons. Statuses: draft, approved, revoked, expired.

- Only a draft can be approved, and only with a named approver. Any change of scope makes a new draft version;
  the earlier approval does not carry over.
- An approved mandate counts as expired from its expiry time on, even if nobody stored the change.

## The decision

`decideSend(input)` returns `ALLOW`, `REQUIRES_APPROVAL` or `DENY`, the reasons, and what the decision is bound to:
recipient, channel, message hash, mandate id and version. It is plain code. No model takes part in authorization.
The drafting step may pass extracted facts (prices, quantities, commitments, parties, attachments, flags); facts can
only add a reason to stop, never remove one. Free text inside the facts is compared, never obeyed.

Rules, in order:

1. **DENY, always** (mandate, flag and approvals make no difference): global kill switch; recipient on the
   suppression list (address or domain) or an opt-out seen in the reply; empty message or no recipient; any request
   to sign, submit a bid or move money. These three actions are never authorized by this system.
2. **DENY with a mandate in force**: mandate revoked or expired; recipient is not the mandate's verified address;
   channel is not the mandate's channel.
3. **ALLOW by the owner's per-message approval**: an approval releases only the exact message it was given for.
   If the text, subject, attachments, recipient, channel or mandate version changed afterwards, the hash no longer
   matches and the approval is void (`approval_invalid`). Rules 1 and 2 still apply.
4. **REQUIRES_APPROVAL** when there is no mandate, the flag `conversationMode` is off (the default), or the mandate
   is still a draft. This is today's per-message behaviour.
5. **REQUIRES_APPROVAL with an escalation reason**, flag on and mandate approved:
   - the first message of a conversation, always;
   - a price or quantity outside the boundary, in another currency or unit, or with no boundary set;
   - any binding commitment: sign, guarantee, bid, pay, exclusivity, acceptance. Detected from the facts and also
     from the wording of the text itself, in case the extraction missed it;
   - the counterparty asking for such a commitment;
   - a new party, a reply from a different address, a topic outside the purpose, a claim that was not permitted;
   - an attachment that was not approved;
   - more messages or concessions than the mandate allows;
   - a sanctions or legal flag, or one of the owner's stop reasons.
6. **ALLOW** (`within_mandate`) only when none of the above applies.

## Default

`conversationMode` defaults to `false`. With it off, a mandate changes nothing: every message needs the owner's
approval. Turning it on is the owner's decision and is not part of this release step.

## Missions

`lib/mission.ts` holds the durable mission: type, goal, budget, allowed tools, stop rules, status and tasks for the
ten specialist roles. Tasks are idempotent (the same key never makes a second task), respect dependencies, reserve
cost before starting (a reservation over the budget is refused and the mission moves to `needs_owner`), retry up to
`max_attempts`, and are reviewed by a different role (red_team reviews; red_team's own work is reviewed by
source_evidence). A dependant starts only after its dependency passed review. State is rebuilt from an append-only
store on every call, so a restart does not duplicate tasks or double-charge. `ROLE_PERSONAS` maps the roles to the
team in `lib/team.ts`.

## Not wired yet

- `dealagent.ts` (`propose_message`, `decide`) and the outreach outbox (`lib/outreach/outbox.ts`) do not call
  `decideSend`. They use per-message approval and campaign authorization as before.
- No UI or Telegram flow creates, approves or revokes a mandate. No route sets the flag or the kill switch.
- Storage: only in-memory stores exist (`MemoryMandateStore`, `MemoryMissionStore`). No Sheets or database adapter.
- No fact extraction step exists; `decideSend` only defines the shape it accepts.
- Nothing runs missions: there is no scheduler, no model call and no cost metering behind `reserveCost`.
- The suppression list is passed in as plain values; the caller must map the outreach suppression entries
  (active ones, workspace-wide and per campaign) into it.

Wiring any of this into live sending is a separate step and needs the owner's explicit approval.

## Open points for the owner

- An owner's exact per-message approval releases an escalated message (for example one that offers exclusivity).
  Signing, bidding and paying stay denied even then.
- A task that fails after its last attempt fails the whole mission. The alternative is `needs_owner`.
- osint and red_team have no persona in the team; commercial_strategy and negotiation_comms both map to Arjun.
