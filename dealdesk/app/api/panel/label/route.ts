import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { appendTo, UNIVERSE } from "@/lib/sheets";
import { logActivity } from "@/lib/activity";

// A person's verdict on one supplier for one product, from the research screen: "can supply" (yes), "related only"
// or "wrong product" (no). This is a factual correction about the company, not a preference, so it joins
// Verified capabilities (method: human report) and the search applies it for everyone, for that product only.
// A preference ("not for me") is not stored here.
export async function POST(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  const supplier = String(b.supplier || "").trim().slice(0, 200), product = String(b.product || "").trim().slice(0, 80);
  const label = ["yes", "no", "related"].includes(b.label) ? b.label : "";
  if (!supplier || !product || !label) return NextResponse.json({ ok: false, error: "supplier, product and label are required" }, { status: 400 });
  const note = String(b.note || "").replace(/[\r\n]+/g, " ").slice(0, 200) || (label === "yes" ? "confirmed by a user" : label === "no" ? "reported as the wrong product by a user" : "reported as a related product by a user");
  const evidence = /^https?:\/\//.test(String(b.url || "")) ? String(b.url).slice(0, 300) : "user report";
  try {
    await appendTo(UNIVERSE, "Verified capabilities", [supplier, String(b.country || "").slice(0, 3).toUpperCase(), product, label, evidence, note,
      new Date().toISOString().slice(0, 10), `human report (${s.email})`, product]);
    await logActivity(s, "supplier_label", `${supplier} | ${product}`, label);
    return NextResponse.json({ ok: true });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
