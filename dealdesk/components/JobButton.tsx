"use client";
import { useState } from "react";
import type { Row } from "@/lib/data";

export default function JobButton({ type, deal, label }: { type: string; deal: Row; label: string }) {
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");
  const [msg, setMsg] = useState("");

  async function queue() {
    setState("busy");
    const r = await fetch("/api/job", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        type,
        targetId: deal.id,
        target: deal.title_en || deal.id,
        context: JSON.stringify({ id: deal.id, buyer: deal.buyer, country: deal.country, sector: deal.sector, value: deal.deal_value_usd, deadline: deal.deadline, link: deal.link }),
        request: "",
      }),
    });
    const j = await r.json().catch(() => ({}));
    if (r.ok) { setMsg(j.jobId || ""); setState("done"); }
    else { setMsg(j.error || ""); setState("error"); }
  }

  if (state === "done") return <span className="rounded-md bg-gobg px-3 py-1.5 text-xs font-bold text-go">Queued {msg}</span>;
  return (
    <span>
      <button onClick={queue} disabled={state === "busy"}
        className="rounded-md border border-accent px-3 py-1.5 text-xs font-semibold text-accent hover:bg-accent hover:text-white disabled:opacity-40">
        {state === "busy" ? "Queueing..." : label}
      </button>
      {state === "error" && <span className="ml-2 text-xs text-no">not connected</span>}
    </span>
  );
}
