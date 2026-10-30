import Link from "next/link";

export type Field =
  | { kind: "text"; name: string; label: string; placeholder?: string; width?: string }
  | { kind: "select"; name: string; label: string; options: [string, number][]; all?: string }
  | { kind: "number"; name: string; label: string; placeholder?: string }
  | { kind: "check"; name: string; label: string };

export default function FilterBar({ fields, values, action, sort, sortOptions, sortName = "sort", sortLabel = "Sort by", hidden }: {
  fields: Field[]; values: Record<string, string | undefined>; action: string;
  sort?: string; sortOptions?: [string, string][]; sortName?: string; sortLabel?: string; hidden?: Record<string, string>;
}) {
  const active = fields.filter((f) => values[f.name]).length;
  return (
    <form method="get" action={action} className="rounded-xl border border-line bg-white p-4 shadow-sm">
      {hidden && Object.entries(hidden).map(([k, v]) => <input key={k} type="hidden" name={k} value={v} />)}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 lg:grid-cols-6">
        {fields.map((f) => (
          <label key={f.name} className={`block ${f.kind === "text" ? "col-span-2" : ""}`}>
            <span className="text-[11px] font-bold uppercase tracking-wide text-muted">{f.label}</span>
            {f.kind === "text" && (
              <input name={f.name} defaultValue={values[f.name] || ""} placeholder={f.placeholder} className="mt-1 w-full rounded-md border border-line px-3 py-1.5 text-sm outline-none focus:border-accent" />
            )}
            {f.kind === "number" && (
              <input name={f.name} type="number" min="0" defaultValue={values[f.name] || ""} placeholder={f.placeholder} className="mt-1 w-full rounded-md border border-line px-3 py-1.5 text-sm outline-none focus:border-accent" />
            )}
            {f.kind === "select" && (
              <select name={f.name} defaultValue={values[f.name] || ""} className="mt-1 w-full rounded-md border border-line bg-white px-2 py-1.5 text-sm outline-none focus:border-accent">
                <option value="">{f.all || "All"}</option>
                {f.options.map(([v, n]) => (<option key={v} value={v}>{v} ({n.toLocaleString()})</option>))}
              </select>
            )}
            {f.kind === "check" && (
              <span className="mt-2 flex items-center gap-2 text-sm">
                <input type="checkbox" name={f.name} value="1" defaultChecked={values[f.name] === "1"} className="h-4 w-4 accent-[#2F6FB3]" />
                <span>Yes</span>
              </span>
            )}
          </label>
        ))}
        {sortOptions && sortOptions.length > 0 && (
          <label className="block">
            <span className="text-[11px] font-bold uppercase tracking-wide text-muted">{sortLabel}</span>
            <select name={sortName} defaultValue={sort} className="mt-1 w-full rounded-md border border-line bg-white px-2 py-1.5 text-sm outline-none focus:border-accent">
              {sortOptions.map(([v, l]) => (<option key={v} value={v}>{l}</option>))}
            </select>
          </label>
        )}
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button className="rounded-md bg-accent px-4 py-1.5 text-sm font-semibold text-white hover:bg-blue">Apply filters</button>
        {active > 0 && <Link href={action + (hidden ? "?" + new URLSearchParams(hidden).toString() : "")} className="text-sm font-semibold text-muted hover:text-ink">Clear all ({active})</Link>}
      </div>
    </form>
  );
}

export function Pager({ page, pages, total, href }: { page: number; pages: number; total: number; href: (p: number) => string }) {
  if (pages <= 1) return <div className="text-xs text-muted">{total.toLocaleString()} results</div>;
  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="text-xs text-muted">{total.toLocaleString()} results · page {page} of {pages}</span>
      {page > 1 && <Link href={href(page - 1)} className="font-semibold text-accent hover:underline">Previous</Link>}
      {page < pages && <Link href={href(page + 1)} className="font-semibold text-accent hover:underline">Next</Link>}
    </div>
  );
}
