"use client";
import { useState } from "react";

const NOTICE: Record<string, string> = {
  pending: "Your access request is waiting for approval. You will be able to sign in once an admin approves it.",
  disabled: "This account is disabled. Contact the admin.",
  google: "Google sign-in did not complete. Try again or use your email and password.",
};

const input = "mt-1 w-full rounded-md border border-line px-3 py-2 text-sm outline-none focus:border-accent";
const label = "text-xs font-semibold text-muted";

export default function LoginForm({ google, notice }: { google: boolean; notice: string }) {
  const [mode, setMode] = useState<"login" | "request" | "sent" | "forgot" | "mailed">("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [passcode, setPasscode] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    if (mode === "login") {
      const r = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, passcode }) });
      const j = await r.json().catch(() => ({}));
      setBusy(false);
      if (r.ok) { const n = new URLSearchParams(window.location.search).get("next") || "/"; window.location.href = /^\/(?![/\\])/.test(n) ? n : "/"; }
      else if (j.code === "pending") setErr(NOTICE.pending);
      else if (j.code === "disabled") setErr(NOTICE.disabled);
      else if (j.code === "rate_limited") setErr(j.error || "Too many failed sign-in attempts. Try again later.");
      else setErr("Wrong email or password.");
    } else {
      const r = await fetch("/api/register", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, name, passcode }) });
      const j = await r.json().catch(() => ({}));
      setBusy(false);
      if (r.ok) setMode("sent");
      else setErr(j.error || "Could not send the request.");
    }
  }

  async function forgot(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr("");
    const r = await fetch("/api/auth/reset", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email }) });
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (r.ok) setMode("mailed"); else setErr(j.error || "Could not send the link.");
  }

  if (mode === "forgot" || mode === "mailed") {
    return (
      <div className="mx-auto mt-16 max-w-sm rounded-xl border border-line bg-white p-8 shadow-sm">
        <h1 className="text-xl font-bold">Forgot password</h1>
        {mode === "mailed" ? (
          <p className="mt-2 text-sm text-muted">If an active account uses this address, a link to set a new password is on its way. It works once, for 30 minutes. Check the spam folder too.</p>
        ) : (
          <form onSubmit={forgot} className="mt-6 space-y-4">
            <div><label className={label}>EMAIL</label>
              <input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} className={input} /></div>
            {err && <div className="rounded-md bg-nobg px-3 py-2 text-sm text-no">{err}</div>}
            <button disabled={busy} className="w-full rounded-md bg-accent py-2 text-sm font-semibold text-white hover:bg-blue disabled:opacity-50">{busy ? "Working..." : "Send me a link"}</button>
          </form>
        )}
        <button onClick={() => { setMode("login"); setErr(""); }} className="mt-6 w-full rounded-md border border-line py-2 text-sm font-semibold hover:bg-paper">Back to sign in</button>
      </div>
    );
  }

  if (mode === "sent") {
    return (
      <div className="mx-auto mt-16 max-w-sm rounded-xl border border-line bg-white p-8 shadow-sm">
        <h1 className="text-xl font-bold">Request sent</h1>
        <p className="mt-2 text-sm text-muted">Your request is waiting for the admin. Once approved, sign in with the email and password you chose.</p>
        <button onClick={() => setMode("login")} className="mt-6 w-full rounded-md border border-line py-2 text-sm font-semibold hover:bg-paper">Back to sign in</button>
      </div>
    );
  }

  return (
    <div className="mx-auto mt-16 max-w-sm rounded-xl border border-line bg-white p-8 shadow-sm">
      <h1 className="text-xl font-bold">{mode === "login" ? "Sign in" : "Request access"}</h1>
      <p className="mt-1 text-sm text-muted">{mode === "login" ? "Sinder team access only." : "New accounts are approved by the admin before they can sign in."}</p>
      {notice && mode === "login" && <div className="mt-4 rounded-md bg-watchbg px-3 py-2 text-sm text-watch">{NOTICE[notice]}</div>}
      {google && mode === "login" && (
        <>
          <a href="/api/auth/google" className="mt-6 flex w-full items-center justify-center gap-2 rounded-md border border-line py-2 text-sm font-semibold hover:bg-paper">
            <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9.1 3.6l6.8-6.8C35.8 2.4 30.3 0 24 0 14.6 0 6.5 5.4 2.6 13.3l7.9 6.1C12.4 13.6 17.7 9.5 24 9.5z"/><path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.7 6c4.5-4.2 6.9-10.3 6.9-17.7z"/><path fill="#FBBC05" d="M10.5 28.6c-.5-1.5-.8-3-.8-4.6s.3-3.1.8-4.6l-7.9-6.1C.9 16.6 0 20.2 0 24s.9 7.4 2.6 10.7l7.9-6.1z"/><path fill="#34A853" d="M24 48c6.3 0 11.7-2.1 15.6-5.7l-7.7-6c-2.1 1.4-4.8 2.3-7.9 2.3-6.3 0-11.6-4.1-13.5-9.9l-7.9 6.1C6.5 42.6 14.6 48 24 48z"/></svg>
            Sign in with Google
          </a>
          <div className="my-4 flex items-center gap-3 text-xs text-muted"><span className="h-px flex-1 bg-line" />or<span className="h-px flex-1 bg-line" /></div>
        </>
      )}
      <form onSubmit={submit} className={`${google && mode === "login" ? "" : "mt-6 "}space-y-4`}>
        {mode === "request" && (
          <div>
            <label className={label}>FULL NAME</label>
            <input type="text" autoComplete="name" required value={name} onChange={(e) => setName(e.target.value)} className={input} />
          </div>
        )}
        <div>
          <label className={label}>{mode === "login" ? "EMAIL OR USERNAME" : "EMAIL"}</label>
          <input type={mode === "login" ? "text" : "email"} autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} className={input} />
        </div>
        <div>
          <label className={label}>{mode === "login" ? "PASSWORD" : "CHOOSE A PASSWORD (10+ CHARACTERS)"}</label>
          <input type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={mode === "login" ? 1 : 10} value={passcode} onChange={(e) => setPasscode(e.target.value)} className={input} />
        </div>
        {err && <div className="rounded-md bg-nobg px-3 py-2 text-sm text-no">{err}</div>}
        <button disabled={busy} className="w-full rounded-md bg-accent py-2 text-sm font-semibold text-white hover:bg-blue disabled:opacity-50">
          {busy ? "Working..." : mode === "login" ? "Sign in" : "Send request"}
        </button>
      </form>
      {mode === "login" && <button type="button" onClick={() => { setMode("forgot"); setErr(""); }} className="mt-4 w-full text-center text-xs text-accent hover:underline">Forgot password?</button>}
      <button type="button" onClick={() => { setMode(mode === "login" ? "request" : "login"); setErr(""); }} className="mt-4 w-full text-center text-xs text-accent hover:underline">
        {mode === "login" ? "No account yet? Request access" : "Already have an account? Sign in"}
      </button>
    </div>
  );
}
