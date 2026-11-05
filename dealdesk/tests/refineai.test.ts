import { validateReading } from "@/lib/refineai";
let n = 0, bad = 0; const ok = (c: boolean, m: string) => { n++; if (!c) { bad++; console.log("FAIL", m); } };
ok(validateReading({ sector: "Agriculture & food", role: "manufacturer", belongs: "yes", note: "makes urea" }).sector === "Agriculture & food", "valid sector kept");
ok(validateReading({ sector: "Fertilizers", role: "maker", belongs: "probably" }).sector === "" && validateReading({ role: "maker" }).role === "" && validateReading({ belongs: "probably" }).belongs === "unsure", "invented values dropped");
ok(!validateReading({ note: "a — b" }).note.includes("—"), "no em-dash");
ok(validateReading(null).belongs === "unsure", "garbage is unsure");
console.log(`${n - bad}/${n} refine ai checks pass`); if (bad) process.exit(1);
