// Usage: node build-agent-test.mjs <outfile> [entry, default tests/dealagent.test.ts]. With an entry, next/headers is
// also replaced (tests/mocks/next-headers.ts) so route handlers can run with a signed test session.
// Bundles tests/dealagent.test.ts with the sheet, panel, index, deal and activity modules replaced by in-memory mocks.
import { build } from "esbuild";
import path from "path";
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
// a route-handler test keeps the real modules and replaces only the sheet, the activity log and the mailer
const mocks = process.argv[3] ? { "@/lib/sheets": "sheets-routes", "@/lib/activity": "activity", "@/lib/mailer": "mailer" }
  : { "@/lib/sheets": "sheets", "@/lib/panel": "panel", "@/lib/index": "index", "@/lib/deal": "deal", "@/lib/activity": "activity", "@/lib/mailer": "mailer" };
await build({ entryPoints: [path.join(root, process.argv[3] || "tests/dealagent.test.ts")], bundle: true, platform: "node", outfile: process.argv[2] || "/tmp/dealagent.cjs", logLevel: "error",
  plugins: [{ name: "mocks", setup(b) {
    b.onResolve({ filter: /^next\/headers$/ }, () => ({ path: path.join(root, "tests/mocks/next-headers.ts") }));
    b.onResolve({ filter: /^@\/(lib|app)\// }, (a) => ({ path: mocks[a.path] ? path.join(root, "tests/mocks", mocks[a.path] + ".ts") : path.join(root, a.path.slice(2) + (/\.(json|ts|tsx)$/.test(a.path) ? "" : ".ts")) }));
  } }] });
