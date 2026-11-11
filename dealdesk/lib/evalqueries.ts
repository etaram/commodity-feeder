// The fixed supplier-search benchmark query set (tools/eval-suppliers.ts) and the verification agent's fallback
// demand when people ran fewer product searches than a run can check.
export const QUERIES = [
  "white maize", "granular urea fertilizer", "diesel generator", "hot rolled steel coil", "power transformer",
  "PE pipes and fittings", "ammonia", "frozen tuna", "canned tuna", "ammunition", "body armour", "night vision",
  "solar panels", "lithium battery storage", "distribution transformer", "copper cable", "steel rebar", "cement",
  "bitumen", "jet fuel", "LPG", "wheat", "rice", "sugar", "sunflower oil", "milk powder", "HDPE pipe",
  "ductile iron pipe", "water meters", "reverse osmosis", "UPS uninterruptible power supply", "data center cooling",
  "server racks", "X-ray machine", "patient monitors", "surgical gloves", "excavator", "fire trucks",
  "sidamo coffee producer", "jasmine rice", "ethiopian sesame", "raw cashew nuts", "green coffee exporter", "basmati rice",
];

// The blind relevance set (tools/eval-suppliers.ts --blind, scored by tools/eval_score.py): 40 requests written the
// way a buyer types them into supplier research. 20 state a concrete specification (grade, capacity, standard,
// voltage, size), 14 name the product only, 6 are deliberately ambiguous single words. The ids are stable: labels
// are keyed by (id, rank), so a request is never edited in place - retire the id and add a new one.
// QUERIES above stays as it is (the verification agent's fallback demand reads it).
export type EvalQuery = { id: string; text: string; product: string; spec: boolean; ambiguous: boolean };
const E = (id: string, text: string, product: string, kind: "" | "spec" | "ambiguous" = ""): EvalQuery =>
  ({ id, text, product, spec: kind === "spec", ambiguous: kind === "ambiguous" });
export const EVAL_SET: EvalQuery[] = [
  E("Q01", "white maize for human consumption", "grains"),
  E("Q02", "milling wheat 12.5% protein", "grains", "spec"),
  E("Q03", "long grain white rice 5% broken", "grains", "spec"),
  E("Q04", "refined white sugar ICUMSA 45", "sugar", "spec"),
  E("Q05", "refined sunflower oil supplier", "edible oils"),
  E("Q06", "RBD palm olein CP10 in 20 litre jerry cans", "edible oils", "spec"),
  E("Q07", "granular urea 46% nitrogen", "fertilizers", "spec"),
  E("Q08", "anhydrous ammonia supplier", "fertilizers"),
  E("Q09", "DAP fertilizer 18-46-0", "fertilizers", "spec"),
  E("Q10", "Portland cement CEM I 42.5N", "cement", "spec"),
  E("Q11", "deformed steel rebar B500B 12 mm", "steel rebar", "spec"),
  E("Q12", "hot rolled steel coil manufacturer", "steel coil"),
  E("Q13", "copper power cable XLPE 11 kV", "copper cable", "spec"),
  E("Q14", "Jet A-1 aviation fuel supplier", "jet fuel"),
  E("Q15", "LPG bulk supply", "LPG"),
  E("Q16", "bitumen 60/70 penetration grade", "bitumen", "spec"),
  E("Q17", "diesel generator 500 kVA 50 Hz", "diesel generators", "spec"),
  E("Q18", "monocrystalline solar panels 550 W", "solar panels", "spec"),
  E("Q19", "power transformer 132/33 kV 40 MVA", "power transformers", "spec"),
  E("Q20", "distribution transformer manufacturer", "distribution transformers"),
  E("Q21", "lithium battery energy storage system 1 MWh", "battery storage", "spec"),
  E("Q22", "HDPE pipe PE100 PN16 110 mm", "PE pipes", "spec"),
  E("Q23", "ductile iron pipe DN300 ISO 2531", "ductile iron pipe", "spec"),
  E("Q24", "cold water meters for a water utility", "water meters"),
  E("Q25", "reverse osmosis membrane 8040 brackish water", "reverse osmosis membranes", "spec"),
  E("Q26", "containerized reverse osmosis desalination system", "reverse osmosis systems"),
  E("Q27", "online UPS 10 kVA", "UPS", "spec"),
  E("Q28", "42U server rack", "server racks", "spec"),
  E("Q29", "data center precision cooling units", "cooling"),
  E("Q30", "digital X-ray machine for a hospital", "medical devices"),
  E("Q31", "patient monitors for intensive care", "medical devices"),
  E("Q32", "sterile latex surgical gloves", "surgical gloves"),
  E("Q33", "20 ton crawler excavator", "excavators", "spec"),
  E("Q34", "fire trucks manufacturer", "fire trucks"),
  E("Q35", "urea", "fertilizers", "ambiguous"),
  E("Q36", "generator", "diesel generators", "ambiguous"),
  E("Q37", "membrane", "reverse osmosis membranes", "ambiguous"),
  E("Q38", "pipes", "PE pipes", "ambiguous"),
  E("Q39", "cable", "copper cable", "ambiguous"),
  E("Q40", "oil", "edible oils", "ambiguous"),
];
