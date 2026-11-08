// helpers for frame capture
const fs = require('fs');
function rec(page, dir) {
  fs.rmSync(dir, { recursive: true, force: true }); fs.mkdirSync(dir, { recursive: true });
  let n = 0; const meta = [];
  return {
    async snap(times = 1, info) { const buf = await page.screenshot({ type: 'jpeg', quality: 88 }); for (let i = 0; i < times; i++) { fs.writeFileSync(`${dir}/${String(n).padStart(4, '0')}.jpg`, buf); meta.push(info || null); n++; } },
    async box(sel) { const b = await page.locator(sel).first().boundingBox(); return b ? { x: b.x + b.width / 2, y: b.y + b.height / 2, w: b.width, h: b.height } : null; },
    mark(info) { meta[meta.length - 1] = Object.assign({}, meta[meta.length - 1] || {}, info); },
    done() { fs.writeFileSync(`${dir}/meta.json`, JSON.stringify({ frames: n, meta })); return n; },
  };
}
async function typeIn(page, r, sel, text, perChar = 2) {
  await page.click(sel); for (const ch of text) { await page.keyboard.type(ch); await r.snap(perChar); }
}
module.exports = { rec, typeIn };
