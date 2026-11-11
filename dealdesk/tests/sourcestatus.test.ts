// F19: the ops page lists the collectors that are not OK first, each with a text label (lib/data.ts).
import { SOURCE_STATUS_LABEL, sortSourceStatus, type SourceStatus } from "@/lib/data";

let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
const s = (source: string, status: string): SourceStatus => ({ source, status, rows: 1, rows_last_good: 1, last_good_at: "2026-11-10T08:00" });

const sorted = sortSourceStatus([s("b_ok", "OK"), s("a_ok", "OK"), s("z_stale", "STALE"), s("m_down", "DOWN"), s("k_degraded", "DEGRADED"), s("c_denied", "DENIED"), s("d_limited", "RATE_LIMITED"), s("x_new", "SOMETHING_NEW")]);
const names = sorted.map((x) => x.source);
ok(names.slice(-2).join() === "a_ok,b_ok", "sources that are OK come last, by name");
ok(sorted.findIndex((x) => x.status === "OK") === 6, "every source that is not OK is listed before the first OK one");
ok(names.indexOf("m_down") < names.indexOf("z_stale") && names.indexOf("z_stale") < names.indexOf("k_degraded"), "failed sources before stale ones, stale before degraded");
ok(names.indexOf("x_new") < names.indexOf("a_ok"), "an unknown status is never sorted among the OK sources");
ok(["OK", "DEGRADED", "STALE", "DOWN", "DENIED", "RATE_LIMITED"].every((k) => typeof SOURCE_STATUS_LABEL[k] === "string" && SOURCE_STATUS_LABEL[k].length > 1), "every status has a text label");
process.exit(fail ? 1 : 0);
