// Usage: node build-agent-test.mjs <outfile> [entry, default tests/dealagent.test.ts]. With an entry, next/headers is
// also replaced (tests/mocks/next-headers.ts) so route handlers can run with a signed test session.
// Bundles tests/dealagent.test.ts with the sheet, panel, index, deal and activity modules replaced by in-memory mocks.
import { build } from "esbuild";
import path from "path";
import { existsSync } from "fs";
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
// a route-handler test keeps the real modules and replaces only the sheet, the activity log and the mailer
// "isolation" (4th argument): the whole app runs for real over an in-memory sheet and a recording model stand-in; the
// activity log is the real module (its rows are part of what is tested), and lib files that import "./sheets" get the
// same in-memory sheet.
// "realmail": as "isolation", but with the REAL mailer (lib/mailer.ts), for tests that prove AGENT_MAIL_LIVE=0 opens no connection.
const realmail = process.argv[4] === "realmail";
const isolation = process.argv[4] === "isolation" || realmail;
const mocks = realmail ? { "@/lib/sheets": "sheets-isolation", "@/lib/anthropic": "anthropic" } : isolation ? { "@/lib/sheets": "sheets-isolation", "@/lib/anthropic": "anthropic", "@/lib/mailer": "mailer" } : process.argv[3] ? { "@/lib/sheets": "sheets-routes", "@/lib/activity": "activity", "@/lib/mailer": "mailer" }
  : { "@/lib/sheets": "sheets", "@/lib/panel": "panel", "@/lib/index": "index", "@/lib/deal": "deal", "@/lib/activity": "activity", "@/lib/mailer": "mailer" };
// "@/lib/x" is lib/x.ts, or lib/x/index.ts when x is a folder
const file = (rel) => { const p = path.join(root, rel); return /\.(json|ts|tsx)$/.test(rel) ? p : existsSync(p + ".ts") ? p + ".ts" : path.join(p, "index.ts"); };
await build({ entryPoints: [path.join(root, process.argv[3] || "tests/dealagent.test.ts")], bundle: true, platform: "node", outfile: process.argv[2] || "/tmp/dealagent.cjs", logLevel: "error",
  plugins: [{ name: "mocks", setup(b) {
    if (isolation) b.onResolve({ filter: /^\.\/sheets$/ }, (a) => (a.importer.startsWith(path.join(root, "lib") + path.sep) ? { path: path.join(root, "tests/mocks/sheets-isolation.ts") } : null));
    b.onResolve({ filter: /^next\/headers$/ }, () => ({ path: path.join(root, "tests/mocks/next-headers.ts") }));
    b.onResolve({ filter: /^@\/(lib|app)\// }, (a) => ({ path: mocks[a.path] ? path.join(root, "tests/mocks", mocks[a.path] + ".ts") : file(a.path.slice(2)) }));
  } }] });
