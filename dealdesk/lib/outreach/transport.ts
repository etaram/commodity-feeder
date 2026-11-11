// Pluggable delivery for the outreach engine. The ONLY implementation is TestTransport, which records what would be
// sent and delivers nothing. A real transport (for example the Gmail API) is out of scope: it must not be added until
// a verified sender connection and an explicit campaign authorization exist, and tick() refuses any transport with
// live=true unless OUTREACH_LIVE_TRANSPORT=1 is also set.

export type OutboundMessage = {
  ws: string; campaign_id: string; account_id: string; outbox_id: string; idem_key: string; step: number;
  to: string; from_email: string; from_name: string; subject: string; body: string;
  attachments: { name: string; ref: string }[]; headers: Record<string, string>;
};

// A failure without `delivery` is a definite answer: the provider refused the message, or the transport is certain the
// request never left (connect refused, DNS). A transport MUST set delivery:"unknown" when the request may have left and
// no clear answer came back (read timeout, connection reset after dispatch, ambiguous provider reply). A send() that
// throws is treated the same way. Such an item is never retried blindly (see OutboxStatus delivery_unknown).
export type SendResult = { ok: true; provider_id: string } | { ok: false; code: string; message: string; delivery?: "unknown" };

// What the provider says about a message, looked up by idempotency key (reconcile step).
export type DeliveryLookup = { state: "sent"; provider_id: string } | { state: "not_sent" } | { state: "unknown" };

export interface Transport {
  readonly name: string;
  readonly live: boolean;
  // The display name of the verified sender connection for this mailbox, or null when it is not verified.
  verifySender(ws: string, email: string): Promise<string | null>;
  send(m: OutboundMessage): Promise<SendResult>;
  // Optional: ask the provider whether a message with this idempotency key was accepted. Without it only the owner can reconcile.
  lookup?(ws: string, idem_key: string): Promise<DeliveryLookup>;
}

export class TestTransport implements Transport {
  readonly name = "test";
  readonly live = false;
  readonly sent: OutboundMessage[] = [];
  private verified = new Map<string, string>();
  private failures = new Map<string, string[]>();
  private ambiguous = new Map<string, ("lost" | "delivered" | "throw")[]>();
  private n = 0;

  constructor(senders: { ws: string; email: string; name: string }[] = []) {
    for (const s of senders) this.verifySenderFor(s.ws, s.email, s.name);
  }
  verifySenderFor(ws: string, email: string, name: string) { this.verified.set(`${ws}|${email.toLowerCase()}`, name); }
  revokeSender(ws: string, email: string) { this.verified.delete(`${ws}|${email.toLowerCase()}`); }
  // Queue error codes for a recipient (consumed one per send attempt), to exercise retry classification.
  failNext(to: string, ...codes: string[]) { this.failures.set(to.toLowerCase(), [...(this.failures.get(to.toLowerCase()) || []), ...codes]); }

  async verifySender(ws: string, email: string): Promise<string | null> {
    return this.verified.get(`${ws}|${email.toLowerCase()}`) ?? null;
  }
  // Ambiguous outcomes for a recipient (consumed one per send attempt). "lost": timeout, nothing was delivered.
  // "delivered": the provider accepted the message but the answer never arrived. "throw": send() itself rejects.
  ambiguousNext(to: string, ...modes: ("lost" | "delivered" | "throw")[]) { this.ambiguous.set(to.toLowerCase(), [...(this.ambiguous.get(to.toLowerCase()) || []), ...modes]); }
  // When set, lookup() answers "unknown" (a provider that cannot confirm either way).
  lookupUnavailable = false;
  async lookup(ws: string, idem_key: string): Promise<DeliveryLookup> {
    if (this.lookupUnavailable) return { state: "unknown" };
    const i = this.sent.findIndex((m) => m.ws === ws && m.idem_key === idem_key);
    return i >= 0 ? { state: "sent", provider_id: `test-lookup-${i + 1}` } : { state: "not_sent" };
  }

  async send(m: OutboundMessage): Promise<SendResult> {
    const amb = this.ambiguous.get(m.to.toLowerCase());
    if (amb && amb.length) {
      const mode = amb.shift()!;
      if (mode === "delivered") this.sent.push(JSON.parse(JSON.stringify(m)));
      if (mode === "throw") throw new Error("socket hang up");
      return { ok: false, code: "timeout", message: "test: no answer after dispatch", delivery: "unknown" };
    }
    const q = this.failures.get(m.to.toLowerCase());
    if (q && q.length) { const code = q.shift()!; return { ok: false, code, message: `test failure ${code}` }; }
    this.sent.push(JSON.parse(JSON.stringify(m)));
    return { ok: true, provider_id: `test-${++this.n}` };
  }
}

// Retry classification of a send error code (SMTP reply code, enhanced status code or provider error name).
export type ErrorClass = "hard_bounce" | "permanent" | "sender" | "transient";
export function classifySendError(code: string): ErrorClass {
  const c = String(code || "").trim().toLowerCase();
  if (/^(550|551|553)\b/.test(c) || /^5\.1\.\d/.test(c) || /^5\.2\.1/.test(c) || ["invalid_recipient", "hard_bounce", "no_such_user", "mailbox_unavailable"].includes(c)) return "hard_bounce";
  if (["auth_failed", "sender_not_verified", "sender_revoked", "530", "535"].includes(c) || /^5\.7\.(0|8)/.test(c)) return "sender";
  if (/^5\d\d\b/.test(c) || /^5\.\d\.\d/.test(c) || ["rejected", "content_rejected", "invalid_message"].includes(c)) return "permanent";
  // 4xx, 4.x.x, rate limits, and timeouts / network errors the transport reports as definitely not sent, and anything
  // unknown (retried, bounded). An ambiguous outcome never reaches this function: see SendResult.delivery.
  return "transient";
}

// The transport used by the API routes and the cron. Senders for the test transport come from
// OUTREACH_TEST_SENDERS ("ws:email:Display Name;ws2:email2:Name"), so a dry run needs an explicit setting too.
let shared: TestTransport | null = null;
export function getTransport(): Transport {
  const want = (process.env.OUTREACH_TRANSPORT || "test").trim().toLowerCase();
  if (want !== "test") throw new Error(`Transport "${want}" is not available: real sending is disabled in this build`);
  if (!shared) {
    const senders = String(process.env.OUTREACH_TEST_SENDERS || "").split(";").map((x) => x.trim()).filter(Boolean).map((x) => {
      const [ws, email, ...name] = x.split(":");
      return { ws: (ws || "").trim(), email: (email || "").trim(), name: name.join(":").trim() };
    }).filter((x) => x.ws && x.email && x.name);
    shared = new TestTransport(senders);
  }
  return shared;
}
