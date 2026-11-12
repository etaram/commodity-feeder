// Deal records (lib/deal.ts clean): the dossier fields on the stage, the evidence fields on requirements and parties,
// the economics skeleton, and drafts that are kept on the deal without ever being sent.
import { clean } from "@/lib/deal";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };

const st = clean("stage", { stage: "lead", status_label: "qualification in progress", decision: "proceed to supplier qualification", actions: ["a", "", "b"],
  sources: [{ key: "S1", label: "Tender document", url: "https://example.org/x" }, { key: "S2", label: "bad url", url: "javascript:alert(1)" }, { key: "", label: "no key" }], as_of: "2026-11-12" });
ok(st.ok && st.data.status_label === "qualification in progress" && (st.data.actions as string[]).length === 2, "stage keeps the status in words and the non-empty next actions");
ok(st.ok && (st.data.sources as { url: string }[]).length === 2 && (st.data.sources as { url: string }[])[1].url === "", "sources: a key is required and only http(s) addresses are kept");
ok(st.ok && st.status === "lead", "the stage itself is unchanged by the dossier fields");

const rq = clean("requirement", { item: "Turnover >= EUR 2m", status: "unknown", source_doc: "S1 §5(B)", as_of: "2026-11-12", group: "selection" });
ok(rq.ok && rq.data.as_of === "2026-11-12" && rq.data.group === "selection", "requirement keeps its evidence date and group");
ok(!clean("requirement", { item: "x", status: "met" }).ok, "a met requirement still needs evidence");

const pt = clean("party", { role: "supplier", name: "Maker", email: "sales@maker.example", verification: "conditional", source: "https://maker.example/p", as_of: "2026-11-12" });
ok(pt.ok && pt.status === "candidate" && pt.data.verification === "conditional", "party: fit verification is separate from the contact status");

const ec = clean("economics", { role: "agent", lines: [{ input: "Base cable price", basis: "Q", treatment: "DDP bidder rate" }, { basis: "S" }] });
ok(ec.ok && (ec.data.lines as unknown[]).length === 1 && ec.data.sale_price === null, "economics skeleton: lines kept, prices stay empty (unknown, never zero)");

const dr = clean("draft", { to_name: "Maker", to_email: "sales@maker.example", subject: "Capability inquiry", body: "Hello", status: "sent" });
ok(dr.ok && dr.status === "awaiting_owner_approval" && dr.data.sent === false, "a draft cannot be saved as sent: it waits for the owner's approval");
ok(!clean("draft", { to_name: "Maker", subject: "" , body: "x" }).ok, "a draft needs a subject and a body");

if (fail) process.exit(1);
