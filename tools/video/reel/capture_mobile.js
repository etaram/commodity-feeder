const { open } = require('./harness'); const { rec } = require('./cap');
(async () => {
  const { b, page, ORIGIN } = await open({ viewport: { width: 390, height: 844 }, dsf: 2 });
  await page.goto(ORIGIN + '/'); await page.waitForTimeout(1200);
  await page.evaluate(() => document.querySelector('[data-v="tenders"]').click()); await page.waitForTimeout(2000);
  const r = rec(page, __dirname + '/mshots/tend');
  await r.snap(4);
  for (let k = 0; k < 36; k++) { await page.mouse.move(200, 600); await page.mouse.wheel(0, 30 + k * 2); await page.waitForTimeout(30); await r.snap(1); }
  for (let k = 0; k < 12; k++) { await page.mouse.wheel(0, -160); await page.waitForTimeout(30); await r.snap(1); }
  await page.evaluate(() => window.scrollTo(0, 0)); await page.waitForTimeout(300); await r.snap(3);
  r.mark({ click: await r.box('#tlist .row >> nth=0') });
  await page.click('#tlist .row >> nth=0'); await page.waitForTimeout(1500); await r.snap(4);
  for (let k = 0; k < 20; k++) { await page.mouse.wheel(0, 40); await page.waitForTimeout(30); await r.snap(1); }
  console.log('tend', r.done());
  await b.close();
})();
