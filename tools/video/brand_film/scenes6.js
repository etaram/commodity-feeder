// v6: pain -> fix. Hook on the lost deal, the noise, then one fix per pain with real proof from the system.
const BEAT = TL.beat, T5 = TL.t5;
const RED = '#C62D23';
const AGENTS = [['Tender hunter', 'TED (EU)'], ['Tender hunter', 'PNCP Brazil'], ['Award tracker', 'World Bank'], ['Trade records', 'customs data'], ['Registry check', 'LEI registry'], ['Sanctions screen', 'sanctions lists'], ['Price scout', 'UCDA Uganda'], ['News watch', 'GDELT'], ['Supplier finder', 'Tridge directory'], ['Tender hunter', 'Prozorro Ukraine'], ['Award tracker', 'SECOP II Colombia'], ['Price scout', 'MPOB Malaysia'], ['Tender hunter', 'Find a Tender UK'], ['Tender hunter', 'Etimad Saudi Arabia']];
const VERBS = ['reading', 'translating', 'scoring', 'matching', 'checking', 'filing'];
const check = (k, sz = 56, col = '#22A565') => `<div style="width:${sz}px;height:${sz}px;border-radius:50%;background:${col};display:flex;align-items:center;justify-content:center;flex:none;transform:scale(${bk(k)});opacity:${cl(k * 2)}"><svg width="${sz * 0.58}" height="${sz * 0.58}" viewBox="0 0 24 24"><path d="M4 12.5l5 5L20 6.5" fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/></svg></div>`;
const lostCard = (stampK) => `<div style="background:#fff;border-radius:40px;padding:44px 46px;box-shadow:0 40px 90px rgba(0,0,0,.35);position:relative">
  <div style="display:flex;align-items:center;gap:16px">${flag('fr', 56)}<span style="font:600 32px Plex;color:#5F6B80">Resah · France · public tender</span></div>
  <div style="font:700 66px/1.05 Plex;color:#0B1324;margin-top:16px">Ophthalmology equipment</div>
  <div style="display:flex;gap:16px;margin-top:28px"><div style="flex:1;background:#F1F4F9;border-radius:20px;padding:18px 22px"><b style="font:700 58px/1 Barlow;color:#0B1324">$182.9M</b><div style="font:500 26px Plex;color:#6B7891;margin-top:4px">stated value</div></div><div style="flex:1;background:#F1F4F9;border-radius:20px;padding:18px 22px"><b style="font:700 58px/1 Barlow;color:#0B1324">26 days</b><div style="font:500 26px Plex;color:#6B7891;margin-top:4px">to deadline</div></div></div>
  <div class="abs" style="left:50%;top:52%;transform:translate(-50%,-50%) rotate(-9deg) scale(${lerp(2.2, 1, ex(stampK))});opacity:${cl(stampK * 4)};border:10px solid ${RED};color:${RED};font:700 112px/1 Barlow;letter-spacing:6px;padding:14px 34px;border-radius:20px;background:rgba(255,255,255,.88);white-space:nowrap">MISSED</div></div>`;
// a pain question that gets struck through when the fix lands, then the fix headline
function painFix(q, fix, tq, tf, lt0) {
  const qk = ex(p(lt0, tq, tq + 0.25)), st = io(p(lt0, tf - 0.05, tf + 0.25)), fk = ex(p(lt0, tf, tf + 0.3));
  return `<div class="abs" style="left:80px;right:80px;top:150px"><div style="position:relative;display:inline-block;font:700 92px/1 Barlow;color:${mix('#0B1324', '#9AA6BA', st)};opacity:${qk};filter:blur(${(1 - qk) * 6}px)">${q}<i class="abs" style="left:0;top:52%;height:9px;width:${st * 100}%;background:${RED};border-radius:5px"></i></div>
    <div style="font:700 128px/1 Barlow;color:${C.ink};margin-top:14px;opacity:${fk};filter:blur(${(1 - fk) * 8}px)">${fix}</div></div>`;
}

function render(t) {
  const sc = Object.values(SC).find((s) => t >= s.t0 && t < s.t1) || SC.cta; const lt = t - sc.t0, D = sc.t1 - sc.t0;
  let ground = C.navy, html = '', mapO = null; phone(0, 0, 1, 0); $('root').style.setProperty('--accent', C.gold); $('black').style.opacity = 0;
  const L = (k) => TL.lines[k].t - sc.t0;

  if (sc.id === 'hook') {
    ground = '#14080A'; const st = p(t, wt('v1', /^lost/) - 0.05, wt('v1', /^lost/) + 0.3); const sk = t < 0.05 ? 1 : st; const nv = ex(p(t, wt('v1', /^never/) - 0.05, wt('v1', /^never/) + 0.3));
    html += `<div class="abs" style="left:80px;right:80px;top:170px;font:700 150px/0.95 Barlow;color:#fff">You never<br><span style="color:${RED === '#C62D23' ? '#FF5A4E' : RED};opacity:${0.35 + 0.65 * nv}">saw it.</span></div>
      <div class="abs" style="left:60px;width:960px;top:${lerp(640, 620, ex(p(lt, 0, 0.6)))}px">${lostCard(sk)}</div>
      <div class="abs" style="left:80px;top:1260px;font:600 40px Plex;color:#C9A9A6;opacity:${p(lt, 0.6, 1)}">Awarded. To someone who saw it first.</div>`;
  } else if (sc.id === 'noise') {
    const c1 = wt('v2', /^thousand/) + 0.25, lv = wt('v2', /^live/), nf = wt('v2', /^ninety/); const n = lerp(0, 34644, ex(p(t, sc.t0, c1)));
    const zo = pin(p(lt, D - 0.01, D)); mapO = { cx: 1085, my0: 470, cy: 1300, z: lerp(2.9, 3.1, io(p(lt, 0, D))), alpha: 1, reveal: lerp(0.3, 1.25, ex(p(t, sc.t0, nf + 0.4))), live: p(t, lv, lv + 0.45) };
    const lk = ex(p(t, lv - 0.05, lv + 0.25)), k195 = ex(p(t, nf - 0.1, nf + 0.25));
    html += `<div class="abs" style="left:80px;top:170px"><div class="num" style="font:700 300px/0.9 Barlow;letter-spacing:-6px;color:${C.gold}">${fmt(n)}</div>
      <div style="display:flex;align-items:center;gap:22px;margin-top:20px"><span style="font:600 50px Plex;color:#fff">tenders</span><span style="display:inline-flex;align-items:center;gap:12px;background:${C.green};color:#fff;font:700 40px Plex;letter-spacing:2px;padding:8px 22px;border-radius:14px;opacity:${lk};transform:scale(${lerp(1.6, 1, lk)})"><i style="width:16px;height:16px;border-radius:50%;background:#fff"></i>LIVE</span></div>
      <div style="margin-top:30px;opacity:${k195};filter:blur(${(1 - k195) * 6}px)"><span class="num" style="font:700 130px/1 Barlow;color:#fff">195</span><span style="font:600 44px Plex;color:#9FB1D3;margin-left:18px">countries</span></div></div>`;
  } else if (sc.id === 'chaos') {
    ground = C.navy; const W3 = [[/^portals/, 'Different portals'], [/^languages/, 'Different languages'], [/^Endless/, 'Endless PDFs']];
    let ci = 0; W3.forEach(([r], i) => { if (t >= wt('v3', r) - 0.35) ci = i; });
    const PORTALS = ['TED', 'SAM.gov', 'PNCP', 'SECOP II', 'Prozorro', 'Etimad', 'AusTender', 'CanadaBuys', 'BOAMP', 'Find a Tender', 'UNGM', 'DGCP', 'MyProcurement', 'simap.ch', 'mr.gov.il', 'eTenders'];
    const LANG = ['Avis de marché', 'Aviso de licitação', 'Licitación pública', 'Оголошення про закупівлю', 'مناقصة عامة', 'Ausschreibung', 'Bando di gara', 'Przetarg', 'Ihale ilanı', 'Zabun', 'מכרז פומבי', '招标公告'];
    let field = ''; const items = ci === 0 ? PORTALS : ci === 1 ? LANG : null; const t0c = wt('v3', W3[ci][0]) - 0.35;
    if (items) items.forEach((s, i) => { const a = i * 2.399 + ci, r = 230 + ((i * 97) % 300); const k = ex(p(t, t0c + i * 0.03, t0c + i * 0.03 + 0.3)); const x = cl(540 + Math.cos(a) * r * 0.75, 300, 780), y = 1150 + Math.sin(a) * r * 1.35;
      field += `<div class="abs" style="left:${x}px;top:${y}px;transform:translate(-50%,-50%) rotate(${((i * 37) % 14) - 7}deg) scale(${lerp(1.4, 1, k)});opacity:${k};font:700 ${ci ? 44 : 50}px Plex;color:#fff;background:${i % 3 ? '#1B2847' : '#2A3B66'};padding:16px 26px;border-radius:16px;white-space:nowrap">${s}</div>`; });
    else for (let i = 0; i < 22; i++) { const k = ex(p(t, t0c + i * 0.035, t0c + i * 0.035 + 0.3)); const x = 140 + ((i * 263) % 800), y = 780 + ((i * 151) % 820);
      field += `<div class="abs" style="left:${x}px;top:${y}px;transform:translate(-50%,-50%) rotate(${((i * 29) % 30) - 15}deg) scale(${lerp(1.5, 1, k)});opacity:${k}">${appIcon('pdf', 150)}</div>`; }
    const k = ex(p(t, t0c, t0c + 0.25));
    html += `<div class="abs" style="inset:0">${field}</div><div class="abs" style="left:80px;right:80px;top:180px;font:700 150px/0.95 Barlow;color:#fff;opacity:${k};filter:blur(${(1 - k) * 8}px)">${W3[ci][1].replace(' ', '<br>')}</div>`;
  } else if (sc.id === 'flood') {
    ground = C.ground_gold; let n = 0; for (let i = 0; i < NOTI.length; i++) if (t >= notiT(i)) n++;
    const last = n ? notiT(n - 1) : -9; const sh = Math.exp(-(t - last) * 16) * (n ? 1 : 0); const enter = ex(p(lt, 0, 0.35));
    const sw = pin(p(t, T5 - 0.55, T5 - 0.3)); const zi = pin(p(t, T5 - 0.3, T5));
    phone(540 + Math.sin(t * 95) * 10 * sh, lerp(1750, 1120, enter), 0.86 * (1 + zi * 7), 1); scr(sw < 1 ? lockScreen(t, n, sw) : homeScreen(t, p(t, T5 - 0.32, T5 - 0.25), 1));
    const fk = ex(p(t, wt('v4', /^whoever/) - 0.05, wt('v4', /^whoever/) + 0.3));
    html += `<div class="abs" style="left:80px;top:150px;color:${C.ink};opacity:${1 - zi}"><span class="num" style="font:700 170px/1 Barlow;letter-spacing:-3px">${n >= NOTI.length ? '99+' : String(n * 11 + (n ? 3 : 0))}</span><span style="font:700 76px Barlow;margin-left:18px">unread</span></div>
      <div class="abs" style="left:80px;top:340px;font:700 64px Barlow;color:${C.ink};opacity:${fk * (1 - zi)}">The first to see it wins.</div>`;
    html += `<div class="abs" style="inset:0;background:${C.navy};opacity:${p(zi, 0.6, 1)}"></div>`;
  } else if (sc.id === 'reveal') {
    ground = C.navy; const k = ex(p(t, T5, T5 + 0.5)); const s1 = wt('v5', /^Sinder/); const wm = ex(p(t, s1, s1 + 0.35)); const fk = ex(p(t, wt('v5', /^first/) - 0.1, wt('v5', /^first/) + 0.25));
    html += `<div class="abs" style="left:540px;top:700px;transform:translate(-50%,-50%) scale(${lerp(1.8, 1, k)});opacity:${cl(k * 3)}">${MARK(360, 'b', io(p(t, T5, T5 + 0.6)))}</div>
      <div class="abs" style="left:0;right:0;top:940px;text-align:center;font:700 240px/1 Barlow;letter-spacing:6px;color:#fff;clip-path:inset(0 ${100 - wm * 100}% 0 0)">SINDER</div>
      <div class="abs" style="left:0;right:0;top:1210px;text-align:center;font:700 96px Barlow;color:${C.gold};opacity:${fk};filter:blur(${(1 - fk) * 8}px)">sees it first.</div>`;
  } else if (sc.id === 'army') {
    ground = C.navy; const a0 = wt('v6', /^army/) - 0.1;
    let grid = ''; AGENTS.forEach(([role, src], i) => { const k = ex(p(t, a0 + i * 0.04, a0 + i * 0.04 + 0.35)); const verb = VERBS[(Math.floor(t * 1.8 + i * 0.7)) % VERBS.length];
      grid += `<div style="display:flex;align-items:center;gap:18px;height:84px;padding:0 26px;border-radius:18px;background:#121D38;border:2px solid #1F2E55;opacity:${k};transform:scale(${lerp(0.85, 1, k)})"><i style="width:16px;height:16px;border-radius:50%;background:${C.green};flex:none"></i><div style="flex:1;min-width:0;white-space:nowrap;overflow:hidden"><b style="font:700 30px Plex;color:#fff">${role}</b><span style="font:500 28px Plex;color:#8FA2C7"> · ${src}</span></div><span style="font:600 26px Plex;color:${C.gold}">${verb}</span></div>`; });
    const tk = ex(p(t, a0, a0 + 0.3)), ok = ex(p(t, wt('v6', /^open/) - 0.1, wt('v6', /^open/) + 0.25)), ck = ex(p(t, wt('v6', /^clock/) - 0.1, wt('v6', /^clock/) + 0.25));
    html += `<div class="abs" style="left:80px;top:160px"><div style="font:700 150px/0.95 Barlow;color:#fff;opacity:${tk};filter:blur(${(1 - tk) * 6}px)">An AI army</div><div style="display:flex;gap:16px;margin-top:22px"><span style="font:700 40px Plex;color:#0B1324;background:${C.gold};padding:8px 20px;border-radius:12px;opacity:${ok}">OSINT</span><span style="font:700 40px Plex;color:#fff;background:${C.green};padding:8px 20px;border-radius:12px;opacity:${ck}">24/7</span></div></div>
      <div class="abs" style="left:50px;right:50px;top:470px;display:flex;flex-direction:column;gap:14px">${grid}</div>`;
  } else if (sc.id === 'rank') {
    ground = C.light; const tq = L('v7'), tf = wt('v7', /^It/) - sc.t0;
    html += painFix('Drowning in tenders?', 'Ranked for you.', tq, tf, lt);
    const ROWS = [['fr', '73.6', 'Ophthalmology equipment', 'Resah, France · $182.9M · 26 days'], ['gb', '', 'Green hydrogen, ISO 14687', 'United Kingdom · $40.1M'], ['do', '', 'Power transformers', 'Dominican Republic · $7.8M']];
    let rows = ''; [0, 1, 2].forEach((i) => { const k = ex(p(lt, tf + 0.1 + i * 0.12, tf + 0.5 + i * 0.12)); const [cc, s, ti, sub] = ROWS[i];
      rows += `<div style="display:flex;align-items:center;gap:26px;padding:30px 34px;border-top:${i ? '2px solid #E1E6EF' : 'none'};opacity:${k};transform:translateY(${(1 - k) * 40}px)"><div style="font:700 70px/1 Barlow;color:${i ? '#9AA6BA' : C.deep};width:60px">${i + 1}</div><div style="flex:1;min-width:0"><div style="font:700 42px Plex;color:${C.ink};white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${ti}</div><div style="font:500 30px Plex;color:#5F6B80;margin-top:4px">${sub}</div></div></div>`; });
    const ck = ex(p(lt, tf, tf + 0.4));
    html += `<div class="abs" style="left:60px;width:960px;top:${lerp(1500, 640, ck)}px;background:#fff;border-radius:40px;box-shadow:0 30px 80px rgba(11,19,36,.14);opacity:${ck}">${rows}<div style="padding:14px 34px 26px;font:500 28px Plex;color:#6B7891">Ranked by fit from 34,644 live tenders</div></div>`;
  } else if (sc.id === 'sup') {
    ground = C.light; const tq = L('v8'), tf = wt('v8', /^Suppliers/) - sc.t0;
    html += painFix('Who really makes it?', 'Suppliers, with proof.', tq, tf, lt);
    const SUP = [['de', 'Optix Medical GmbH', 'Sold ophthalmic equipment to 6 public hospitals', 'award records', 1], ['fr', 'Clarion Ophthalmique SAS', 'Supplied this buyer before', 'award records', 1], ['se', 'Nordlys Instruments AB', 'Lists the product, not yet proven', 'trade directory', 0]];
    let rows = ''; SUP.forEach(([cc, nm, ev, src, v], i) => { const k = ex(p(lt, tf + 0.05 + i * 0.14, tf + 0.45 + i * 0.14)); const okk = p(lt, tf + 0.35 + i * 0.14, tf + 0.6 + i * 0.14);
      rows += `<div style="display:flex;gap:24px;align-items:center;padding:28px 34px;border-top:${i ? '2px solid #E1E6EF' : 'none'};opacity:${k}">${flag(cc, 60)}<div style="flex:1"><div style="font:700 38px Plex;color:${C.ink}">${nm}</div><div style="font:500 30px/1.3 Plex;color:#3C475C;margin-top:4px">${ev}</div><div style="font:600 27px Plex;color:#6B7891;margin-top:2px">evidence: ${src}</div></div>${v ? check(okk, 62) : `<div style="width:62px;height:62px;border-radius:50%;background:#D9A21B;color:#fff;font:700 40px/62px Plex;text-align:center;opacity:${okk}">!</div>`}</div>`; });
    const ck = ex(p(lt, tf, tf + 0.4));
    html += `<div class="abs" style="left:60px;width:960px;top:${lerp(1500, 640, ck)}px;background:#fff;border-radius:40px;box-shadow:0 30px 80px rgba(11,19,36,.14);opacity:${ck}">${rows}<div style="padding:14px 34px 26px;font:500 28px Plex;color:#6B7891">Supplier names are illustrative</div></div>`;
  } else if (sc.id === 'price') {
    ground = C.light; const tq = L('v9'), tf = wt('v9', /^Straight/) - sc.t0;
    html += painFix("What's the real price?", 'From the source.', tq, tf, lt);
    const G = [['Bugisu AA', 2.7215], ['Bugisu A', 2.7115], ['Wugar', 2.7015], ['Drugar', 2.5115], ['Robusta Screen 18', 1.8563]];
    const ck = ex(p(lt, tf, tf + 0.4)); let rows = ''; G.forEach(([g, v], i) => { const q = ex(p(lt, tf + 0.2 + i * 0.06, tf + 0.6 + i * 0.06)); rows += `<div style="display:flex;align-items:center;gap:20px;margin-top:20px;opacity:${q}"><div style="width:290px;font:600 32px Plex;color:#D5DDEB">${g}</div><div style="flex:1;height:18px;border-radius:9px;background:#1E2B48"><div style="width:${q * (v / 2.8) * 100}%;height:100%;border-radius:9px;background:${i === 0 ? C.gold : '#4A5E8C'}"></div></div><div class="num" style="width:120px;text-align:right;font:700 36px Plex;color:#fff">$${v.toFixed(2)}</div></div>`; });
    html += `<div class="abs" style="left:60px;width:960px;top:${lerp(1500, 620, ck)}px;background:${C.card};border-radius:40px;padding:44px 46px;opacity:${ck}">
      <div style="display:flex;align-items:center;gap:18px">${flag('ug', 60)}<span style="font:600 34px Plex;color:#AFC0DD">Arabica coffee · Kampala, Uganda</span></div>
      <div style="display:flex;align-items:baseline;gap:18px;margin-top:8px"><span class="num" style="font:700 210px/1 Barlow;color:${C.gold};letter-spacing:-4px">$${(2.72 * ex(p(lt, tf, tf + 0.7))).toFixed(2)}</span><span style="font:700 56px Barlow;color:#fff">per lb</span></div>${rows}
      <div style="font:500 28px Plex;color:#8FA2C7;margin-top:26px">Uganda Coffee Development Authority, 6 Nov 2026</div></div>`;
  } else if (sc.id === 'odds') {
    ground = C.light; const tq = L('v10'), tf = wt('v10', /^Your/) - sc.t0; const bd = wt('v10', /^bid/) - sc.t0;
    html += painFix('Can you win?', 'Know your odds.', tq, tf, lt);
    const sl = io(p(lt, tf, bd + 0.2)); const win = lerp(0.03, 0.154, sl), ev = lerp(0.1, 1.744, sl); const R = 300, Cc = Math.PI * R, k = ex(p(lt, tf - 0.05, tf + 0.35));
    html += `<div class="abs" style="left:60px;width:960px;top:${lerp(1500, 600, k)}px;height:1000px;background:#fff;border-radius:40px;box-shadow:0 30px 80px rgba(11,19,36,.12);opacity:${k}">
      <svg class="abs" style="left:${480 - R - 24}px;top:60px" width="${2 * R + 48}" height="${R + 48}"><path d="M24 ${R + 24} A${R} ${R} 0 0 1 ${2 * R + 24} ${R + 24}" fill="none" stroke="#E4E9F2" stroke-width="38" stroke-linecap="round"/><path d="M24 ${R + 24} A${R} ${R} 0 0 1 ${2 * R + 24} ${R + 24}" fill="none" stroke="${C.deep}" stroke-width="38" stroke-linecap="round" stroke-dasharray="${Cc}" stroke-dashoffset="${Cc * (1 - win / 0.3)}"/></svg>
      <div class="abs" style="left:0;right:0;top:220px;text-align:center"><div class="num" style="font:700 160px/1 Barlow;color:${C.ink}">${Math.round(win * 100)}%</div><div style="font:600 32px Plex;color:#6B7891">win chance · 2 expected bidders</div></div>
      <div class="abs" style="left:60px;top:520px"><div style="font:600 32px Plex;color:#6B7891">Expected value</div><div class="num" style="font:700 190px/1 Barlow;color:${C.deep};letter-spacing:-3px">$${ev.toFixed(2)}M</div></div>
      <div class="abs" style="left:60px;right:60px;top:820px;padding-top:28px;border-top:2px solid #E1E6EF;display:flex;align-items:center;justify-content:space-between"><span style="font:600 32px Plex;color:#6B7891">Ophthalmology equipment · Resah</span><span style="font:700 64px Barlow;letter-spacing:3px;color:#fff;background:${C.green};padding:4px 30px;border-radius:14px;opacity:${p(lt, bd, bd + 0.1)};transform:scale(${lerp(1.5, 1, ex(p(lt, bd, bd + 0.3)))});display:inline-block">PURSUE</span></div></div>`;
  } else if (sc.id === 'build') {
    ground = C.light; const ITEMS = ['Tender, ranked', 'Suppliers, with proof', 'Price at source', 'Freight, duty, landed cost', 'RFQ, drafted', 'Odds and expected value'];
    const b0 = L('v11'), one = wt('v11', /^one/) - sc.t0; const col = io(p(lt, one, one + 0.6));
    let rows = ''; ITEMS.forEach((s, i) => { const k = ex(p(lt, b0 + i * 0.12, b0 + i * 0.12 + 0.3)); rows += `<div style="display:flex;align-items:center;gap:24px;padding:22px 34px;border-top:${i ? '2px solid #E1E6EF' : 'none'};opacity:${k}">${check(p(lt, b0 + i * 0.12 + 0.15, b0 + i * 0.12 + 0.4), 52)}<span style="font:700 40px Plex;color:${C.ink}">${s}</span></div>`; });
    html += `<div class="abs" style="left:80px;top:170px;font:700 140px/0.95 Barlow;color:${C.ink};opacity:${1 - p(col, 0, 0.4)}">The whole deal</div>`;
    html += `<div class="abs" style="left:60px;width:960px;top:${lerp(560, 760, col)}px;transform-origin:50% 0;transform:scale(${lerp(1, 0.5, col)});background:#fff;border-radius:40px;box-shadow:0 30px 80px rgba(11,19,36,.14);opacity:${1 - p(col, 0.7, 1)}">${rows}</div>`;
    if (col > 0) { phone(540, lerp(1500, 1110, col), 0.84, p(col, 0.3, 0.8)); ui(70); html += `<div class="abs" style="left:80px;top:170px;font:700 140px/0.95 Barlow;color:${C.ink};opacity:${p(col, 0.4, 1)}">One screen.</div>`; }
  } else if (sc.id === 'meet') {
    const fl = io(p(lt, 0, 0.35)); ground = mix(C.light, C.tg, fl);
    const q1 = wt('v12', /^Ask/) - 0.05, a1 = q1 + 0.75, a3 = q1 + 1.35;
    phone(540, lerp(1900, 1130, ex(p(lt, 0, 0.45))), 0.84, 1);
    const chat = [[q1, 'me', "Arabica exporters in Uganda, and today's price?"], [a1, 'bot', '<b>Elgon Highland Coffee</b>, Mbale<br><span style="color:#7E8CA6">listed exporter · check before use</span><br>Export manager, email on file'], [a3, 'bot', `Bugisu AA <b style="color:#B07A0E">$2.72/lb</b> FOT Kampala<br><span style="color:#7E8CA6;font-size:26px">UCDA, 6 Nov</span>`]];
    let h = ''; for (const [tc, w, x] of chat) { const k = ex(p(t, tc, tc + 0.25)); if (k <= 0) continue; const st = `opacity:${k};transform:translateY(${(1 - k) * 30}px)`;
      h += w === 'me' ? `<div style="${st};align-self:flex-end;max-width:84%;background:#EEFFDE;color:#0B1324;padding:20px 24px;border-radius:30px 30px 8px 30px;font:500 32px/1.3 Plex">${x}</div>` : `<div style="${st};align-self:flex-start;max-width:88%;background:#fff;color:#0B1324;padding:20px 24px;border-radius:30px 30px 30px 8px;font:500 32px/1.3 Plex">${x}</div>`; }
    scr(`<div class="abs" style="inset:0;background:#C9DCEB"><div style="height:190px;padding-top:80px;background:#fff;display:flex;align-items:center;gap:20px;padding-left:30px;border-bottom:1px solid #DDE3EC"><div style="border-radius:50%;overflow:hidden;width:76px;height:76px">${MARK(76, 't')}</div><div><div style="font:700 34px Plex;color:#0B1324">Sinder Deal Agent</div><div style="font:500 26px Plex;color:#2481CC">bot</div></div></div><div class="abs" style="left:0;right:0;top:190px;bottom:0;padding:26px;display:flex;flex-direction:column;justify-content:flex-end;gap:14px">${h}</div></div>`);
    const ik = ex(p(lt, 0.1, 0.45));
    html += `<div class="abs" style="left:80px;top:170px;display:flex;align-items:center;gap:26px;opacity:${ik}"><div style="width:112px;height:112px;border-radius:50%;background:#fff;display:flex;align-items:center;justify-content:center">${icon('telegram', 112, C.tg)}</div><span style="font:700 112px/1 Barlow;color:#fff">Mid-meeting</span></div>`;
  } else if (sc.id === 'yes') {
    ground = C.tg; const tap = wt('v13', /^yes/) - 0.05; const ok = t >= tap; const k = ex(p(lt, 0, 0.3)); const pr = p(t, tap - 0.08, tap) - p(t, tap, tap + 0.1);
    html += `<div class="abs" style="left:80px;top:180px;font:700 150px/0.95 Barlow;color:#fff">Your call.</div>
      <div class="abs" style="left:60px;right:60px;top:440px;background:#fff;border-radius:40px;padding:40px;opacity:${k};transform:translateY(${(1 - k) * 60}px)"><div style="font:600 38px/1.35 Plex;color:#0B1324">Send the RFQ to 3 suppliers?</div>
      <div style="display:flex;gap:18px;margin-top:30px"><div style="flex:1;text-align:center;padding:36px;border-radius:26px;background:${ok ? C.green : C.tg};color:#fff;font:700 56px Barlow;letter-spacing:2px;transform:scale(${1 - 0.06 * pr})">${ok ? 'APPROVED' : 'APPROVE'}</div><div style="flex:1;text-align:center;padding:36px;border-radius:26px;background:#EEF2F7;color:#2481CC;font:700 56px Barlow;letter-spacing:2px">REJECT</div></div></div>`;
  } else if (sc.id === 'cta') {
    ground = mix(C.tg, C.navy, io(p(lt, 0, 0.35))); const s1 = wt('v14', /^Sinder/) - sc.t0, sf = wt('v14', /^See/) - sc.t0, pa = wt('v15', /^Partners/) - sc.t0, lt0 = wt('v15', /^let/) - sc.t0;
    const mk = ex(p(lt, s1 - 0.1, s1 + 0.35)), wm = ex(p(lt, s1, s1 + 0.35)), sk = ex(p(lt, sf - 0.05, sf + 0.3)), out1 = 1 - p(lt, pa - 0.25, pa);
    html += `<div class="abs" style="left:0;right:0;top:220px;display:flex;align-items:center;justify-content:center;gap:34px"><div style="transform:scale(${lerp(1.6, 1, mk)});opacity:${cl(mk * 3)}">${MARK(190, 'c', io(p(lt, s1 - 0.1, s1 + 0.5)))}</div><div style="font:700 190px/1 Barlow;letter-spacing:4px;color:#fff;clip-path:inset(0 ${100 - wm * 100}% 0 0)">SINDER</div></div>
      <div class="abs" style="left:80px;right:80px;top:560px;font:700 150px/0.95 Barlow;color:${C.gold};opacity:${sk * out1};filter:blur(${(1 - sk) * 8}px)">See every<br>deal first.</div>`;
    const k2 = ex(p(lt, pa - 0.1, pa + 0.3)), k3 = ex(p(lt, lt0 - 0.05, lt0 + 0.3)), k4 = ex(p(lt, lt0 + 0.35, lt0 + 0.7));
    html += `<div class="abs" style="left:80px;right:80px;top:600px;opacity:${k2};font:700 110px/1.02 Barlow;color:#fff">Partners and investors</div>
      <div class="abs" style="left:0;right:0;top:800px;text-align:center;font:700 250px/1 Barlow;color:${C.gold};opacity:${k3};filter:blur(${(1 - k3) * 10}px)">Let's talk.</div>
      <div class="abs" style="left:0;right:0;top:1150px;display:flex;justify-content:center;opacity:${k4}"><div style="font:600 64px Plex;color:${C.navy};background:${C.gold};padding:30px 60px;border-radius:24px">Etamar@sinder.pro</div></div>
      <div class="abs" style="left:0;right:0;top:1330px;text-align:center;font:600 40px Plex;color:#9FB1D3;opacity:${k4}">sinder.pro</div>
      <div class="abs" style="left:0;right:0;top:1820px;text-align:center;font:500 28px Plex;color:#5E6E90;opacity:${k4}">Music: Future Business, Marco Margna, CC BY 3.0</div>`;
    $('black').style.opacity = p(lt, D - 0.4, D);
  }
  $('ground').style.background = ground; drawMap(t, mapO); $('fx').innerHTML = html;
  $('subs').innerHTML = (sc.id === 'cta' && t >= wt('v15', /^let/) - 0.1) ? '' : subtitle(t);
}
const tl = gsap.timeline({ paused: true });
const clock = { t: 0 };
tl.to(clock, { t: TL.total, duration: TL.total, ease: 'none', onUpdate: () => render(tl.time()) }, 0);
render(0);
window.__timelines = window.__timelines || {};
window.__timelines['main'] = tl;
