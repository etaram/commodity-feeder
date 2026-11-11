// fail: results for the next sends, one per call (a failure at an SMTP stage); nothing is ever really sent
export const MAIL = { ready: false, sent: [] as { to: string; subject: string }[], fail: [] as { ok: false; error: string; stage?: string }[] };
export const mailReady = () => MAIL.ready;
export async function sendMail(m: { to: string; subject: string; text: string }) {
  await new Promise((r) => setTimeout(r, 20));  // a real send takes time: two presses overlap
  const f = MAIL.fail.shift(); if (f) return f;
  MAIL.sent.push({ to: m.to, subject: m.subject });
  return { ok: true, id: "<id@x>" };
}
export async function mailCheck() { return { ok: true, host: "mock" }; }
