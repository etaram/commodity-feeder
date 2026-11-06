// Bundles tests/dealagent.test.ts with the sheet, panel, index, deal and activity modules replaced by in-memory mocks.
import { build } from "esbuild";
import path from "path";
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const mocks = { "@/lib/sheets": "sheets", "@/lib/panel": "panel", "@/lib/index": "index", "@/lib/deal": "deal", "@/lib/activity": "activity" };
await build({ entryPoints: [path.join(root, "tests/dealagent.test.ts")], bundle: true, platform: "node", outfile: process.argv[2] || "/tmp/dealagent.cjs", logLevel: "error",
  plugins: [{ name: "mocks", setup(b) {
    b.onResolve({ filter: /^@\/lib\// }, (a) => ({ path: mocks[a.path] ? path.join(root, "tests/mocks", mocks[a.path] + ".ts") : path.join(root, a.path.slice(2) + ".ts") }));
  } }] });
