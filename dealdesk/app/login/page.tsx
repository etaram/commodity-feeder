"use client";
import { useState } from "react";

export default function Login() {
  const [email, setEmail] = useState("");
  const [passcode, setPasscode] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setErr("");
    const r = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, passcode }),
    });
    setBusy(false);
    if (r.ok) window.location.href = "/";
    else setErr("Wrong e-mail or passcode.");
  }

  return (
    <div className="mx-auto mt-16 max-w-sm rounded-xl border border-line bg-white p-8 shadow-sm">
      <h1 className="text-xl font-bold">Sign in</h1>
      <p className="mt-1 text-sm text-muted">Sinder team access only.</p>
      <form onSubmit={submit} className="mt-6 space-y-4">
        <div>
          <label className="text-xs font-semibold text-muted">E-MAIL</label>
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
            className="mt-1 w-full rounded-md border border-line px-3 py-2 text-sm outline-none focus:border-accent" />
        </div>
        <div>
          <label className="text-xs font-semibold text-muted">TEAM PASSCODE</label>
          <input type="password" required value={passcode} onChange={(e) => setPasscode(e.target.value)}
            className="mt-1 w-full rounded-md border border-line px-3 py-2 text-sm outline-none focus:border-accent" />
        </div>
        {err && <div className="rounded-md bg-nobg px-3 py-2 text-sm text-no">{err}</div>}
        <button disabled={busy} className="w-full rounded-md bg-accent py-2 text-sm font-semibold text-white hover:bg-blue disabled:opacity-50">
          {busy ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </div>
  );
}
