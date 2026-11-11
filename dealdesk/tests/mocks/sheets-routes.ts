// Sheet stand-in for route-handler tests: every export of the real module, with the reads and writes the client
// routes use replaced by the in-memory tabs. Without credentials the real module's own reads return null (no network).
export * from "../../lib/sheets";
export { TABS, appendRow, readRanges } from "./sheets";
