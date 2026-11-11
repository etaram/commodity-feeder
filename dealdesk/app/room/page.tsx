import { notFound } from "next/navigation";
import { gate } from "@/lib/gate";
import { loadRoom, roomOn } from "@/lib/roomdata";
import OpsRoom from "@/components/OpsRoom";
import type { RoomView } from "@/lib/room";
import "./room.css";

// The operations room: the agent team at work, from stored rows only (lib/room.ts). Admins only, and the page does
// not exist unless OPS_ROOM=on. The first view is rendered on the server; the screen then refreshes itself from
// /api/room every 20 seconds.
export const dynamic = "force-dynamic";
export const metadata = { title: "חדר מבצעים · Sinder", robots: { index: false, follow: false } };

export default async function RoomPage() {
  if (!roomOn()) notFound();
  const { s } = await gate("admin");
  if (!s) notFound();
  let first: RoomView | null = null, error = "";
  try { first = await loadRoom(s.ws); } catch (e) { error = String(e).slice(0, 200); }
  return <OpsRoom first={first} firstError={error} />;
}
