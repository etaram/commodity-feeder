import assert from "node:assert/strict";
import { joinRows, pinkSheet } from "@/lib/commodities";

const norm: Record<string, string>[] = [
  { id: "L0033", hs6: "1001", commodity: "Wheat (HRW) - KCBT futures", product: "Wheat (HRW)", grade: "HRW", price_usd: "6.365", unit: "USD/bu", unit_canonical: "USD/bu", price_usd_t: "233.874", conversion: "1 bu wheat = 27.2155 kg", price_type_norm: "futures", physical: "false", timestamp: "2026-11-05" },
  { id: "H0533", hs6: "100119", commodity: "Cereals; wheat and meslin, durum wheat", product: "Cereals; wheat and meslin, durum wheat", grade: "Durum", price_usd: "306", unit: "USD/t", unit_canonical: "USD/t", price_usd_t: "306", price_type_norm: "spot", physical: "true", timestamp: "2026-11-01" },
];
const stats: Record<string, string>[] = [
  { id: "L0033", freq: "daily", n_points: "9", chg_1w_pct: "-1.2", vol_30d: "", season_idx: "", season_note: "1 months of data, 24 needed", anomaly: "", basis: "daily 2026-10-25..2026-11-05, 9 points" },
  { id: "WB:Wheat, US HRW", name: "Wheat, US HRW ($/mt)", last_date: "2026-10-01", last_price: "317", chg_1m_pct: "-8.6", season_idx: "[1,1,1,1,1,1,1,1,1,1,1,1]", anomaly: "", basis: "World Bank Pink Sheet monthly" },
];
const all = joinRows(norm, stats);
assert.equal(all.length, 2);
assert.equal(all[0].physical, false);
assert.equal(all[0].price_type, "futures");
assert.equal(all[0].price_usd_t, 233.874);
assert.equal(all[0].chg_1w_pct, -1.2);
assert.equal(all[0].vol_30d, null);
assert.equal(all[1].physical, true);
assert.equal(all[1].n_points, 0, "no stats row gives empty stats, not an error");
assert.equal(joinRows(norm, stats, { product: "wheat hrw" }).length, 1);
assert.equal(joinRows(norm, stats, { hs6: "1001" }).length, 2);
assert.equal(joinRows(norm, stats, { hs6: "100119" }).length, 1);
const wb = pinkSheet(stats);
assert.equal(wb.length, 1);
assert.equal(wb[0].season_idx?.length, 12);
console.log("commodities.test ok");
