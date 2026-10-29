import { getIsrael, num } from "@/lib/data";

export const revalidate = 900;

export default async function IsraelPage({ searchParams }: { searchParams: Promise<{ kind?: string }> }) {
  const { kind } = await searchParams;
  const items = await getIsrael();
  const open = items.filter((r) => r.id);
  const shown = (kind ? open.filter((r) => r.kind === kind) : open.filter((r) => r.kind !== "exemption"))
    .sort((a, b) => (b.first_seen || "").localeCompare(a.first_seen || "") || (a.deadline || "9999").localeCompare(b.deadline || "9999"));
  const counts = { tender: 0, call: 0, exemption: 0 } as Record<string, number>;
  for (const r of open) counts[r.kind] = (counts[r.kind] || 0) + 1;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-bold text-navy">Israel - public notices</h1>
        <div className="flex gap-2 text-xs">
          {[["", `All ${open.length - counts.exemption}`], ["tender", `Tenders ${counts.tender}`], ["call", `Calls ${counts.call}`], ["exemption", `Exemptions ${counts.exemption}`]].map(([k, label]) => (
            <a key={k} href={k ? `?kind=${k}` : "?"} className={`rounded-full px-3 py-1 font-semibold ${kind === k || (!kind && !k) ? "bg-navy text-white" : "bg-white border border-line text-muted"}`}>{label}</a>
          ))}
        </div>
      </div>
      <div className="overflow-x-auto rounded-xl border border-line bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-line text-left text-[11px] uppercase text-muted">
            <th className="px-4 py-2">New</th><th className="px-4 py-2">Body</th><th className="px-4 py-2">Type</th>
            <th className="px-4 py-2">Title</th><th className="px-4 py-2">Kind</th><th className="px-4 py-2">Deadline</th><th className="px-4 py-2">Days</th><th className="px-4 py-2"></th>
          </tr></thead>
          <tbody>
            {shown.slice(0, 400).map((r) => (
              <tr key={r.id} className="border-b border-line/60">
                <td className="px-4 py-2">{r.new === "NEW" && <span className="rounded bg-gobg px-1.5 py-0.5 text-[10px] font-bold text-go">NEW</span>}</td>
                <td className="px-4 py-2 whitespace-nowrap">{r.body}</td>
                <td className="px-4 py-2 whitespace-nowrap text-muted">{r.body_type}</td>
                <td className="px-4 py-2" dir="rtl" style={{ textAlign: "left" }}>{r.title}</td>
                <td className="px-4 py-2">{r.kind}</td>
                <td className="px-4 py-2 whitespace-nowrap">{r.deadline || "-"}</td>
                <td className={`px-4 py-2 font-semibold ${num(r.days_left) > 0 && num(r.days_left) <= 7 ? "text-no" : ""}`}>{r.days_left || "-"}</td>
                <td className="px-4 py-2">{r.link && <a href={r.link} target="_blank" className="font-semibold text-accent hover:underline">Open</a>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
