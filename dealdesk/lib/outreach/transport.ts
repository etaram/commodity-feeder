// Pluggable delivery for the outreach engine. The ONLY implementation is TestTransport, which records what would be
// sent and delivers nothing. A real transport (for example the Gmail API) is out of scope: it must not be added until
// a verified sender connection and an explicit campaign authorization exist, and tick() refuses any transport with
// live=true unless OUTREACH_LIVE_TRANSPORT=1 is also set.

export type OutboundMessage = {
  ws: string; campaign_id: string; account_id: string; outbox_id: string; idem_key: string; step: number;
  to: string; from_email: string; from_name: string; subject: string; body: string;
  attachments: { name: string; ref: string }[]; headers: Record<string, string>;
};

export type SendResult = { ok: true; provider_id: string } | { ok: false; code: string; message: string };

export interface Transport {
  readonly name: string;
  readonly live: boolean;
  // The display name of the verified sender connection for this mailbox, or null when it is not verified.
  verifySender(ws: string, email: string): Promise<string | null>;
  send(m: OutboundMessage): Promise<SendResult>;
}

export class TestTransport implements Transport {
  readonly name = "test";
  readonly live = false;
  readonly sent: OutboundMessage[] = [];
  private verified = new Map<string, string>();
  private failures = new Map<string, string[]>();
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
  async send(m: OutboundMessage): Promise<SendResult> {
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
  return "transient"; // 4xx, 4.x.x, timeouts, rate limits, network errors and anything unknown (retried, bounded)
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
