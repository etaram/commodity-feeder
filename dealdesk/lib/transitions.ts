// The allowed moves of the deal builder's own states, in one place (they were checked only for membership, so a
// deal could jump from lead to won, and a sent request left the supplier as a candidate).
import type { STAGES } from "@/lib/deal";

type Stage = (typeof STAGES)[number];
export const PARTY_ORDER = ["candidate", "contacted", "replied", "quoted", "selected"] as const;

/** Deal stage. A deal can move between working stages freely (people correct mistakes), but it is won only from an
 *  offer or a negotiation, and a won or lost deal can only be reopened into negotiation. */
export function canMoveDeal(from: string | undefined, to: string): { ok: boolean; why?: string } {
  if (!from || from === to) return { ok: true };
  if (from === "won" || from === "lost") return to === "negotiation" ? { ok: true } : { ok: false, why: `a ${from} deal can only be reopened into negotiation` };
  if (to === "won" && !(["offer", "negotiation"] as Stage[]).includes(from as Stage)) return { ok: false, why: "a deal is won only after an offer was sent" };
  return { ok: true };
}

/** Supplier, buyer or partner status in a deal. Forward along candidate → contacted → replied → quoted → selected,
 *  dropped from anywhere, and a dropped party can come back only as a candidate. A person may also step one back. */
export function canMoveParty(from: string | undefined, to: string): { ok: boolean; why?: string } {
  if (!from || from === to || to === "dropped") return { ok: true };
  if (from === "dropped") return to === "candidate" ? { ok: true } : { ok: false, why: "a dropped party comes back as a candidate first" };
  const a = PARTY_ORDER.indexOf(from as never), b = PARTY_ORDER.indexOf(to as never);
  if (a < 0 || b < 0) return { ok: true };
  return b >= a - 1 ? { ok: true } : { ok: false, why: `cannot move from ${from} back to ${to}` };
}

/** The status a system event moves a party to, never backwards (a reply already recorded is not undone by a send). */
export function advanceParty(from: string | undefined, to: (typeof PARTY_ORDER)[number]): string {
  if (!from || from === "dropped") return to;
  const a = PARTY_ORDER.indexOf(from as never), b = PARTY_ORDER.indexOf(to);
  return a >= b ? from : to;
}
