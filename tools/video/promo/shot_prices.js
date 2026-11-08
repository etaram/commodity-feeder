const { open } = require('./harness'); const { rec, typeIn } = require('./cap');
(async () => {
  const { b, page, ORIGIN } = await open();
  await page.goto(ORIGIN + '/'); await page.waitForTimeout(1500);
  await page.evaluate(() => document.querySelector('[data-v="markets"]').click()); await page.waitForTimeout(1500);
  const r = rec(page, __dirname + '/shots/prices');
  const inp = '#cm-q, #cm-box input[type=search], #cm-box input';
  const sel = await page.evaluate(() => { const i = document.querySelector('#cm-box input'); return i ? '#' + i.id : ''; }); console.log('input', sel);
  await page.fill(sel, ''); await page.evaluate(s => { const i = document.querySelector(s); i.value=''; i.dispatchEvent(new Event('input')); }, sel); await page.waitForTimeout(300);
  await r.snap(6); r.mark({ click: await r.box(sel) });
  await typeIn(page, r, sel, 'palm oil', 2);
  await page.keyboard.press('Enter'); await page.waitForTimeout(1200); await r.snap(10);
  await page.evaluate(s => { const i = document.querySelector(s); i.select(); }, sel);
  await page.keyboard.press('Backspace');
  await typeIn(page, r, sel, 'coffee', 2);
  await page.keyboard.press('Enter'); await page.waitForTimeout(1200); await r.snap(10);
  for (let k = 0; k < 30; k++) { await page.mouse.move(1000, 600); await page.mouse.wheel(0, 18); await page.waitForTimeout(30); await r.snap(1); }
  console.log('frames', r.done()); await b.close();
})();
