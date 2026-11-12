// Runs every test in tests/ and prints one line per file. Usage: npm test
// dealagent.test.ts needs the in-memory mocks (tests/build-agent-test.mjs); the rest bundle with the "@" alias.
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readdirSync } from "node:fs";
import os from "node:os";
import path from "node:path";
const here = path.dirname(new URL(import.meta.url).pathname), root = path.resolve(here, "..");
const out = mkdtempSync(path.join(os.tmpdir(), "ddtest-"));
const esbuild = path.join(root, "node_modules/.bin/esbuild");
let failed = 0; const rows = [];
for (const f of readdirSync(here).filter((x) => /\.test\.(ts|mjs)$/.test(x)).sort()) {
  const js = path.join(out, f.replace(/\.(ts|mjs)$/, ".cjs"));
  let r;
  try {
    if (f.endsWith(".mjs")) r = spawnSync("node", [path.join(here, f)], { cwd: root, encoding: "utf8" });
    else {
      if (f === "dealagent.test.ts") execFileSync("node", [path.join(here, "build-agent-test.mjs"), js], { cwd: root, stdio: "pipe" });
      else if (f === "draftmailoff.test.ts") execFileSync("node", [path.join(here, "build-agent-test.mjs"), js, "tests/" + f, "realmail"], { cwd: root, stdio: "pipe" });
      else if (f === "isolation.test.ts" || f === "approver-route.test.ts" || f === "draftsend.test.ts") execFileSync("node", [path.join(here, "build-agent-test.mjs"), js, "tests/" + f, "isolation"], { cwd: root, stdio: "pipe" });
      else if (f === "clients-scope.test.ts" || f === "runner-api.test.ts" || f === "aicap.test.ts") execFileSync("node", [path.join(here, "build-agent-test.mjs"), js, "tests/" + f], { cwd: root, stdio: "pipe" });
      else execFileSync(esbuild, [path.join(here, f), "--bundle", "--platform=node", "--format=cjs", `--alias:@=${root}`, `--outfile=${js}`, "--log-level=error"], { cwd: root, stdio: "pipe" });
      r = spawnSync("node", [js], { cwd: root, encoding: "utf8", env: { ...process.env, AUTH_SECRET: process.env.AUTH_SECRET || "test-secret" } });
    }
  } catch (e) { r = { status: 1, stdout: "", stderr: String(e.stderr || e.message) }; }
  const text = (r.stdout || "") + (r.stderr || "");
  const fails = (text.match(/^FAIL/gm) || []).length, oks = (text.match(/^ok /gm) || []).length;
  const bad = r.status !== 0 || fails > 0;
  if (bad) failed++;
  rows.push(`${bad ? "FAIL" : "ok  "} ${f.padEnd(28)} ${oks} ok, ${fails} failed${bad ? "\n" + text.split("\n").filter((l) => /FAIL|Error|error/.test(l)).slice(0, 6).map((l) => "       " + l.slice(0, 200)).join("\n") : ""}`);
}
console.log(rows.join("\n"));
console.log(failed ? `\n${failed} test file(s) failing` : "\nall test files pass");
process.exit(failed ? 1 : 0);
