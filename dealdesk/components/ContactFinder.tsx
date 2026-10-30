"use client";
import { useState } from "react";
import type { Row } from "@/lib/data";

type C = { name?: string; role?: string; email?: string; phone?: string; channel?: string; source?: string; confidence?: string };

export default function ContactFinder({ deal }: { deal: Row }) {
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");
  const [res, setRes] = useState<{ contacts: C[]; website?: string; notes?: string } | null>(null);
  const [err, setErr] = useState("");

  async function go() {
    setState("busy"); setErr("");
    try {
      const r = await fetch("/api/panel/run", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: "find_contact", target_id: "FC:" + deal.id, target: String(deal.buyer || deal.title_en || deal.id),
          context: { buyer: deal.buyer, country: deal.country, title: deal.title_en, contact: deal.contact, link: deal.link, access: deal.access, notice_type: deal.notice_type },
          lang: "en",
        }),
      });
      const j = await r.json();
      if (!r.ok || !j.ok) throw new Error(j.error || "failed");
      setRes(j.contacts && Array.isArray(j.contacts.contacts) ? j.contacts : { contacts: [], notes: "" });
      setState("done");
    } catch (e) { setErr(String((e as Error).message || e)); setState("error"); }
  }

  return (
    <div className="w-full">
      <button onClick={go} disabled={state === "busy"} className="rounded-md border border-accent px-3 py-1.5 text-xs font-semibold text-accent hover:bg-accent hover:text-white disabled:opacity-40">
        {state === "busy" ? "Searching official sources..." : state === "done" ? "Search again" : "Get contact details"}
      </button>
      {state === "error" && <span className="ml-2 text-xs text-no">{err}</span>}
      {deal.contact ? <p className="mt-2 text-xs text-muted">From the notice: <span dir="ltr">{String(deal.contact)}</span></p> : null}
      {state === "done" && res && (
        <div className="mt-3 space-y-2">
          {res.contacts.length === 0 && <p className="text-sm text-muted">No public email found.</p>}
          {res.contacts.map((c, i) => (
            <div key={i} className="rounded-lg border border-line bg-white p-3 text-sm">
              <div className="font-semibold">{c.name || c.role || "Contact"}{c.name && c.role ? <span className="font-normal text-muted"> · {c.role}</span> : null}</div>
              {c.email && <div dir="ltr"><a className="text-accent underline" href={`mailto:${c.email}`}>{c.email}</a></div>}
              {c.phone && <div dir="ltr" className="text-muted">{c.phone}</div>}
              {c.channel && <div className="text-muted">{c.channel}</div>}
              {c.source && <div className="text-xs text-muted">Source: <a className="underline" href={c.source} target="_blank" rel="noopener">{c.source}</a> ({c.confidence || "?"})</div>}
            </div>
          ))}
          {res.website && <p className="text-xs"><a className="underline" href={res.website} target="_blank" rel="noopener">{res.website}</a></p>}
          {res.notes && <p className="text-xs text-muted">{res.notes}</p>}
        </div>
      )}
    </div>
  );
}
