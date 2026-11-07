export const MAIL = { ready: false, sent: [] as { to: string; subject: string }[] };
export const mailReady = () => MAIL.ready;
export async function sendMail(m: { to: string; subject: string; text: string }) {
  await new Promise((r) => setTimeout(r, 20));  // a real send takes time: two presses overlap
  MAIL.sent.push({ to: m.to, subject: m.subject });
  return { ok: true, id: "<id@x>" };
}
export async function mailCheck() { return { ok: true, host: "mock" }; }
