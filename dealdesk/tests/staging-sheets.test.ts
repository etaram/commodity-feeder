import assert from "node:assert/strict";
import { ENGINE_SHEET, sheetFor, writeRefused } from "../lib/sheets";

const API = "https://sheets.googleapis.com/v4/spreadsheets";
// production settings: state tabs go to the state sheet, everything else to the engine sheet, nothing is refused
process.env.STATE_SHEET_ID = "LIVE_STATE"; delete process.env.STATE_TABS_EXTRA; delete process.env.SHEETS_READONLY_IDS;
assert.equal(sheetFor("Send Guard"), "LIVE_STATE");
assert.equal(sheetFor("Suppression"), ENGINE_SHEET);
assert.equal(writeRefused("POST", `${API}/${ENGINE_SHEET}/values/x:append`), "");
// staging settings
process.env.STATE_SHEET_ID = "COPY_STATE"; process.env.STATE_TABS_EXTRA = "Campaigns, Suppression ,Outreach Log";
process.env.SHEETS_READONLY_IDS = `${ENGINE_SHEET},LIVE_STATE`;
assert.equal(sheetFor("Suppression"), "COPY_STATE", "an extra tab moves to the copy");
assert.equal(sheetFor("Send Guard"), "COPY_STATE");
assert.equal(sheetFor("Suppliers"), ENGINE_SHEET, "data tabs are still read from the engine sheet");
assert.equal(writeRefused("GET", `${API}/${ENGINE_SHEET}/values:batchGet?ranges=a`), "", "reads are allowed");
assert.equal(writeRefused("POST", `${API}/${ENGINE_SHEET}/values/x:append?valueInputOption=RAW`), ENGINE_SHEET, "append to the engine sheet is refused");
assert.equal(writeRefused("POST", `${API}/${ENGINE_SHEET}:batchUpdate`), ENGINE_SHEET, "adding a tab to the engine sheet is refused");
assert.equal(writeRefused("PUT", `${API}/LIVE_STATE/values/x`), "LIVE_STATE", "the live state sheet is refused");
assert.equal(writeRefused("POST", `${API}/COPY_STATE/values/x:append`), "", "the copy takes writes");
console.log("ok staging routing and write guard");
