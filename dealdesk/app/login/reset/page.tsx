"use client";
import { useState } from "react";

const input = "mt-1 w-full rounded-md border border-line px-3 py-2 text-sm outline-none focus:border-accent";

export default function ResetPage() {
  const [pw, setPw] = useState(""), [pw2, setPw2] = useState(""), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (pw !== pw2) { setErr("The two passwords are not the same."); return; }
    setBusy(true); setErr("");
    const t = new URLSearchParams(window.location.search).get("t") || "";
    const r = await fetch("/api/auth/reset/confirm", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ t, passcode: pw }) });
    const j = await r.json().catch(() => ({}));
    setBusy(false);
    if (r.ok) window.location.href = "/"; else setErr(j.error || "Could not set the password.");
  }
  return (
    <div className="mx-auto mt-16 max-w-sm rounded-xl border border-line bg-white p-8 shadow-sm">
      <h1 className="text-xl font-bold">Set a new password</h1>
      <form onSubmit={submit} className="mt-6 space-y-4">
        <div><label className="text-xs font-semibold text-muted">NEW PASSWORD (10+ CHARACTERS)</label>
          <input type="password" autoComplete="new-password" required minLength={10} value={pw} onChange={(e) => setPw(e.target.value)} className={input} /></div>
        <div><label className="text-xs font-semibold text-muted">THE SAME AGAIN</label>
          <input type="password" autoComplete="new-password" required minLength={10} value={pw2} onChange={(e) => setPw2(e.target.value)} className={input} /></div>
        {err && <div className="rounded-md bg-nobg px-3 py-2 text-sm text-no">{err}</div>}
        <button disabled={busy} className="w-full rounded-md bg-accent py-2 text-sm font-semibold text-white hover:bg-blue disabled:opacity-50">{busy ? "Working..." : "Save and sign in"}</button>
      </form>
      <a href="/login" className="mt-4 block text-center text-xs text-accent hover:underline">Back to sign in</a>
    </div>
  );
}
