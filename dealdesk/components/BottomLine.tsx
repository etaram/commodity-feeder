import type { Verdict } from "@/lib/verdict";

const TONE = {
  go: "border-go bg-gobg text-go",
  watch: "border-watch bg-watchbg text-watch",
  no: "border-line bg-paper text-muted",
};

export default function BottomLine({ v }: { v: Verdict }) {
  return (
    <section className={`rounded-xl border-l-4 bg-white p-5 shadow-sm ${TONE[v.tone].split(" ")[0]}`}>
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-[11px] font-bold uppercase tracking-wide text-muted">Bottom line</span>
        <span className={`rounded-full px-3 py-1 text-sm font-bold ${TONE[v.tone]}`}>{v.action}</span>
      </div>
      <div className="mt-3 grid gap-4 md:grid-cols-2">
        <div>
          <div className="text-xs font-bold text-go">Why</div>
          <ul className="mt-1 list-disc pl-5 text-sm">{v.reasons.length ? v.reasons.map((r) => <li key={r}>{r}</li>) : <li className="text-muted">nothing stands out in favour</li>}</ul>
        </div>
        <div>
          <div className="text-xs font-bold text-no">Watch out</div>
          <ul className="mt-1 list-disc pl-5 text-sm">{v.risks.length ? v.risks.map((r) => <li key={r}>{r}</li>) : <li className="text-muted">no specific risk flagged</li>}</ul>
        </div>
      </div>
      <div className="mt-3 rounded-lg bg-paper px-3 py-2 text-sm"><b>Next step:</b> {v.next}</div>
    </section>
  );
}
