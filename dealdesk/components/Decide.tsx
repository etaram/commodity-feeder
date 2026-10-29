"use client";
import { useState } from "react";

export default function Decide({ id, title, buyer, country, compact }: {
  id: string; title: string; buyer: string; country: string; compact?: boolean;
}) {
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");
  const [picked, setPicked] = useState("");

  async function decide(decision: string) {
    setState("busy");
    const r = await fetch("/api/decision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, decision, title, buyer, country }),
    });
    if (r.ok) { setPicked(decision); setState("done"); }
    else setState("error");
  }

  if (state === "done")
    return <span className={`rounded-full px-3 py-1 text-xs font-bold ${picked === "Go" ? "bg-gobg text-go" : picked === "Watch" ? "bg-watchbg text-watch" : "bg-nobg text-no"}`}>
      Saved: {picked}
    </span>;

  return (
    <span className="flex items-center gap-1.5">
      <button onClick={() => decide("Go")} disabled={state === "busy"}
        className="rounded-full bg-gobg px-3 py-1 text-xs font-bold text-go hover:ring-1 hover:ring-go disabled:opacity-40">Go</button>
      <button onClick={() => decide("Watch")} disabled={state === "busy"}
        className="rounded-full bg-watchbg px-3 py-1 text-xs font-bold text-watch hover:ring-1 hover:ring-watch disabled:opacity-40">Watch</button>
      <button onClick={() => decide("No")} disabled={state === "busy"}
        className="rounded-full bg-nobg px-3 py-1 text-xs font-bold text-no hover:ring-1 hover:ring-no disabled:opacity-40">No</button>
      {state === "error" && !compact && <span className="text-xs text-no">Could not save (Sheets not connected)</span>}
    </span>
  );
}
