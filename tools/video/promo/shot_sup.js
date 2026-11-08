const { open } = require('./harness'); const { rec, typeIn } = require('./cap');
(async () => {
  const { b, page, ORIGIN } = await open();
  await page.goto(ORIGIN + '/'); await page.waitForTimeout(1200);
  await page.evaluate(() => document.querySelector('[data-v="research"]').click()); await page.waitForTimeout(1500);
  let r = rec(page, __dirname + '/shots/sup');
  await r.snap(4); r.mark({ click: await r.box('#sr-q') });
  await typeIn(page, r, '#sr-q', 'white maize grade 1', 2);
  r.mark({ click: await r.box('#sr-form button[type=submit], #sr-form button') });
  await page.keyboard.press('Enter'); await page.waitForTimeout(1500); await r.snap(12);
  const btns = await page.evaluate(() => [...document.querySelectorAll('#sr-out button')].map(b => b.innerText.trim()).slice(0, 30)); console.log(btns.join(' | '));
  await page.screenshot({ path: __dirname + '/shots/x_sup_full.jpg', type: 'jpeg', quality: 60, fullPage: true });
  const lab = async (row, label) => { const loc = page.locator('#sr-out .sup').nth(row).locator('button', { hasText: label }); await loc.scrollIntoViewIfNeeded(); await r.snap(3); const bx = await loc.boundingBox(); r.mark({ click: { x: bx.x + bx.width / 2, y: bx.y + bx.height / 2 } }); await loc.click(); await page.waitForTimeout(500); await r.snap(10); };
  await lab(0, 'Can supply this');
  for (let k = 0; k < 16; k++) { await page.mouse.move(1000, 600); await page.mouse.wheel(0, 30); await page.waitForTimeout(25); await r.snap(1); }
  await lab(4, 'Wrong product');
  console.log('sup', r.done());
  r = rec(page, __dirname + '/shots/rfq');
  await page.evaluate(() => window.scrollTo(0, 0)); await page.waitForTimeout(300);
  for (const i of [0, 1]) { const c = page.locator('#sr' + i); await c.scrollIntoViewIfNeeded(); await c.check(); }
  const dr = page.locator('#sr-rfq'); await dr.scrollIntoViewIfNeeded(); await page.waitForTimeout(200); await r.snap(6);
  let bx = await dr.boundingBox(); r.mark({ click: { x: bx.x + bx.width / 2, y: bx.y + bx.height / 2 } });
  await dr.click(); await page.waitForTimeout(2500);
  await page.evaluate(() => document.querySelector('#m-sub')?.closest('.section')?.scrollIntoView({ block: 'start' })); await page.waitForTimeout(400); await r.snap(18);
  const sb = page.locator('#m-send'); console.log('send', await sb.count());
  if (await sb.count()) { await sb.scrollIntoViewIfNeeded(); await r.snap(4); bx = await sb.boundingBox(); r.mark({ click: { x: bx.x + bx.width / 2, y: bx.y + bx.height / 2 } });
    await sb.click(); await page.waitForTimeout(500); await r.snap(14); bx = await sb.boundingBox(); r.mark({ click: { x: bx.x + bx.width / 2, y: bx.y + bx.height / 2 } }); await sb.click(); await page.waitForTimeout(800); await r.snap(16); }
  await page.screenshot({ path: __dirname + '/shots/x_rfq_full.jpg', type: 'jpeg', quality: 60, fullPage: true });
  console.log('rfq', r.done());
  await b.close();
})();
