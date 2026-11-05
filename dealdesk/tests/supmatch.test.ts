// Regression cases from the 5 November 2026 review (spec section 4). Run: npx esbuild ... && node
import { classifyMatch, familiesFor, termRe } from "@/lib/supmatch";
let fail = 0;
const T = (q: string, concepts: string[][], s: any, want: string) => {
  const m = classifyMatch(s, concepts.map((c) => c.map(termRe)), concepts.map(() => []), q, familiesFor(q));
  const ok = m.bucket === want; if (!ok) fail++;
  console.log(`${ok ? "ok  " : "FAIL"} [${q}] ${s.n}: ${m.bucket} (want ${want}) - ${m.why}${m.conflicts.length ? " | " + m.conflicts.join("; ") : ""}`);
};
// A white maize
T("white maize", [["white"], ["maize", "corn"]], { n: "Corning Incorporated", p: "glass and ceramics", ty: "goods supplier" }, "plausible");
T("white maize", [["maize", "corn"]], { n: "Corning Incorporated", p: "specialty glass", ty: "goods supplier" }, "plausible");
T("white maize", [["maize", "corn"]], { n: "Cornerstone Software", p: "lottery management systems", ty: "works/services" }, "plausible");
T("white maize", [["white"], ["maize", "corn"]], { n: "Grain Co", p: "white maize, yellow maize, sorghum exporter", ty: "goods supplier", web: "x" }, "supported");
T("white maize", [["maize", "corn"]], { n: "Mill Co", p: "maize flour and corn starch", ty: "goods supplier" }, "related");
// B urea
T("granular urea fertilizer", [["urea"], ["fertilizer"]], { n: "Derma Labs", p: "urea cream 10% moisturizing lotion, fertilizer-free", ty: "goods supplier" }, "incompatible");
T("granular urea fertilizer", [["urea"]], { n: "Fertiglobe", p: "granular urea, ammonia, nitrogen fertilizers", ty: "goods supplier", web: "x" }, "supported");
// C diesel generator
T("diesel generator", [["diesel"], ["generator", "genset"]], { n: "Fresh Foods Ltd", p: "frozen fish", hd: "", sp: "reefer genset diesel generator for refrigerated containers", ty: "goods supplier" }, "related");
T("diesel generator", [["diesel"], ["generator", "genset"]], { n: "Power Gen Co", p: "diesel generators 20-2000 kVA", ty: "goods supplier", web: "x" }, "supported");
// D hot rolled coil
T("hot rolled steel coil", [["hot rolled"], ["steel"], ["coil"]], { n: "Shoe Co", p: "safety shoes with steel toe coil", hd: "flat-rolled products of iron hot rolled", ty: "goods supplier" }, "incompatible");
T("hot rolled steel coil", [["hot rolled"], ["steel"], ["coil"]], { n: "Mill A", p: "cold rolled steel coil, wire rod", ty: "goods supplier" }, "related");
T("hot rolled steel coil", [["hot rolled"], ["steel"], ["coil"]], { n: "Mill B", p: "hot rolled steel coil HRC, plates", ty: "goods supplier", web: "x" }, "supported");
// E power transformer
T("power transformer", [["power transformer"]], { n: "Instr Co", p: "instrument transformers and current transformers; power transformer protection", ty: "goods supplier" }, "related");
T("power transformer", [["power transformer"]], { n: "Trafo AG", p: "power transformers up to 500 MVA, oil-immersed", ty: "goods supplier", web: "x" }, "supported");
T("power transformer", [["power transformer"]], { n: "EPC Build", sp: "supply and installation of power transformer, substation construction", ty: "works/services" }, "related");
// F PE pipe
T("PE pipes and fittings", [["pe pipe", "polyethylene pipe", "hdpe pipe"]], { n: "Rail Steel", p: "rails, steel pipe fittings", ty: "goods supplier" }, "incompatible");
T("PE pipes and fittings", [["pe pipe", "polyethylene pipe", "hdpe pipe"]], { n: "Plastic Pipes Ltd", p: "HDPE pipe PE100, polyethylene pipe fittings", ty: "goods supplier", web: "x" }, "supported");
console.log(fail ? `${fail} FAILED` : "all passed"); process.exit(fail ? 1 : 0);
