const { chromium } = require('playwright'); const fs = require('fs');
const axe = fs.readFileSync(__dirname + '/node_modules/axe-core/axe.min.js', 'utf8');
(async () => { const b = await chromium.launch(); const d = __dirname; const all = {};
  for (const [view, lang] of [["today","he"],["forme","he"],["tenders","en"],["research","en"],["companies","he"]]) {
    const p = await (await b.newContext({ viewport: {width:1440,height:900} })).newPage();
    await p.goto('file://' + d + '/index.html'); await p.evaluate(l => localStorage.setItem('sinder-panel-lang', l), lang);
    await p.evaluate(v => { location.hash = v; }, view); await p.reload(); await p.waitForTimeout(1300);
    if (view === "research") { await p.fill('#sr-q', 'ductile iron pipes'); await p.click('#sr-form button[type=submit]'); await p.waitForTimeout(600); }
    await p.addScriptTag({ content: axe });
    const r = await p.evaluate(async () => (await axe.run(document, { runOnly: ['wcag2a','wcag2aa','wcag21aa','wcag22aa','best-practice'] })).violations.map(v => ({ id: v.id, impact: v.impact, n: v.nodes.length, ex: v.nodes.slice(0,2).map(n => n.target.join(' ')) })));
    for (const v of r) { const k = v.id; all[k] = all[k] || { impact: v.impact, n: 0, views: [], ex: v.ex }; all[k].n += v.n; all[k].views.push(view); }
  }
  for (const [k, v] of Object.entries(all).sort((a, b) => b[1].n - a[1].n)) console.log(`${v.impact}\t${k}\t${v.n}\t${v.views.join(',')}\t${v.ex.join(' | ').slice(0,140)}`);
  await b.close(); })();
