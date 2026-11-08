const { open } = require('./harness'); const { rec, typeIn } = require('./cap');
(async () => {
  const { b, page, ORIGIN } = await open();
  await page.goto(ORIGIN + '/'); await page.waitForTimeout(1200);
  await page.evaluate(() => document.querySelector('[data-v="tenders"]').click()); await page.waitForTimeout(2000);
  let r = rec(page, __dirname + '/shots/tlist');
  await r.snap(8);
  for (let k = 0; k < 40; k++) { await page.mouse.move(700, 700); await page.mouse.wheel(0, 22); await page.waitForTimeout(25); await r.snap(1); }
  for (let k = 0; k < 10; k++) { await page.mouse.wheel(0, -88); await page.waitForTimeout(25); await r.snap(1); }
  await page.evaluate(() => window.scrollTo(0, 0)); await page.waitForTimeout(300); await r.snap(4);
  r.mark({ click: await r.box('#tlist .row >> nth=0') });
  await page.click('#tlist .row >> nth=0'); await page.waitForTimeout(1800); await r.snap(16);
  console.log('tlist', r.done());
  // estimate
  r = rec(page, __dirname + '/shots/est');
  const est = await page.evaluate(() => { const e = document.querySelector('#e-cost'); if (!e) return null; e.closest('.section').scrollIntoView({ block: 'start' }); return true; });
  console.log('est', est); await page.waitForTimeout(500);
  await r.snap(4);
  await page.fill('#e-cost', ''); await typeIn(page, r, '#e-cost', '150000000', 1);
  await page.waitForTimeout(300); await r.snap(4);
  if (await page.$('#e-find')) { r.mark({ click: await r.box('#e-find') }); await page.click('#e-find'); await page.waitForTimeout(1200); await r.snap(8); }
  await page.evaluate(() => document.querySelector('#e-slide')?.scrollIntoView({ block: 'center' })); await page.waitForTimeout(300); await r.snap(4);
  const rng = await page.evaluate(() => { const i = document.querySelector('#e-bid'); return i ? { min: +i.min, max: +i.max, v: +i.value } : null; }); console.log(rng);
  if (rng) {
    const best = 182793000, seq = []; const span = rng.max - rng.min;
    for (let k = 0; k <= 45; k++) { const f = k / 45; seq.push(rng.min + span * (0.03 + 0.85 * (f < .5 ? 2 * f * f : 1 - (-2 * f + 2) ** 2 / 2))); }
    const top = seq[seq.length - 1]; for (let k = 1; k <= 25; k++) { const f = k / 25; seq.push(top + (best - top) * (1 - (1 - f) ** 3)); }
    for (const v of seq) { await page.evaluate(v => { const i = document.querySelector('#e-bid'); i.value = String(Math.round(v)); i.dispatchEvent(new Event('input')); }, v); await r.snap(1, { knob: await r.box('#e-bid') }); }
    await page.evaluate(() => { const i = document.querySelector('#e-bid'); const best = document.querySelector('#e-best'); }); await r.snap(18);
  }
  console.log('est', r.done());
  await page.screenshot({ path: __dirname + '/shots/x_est_full.jpg', type: 'jpeg', quality: 60, fullPage: true });
  await b.close();
})();
