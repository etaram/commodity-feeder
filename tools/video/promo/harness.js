// Real Deal Desk panel, served from disk with the API answered by fixtures (public tenders, real origin prices, invented suppliers).
const { chromium } = require('playwright');
const fs = require('fs'); const path = require('path');
const D = __dirname, SITE = D + '/site', FX = D + '/fx';
const ORIGIN = 'https://desk.sinder.pro';
const fx = n => JSON.parse(fs.readFileSync(FX + '/' + n, 'utf8'));
async function open(opts = {}) {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: opts.viewport || { width: 1600, height: 900 }, deviceScaleFactor: opts.dsf || 2, locale: 'en-US' });
  await ctx.addInitScript(() => { try { localStorage.setItem('sinder-panel-lang', 'en'); localStorage.setItem('dd-lang', 'en'); localStorage.setItem('dd-ui', 'v3'); } catch (e) {} });
  const tenders = fx('tenders.json'), cm = fx('commodities.json'), sups = fx('suppliers.json');
  await ctx.route(ORIGIN + '/**', async (route) => {
    const req = route.request(); const u = new URL(req.url()); const p = u.pathname;
    const json = (o, s = 200) => route.fulfill({ status: s, contentType: 'application/json', body: JSON.stringify(o) });
    if (!p.startsWith('/api/')) {
      let f = SITE + (p === '/' ? '/index.html' : p);
      if (!fs.existsSync(f)) return route.fulfill({ status: 404, body: '' });
      const ct = f.endsWith('.js') ? 'application/javascript' : f.endsWith('.svg') ? 'image/svg+xml' : f.endsWith('.png') ? 'image/png' : 'text/html';
      return route.fulfill({ status: 200, contentType: ct, body: fs.readFileSync(f) });
    }
    let body = {}; try { body = JSON.parse(req.postData() || '{}'); } catch (e) {}
    if (p === '/api/me') return json({ ok: true, email: 'etamar@sinder.pro', name: 'Etamar', role: 'admin' });
    if (p === '/api/panel/search') { if (body.kind === 't') return json({ ok: true, values: tenders, total: 34644 }); return json({ ok: true, values: [[]], total: 0 }); }
    if (p.startsWith('/api/panel/brief')) return json({ ok: false, error: 'not in demo' }, 503);
    if (p === '/api/panel/get') return json({ ok: true, values: body.key === 'tenders' ? tenders : [[]], at: Date.now() });
    if (p === '/api/panel/commodities') { const q = (u.searchParams.get('product') || '').toLowerCase(); return json({ ok: true, ...(cm[q] || cm['']) }); }
    if (p === '/api/panel/suppliers-for') return json({ ok: true, ...sups });
    if (p === '/api/panel/label') return json({ ok: true, label: String(body.text || '').slice(0, 40) || 'white maize', verdicts: {} });
    if (p === '/api/panel/costs') return json({ ok: true, duty_pct: 0, duty_basis: 'EU internal supply, no customs duty', duty_exempt_possible: false, freight_pct: 3, freight_basis: 'road freight within the EU', other_pct: 4, other_basis: 'insurance, installation, finance', origin: 'DEU', incoterm: 'DAP', sources: [{ url: 'https://taxation-customs.ec.europa.eu', title: 'EU customs tariff' }] });
    if (p === '/api/panel/ai') { if (req.method() === 'GET') return json({ ok: true, enabled: true });
      const pr = String(body.prompt || '');
      if (/subject/.test(pr)) return json({ ok: true, text: JSON.stringify({ subject: 'Request for quotation - white maize, grade 1, 5,000 t CFR Mombasa', body: 'Dear Northfield Grains team,\n\nWe are preparing an offer for a buyer in East Africa and would like your quotation for:\n- White maize, grade 1, non-GMO, moisture max 13.5%\n- Quantity: 5,000 t, delivery CFR Mombasa\n- Packing: 50 kg PP bags\n\nPlease state the price basis (Incoterm and named place), validity, lead time, payment terms, origin and the certificates you can provide.\n\nThis is a request for information, not an order.\n\nBest regards,\nEtamar Ramot Naaman\nSinder' }) });
      return json({ ok: true, text: '' }); }
    if (p === '/api/panel/sendmail') return json({ ok: true, from: 'etamar@sinder.pro', results: (body.to || []).map(t => ({ ok: true, to: t })) });
    if (p === '/api/deal') return json({ ok: true, versions: 2, records: [{ kind: 'requirement', record_id: 'r1', version: 1, data: { item: 'white maize grade 1', mandatory: true, status: 'unknown' } }],
      readiness: { reached: 'research', next: 'ready_for_rfq', missing: ['a supplier with a sourced match and a valid contact channel'], validation_only: true, execution_approved: false },
      routes: [{ route: 'direct', verdict: 'conditional', basis: 'World Bank procurement: open to firms from all member countries', assumptions: ['registration with the buyer'], missing: ['bid security'], next: 'Read the bidding document.' },
        { route: 'agency', verdict: 'conditional', basis: 'a manufacturer may bid with an agent', assumptions: [], missing: ['a manufacturer willing to bid'], next: 'Shortlist manufacturers.' },
        { route: 'local_partner', verdict: 'conditional', basis: 'local distributor holds the registration', assumptions: [], missing: [], next: 'Find a local distributor.' },
        { route: 'sub_supply', verdict: 'conditional', basis: 'supply the contractor that wins', assumptions: [], missing: [], next: 'Track the award.' }] });
    if (opts.api) { const r = await opts.api(p, body, u); if (r !== undefined) return json(r); }
    return json({ ok: true, values: [[]], items: [] });
  });
  const page = await ctx.newPage();
  page.on('pageerror', e => console.log('pageerror', e.message.slice(0, 200)));
  return { b, ctx, page, ORIGIN };
}
module.exports = { open };
