// v5 scenes: FOMO -> Sinder -> the agent army (OSINT) -> analysis -> the deal built in the system -> Telegram -> your yes -> end card.
const BEAT = TL.beat, T5 = TL.t5;
const AGENTS = [['Tender hunter', 'TED (EU)'], ['Tender hunter', 'PNCP Brazil'], ['Award tracker', 'World Bank'], ['Trade records', 'customs data'], ['Registry check', 'LEI registry'], ['Sanctions screen', 'sanctions lists'], ['Price scout', 'UCDA Uganda'], ['News watch', 'GDELT'], ['Supplier finder', 'Tridge directory'], ['Tender hunter', 'Prozorro Ukraine'], ['Award tracker', 'SECOP II Colombia'], ['Price scout', 'MPOB Malaysia'], ['Tender hunter', 'Find a Tender UK'], ['Registry check', 'company registers'], ['Tender hunter', 'Etimad Saudi Arabia'], ['Price scout', 'US EIA']];
const VERBS = ['reading', 'translating', 'scoring', 'matching', 'checking', 'filing'];
const CATS = [[/^Tender/, 'TENDER PORTALS'], [/^Award/, 'AWARD RECORDS'], [/^Trade/, 'TRADE DATA'], [/^Registries/, 'REGISTRIES'], [/^Sanctions/, 'SANCTIONS LISTS'], [/^Prices/, 'PRICES AT ORIGIN']];
const check = (k, sz = 56, col = '#22A565') => `<div style="width:${sz}px;height:${sz}px;border-radius:50%;background:${col};display:flex;align-items:center;justify-content:center;flex:none;transform:scale(${bk(k)});opacity:${cl(k * 2)}"><svg width="${sz * 0.58}" height="${sz * 0.58}" viewBox="0 0 24 24"><path d="M4 12.5l5 5L20 6.5" fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/></svg></div>`;

function render(t) {
  const sc = Object.values(SC).find((s) => t >= s.t0 && t < s.t1) || SC.cta; const lt = t - sc.t0, D = sc.t1 - sc.t0;
  let ground = C.navy, html = '', mapO = null; phone(0, 0, 1, 0); $('root').style.setProperty('--accent', C.gold); $('black').style.opacity = 0;
  const beatK = Math.exp(-(((t - T5) % BEAT + BEAT) % BEAT) * 9) * (t > T5 ? 1 : 0);

  if (sc.id === 'hook') {
    const zo = pin(p(lt, D - 0.6, D)); const z = lerp(2.9, 3.15, io(p(lt, 0, D - 0.6))) * Math.pow(28, zo);
    const c0 = wt('v1', /^thirty/), c1 = wt('v1', /^tenders/) + 0.3, lv = wt('v2', /^Live/), r0 = wt('v3', /^In/);
    mapO = { cx: lerp(1085, 1123, zo), my0: lerp(470, 407, zo), cy: lerp(1260, 1000, zo), z, alpha: 1, reveal: lerp(0.3, 1.25, ex(p(t, 0.2, wt('v3', /^sources/)))), live: p(t, lv, lv + 0.45), focus: [1123, 407, p(lt, D - 0.6, D - 0.45) * 4 * Math.pow(28, zo)] };
    const n = lerp(29120, 34644, ex(p(t, c0 - 0.1, c1))); const out = 1 - p(lt, D - 0.6, D - 0.4); const lk = ex(p(t, lv - 0.05, lv + 0.3));
    const k195 = ex(p(t, wt('v3', /^ninety/) - 0.1, wt('v3', /^ninety/) + 0.3)), k200 = ex(p(t, wt('v3', /^two/) - 0.1, wt('v3', /^two/) + 0.3));
    html += `<div class="abs" style="left:80px;top:180px;opacity:${out}"><div class="num" style="font:700 300px/0.9 Barlow;letter-spacing:-6px;color:${C.gold}">${fmt(n)}</div>
      <div style="display:flex;align-items:center;gap:22px;margin-top:22px"><span style="font:600 50px Plex;color:#fff">active tenders</span>
      <span style="display:inline-flex;align-items:center;gap:12px;background:${C.green};color:#fff;font:700 40px Plex;letter-spacing:2px;padding:8px 22px;border-radius:14px;opacity:${lk};transform:scale(${lerp(1.6, 1, lk)})"><i style="width:16px;height:16px;border-radius:50%;background:#fff;opacity:${0.5 + 0.5 * Math.cos(t * 6)}"></i>LIVE</span></div>
      <div style="display:flex;gap:70px;margin-top:40px"><div style="opacity:${k195};filter:blur(${(1 - k195) * 6}px)"><div class="num" style="font:700 130px/1 Barlow;color:#fff">195</div><div style="font:600 36px Plex;color:#9FB1D3">countries</div></div>
      <div style="opacity:${k200};filter:blur(${(1 - k200) * 6}px)"><div class="num" style="font:700 130px/1 Barlow;color:#fff">200+</div><div style="font:600 36px Plex;color:#9FB1D3">sources</div></div></div></div>`;
    if (lt > D - 0.1) ground = C.ground_gold;
  } else if (sc.id === 'fomo') {
    ground = C.ground_gold; let n = 0; for (let i = 0; i < NOTI.length; i++) if (t >= notiT(i)) n++;
    const last = n ? notiT(n - 1) : -9; const sh = Math.exp(-(t - last) * 16) * (n ? 1 : 0); const enter = ex(p(lt, 0, 0.45));
    phone(540 + Math.sin(t * 95) * 10 * sh, lerp(1750, 1100, enter), 0.86, 1); scr(lockScreen(t, n, 0));
    const bt = wt('v4', /^already/) - 0.05; const bk2 = ex(p(t, bt, bt + 0.3));
    html += `<div class="abs" style="left:80px;top:150px;color:${C.ink}"><span class="num" style="font:700 170px/1 Barlow;letter-spacing:-3px;display:inline-block;transform:scale(${1 + 0.06 * sh});transform-origin:left bottom">${n >= NOTI.length ? '99+' : String(n * 11 + (n ? 3 : 0))}</span><span style="font:700 76px Barlow;margin-left:18px">unread</span></div>`;
    html += `<div class="abs" style="left:60px;right:60px;top:${lerp(330, 420, bk2)}px;opacity:${bk2};background:#B3261E;color:#fff;border-radius:30px;padding:28px 32px;display:flex;gap:22px;align-items:center;box-shadow:0 30px 70px rgba(80,10,10,.35)"><svg width="64" height="64" viewBox="0 0 24 24" style="flex:none"><circle cx="12" cy="12" r="10" fill="none" stroke="#fff" stroke-width="2.2"/><path d="M12 6v6l4 2" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round"/></svg><div><div style="font:700 40px Plex">Tender closed</div><div style="font:500 32px Plex;opacity:.9">A competitor submitted first</div></div></div>`;
  } else if (sc.id === 'brand') {
    const drop = T5 - sc.t0; ground = C.ground_gold;
    const sw = pin(p(lt, 0, 0.35)); const press = p(lt, 0.35, 0.45) - p(lt, 0.45, 0.52); const zi = pin(p(lt, 0.45, drop));
    if (lt < drop) { phone(540, 1100, 0.86 * (1 + zi * 7), 1); scr(sw < 1 ? lockScreen(t, NOTI.length, sw) : homeScreen(t, press, 1)); html += `<div class="abs" style="inset:0;background:${C.navy};opacity:${p(zi, 0.6, 1)}"></div>`; }
    else { ground = C.navy; const k = ex(p(lt, drop, drop + 0.5)); const s1 = wt('v5', /^Sinder/) - sc.t0; const wm = ex(p(lt, s1 - 0.1, s1 + 0.35));
      html += `<div class="abs" style="left:540px;top:760px;transform:translate(-50%,-50%) scale(${lerp(1.8, 1, k)});opacity:${cl(k * 3)}">${MARK(380, 'b', io(p(lt, drop, drop + 0.7)))}</div>
        <div class="abs" style="left:0;right:0;top:1010px;text-align:center;font:700 240px/1 Barlow;letter-spacing:6px;color:#fff;clip-path:inset(0 ${100 - wm * 100}% 0 0)">SINDER</div>`; }
  } else if (sc.id === 'army') {
    ground = C.navy; const a0 = wt('v6', /^army/) - 0.1; const v7 = TL.lines.v7.t - 0.15; const dim = io(p(t, v7, v7 + 0.4));
    let grid = ''; AGENTS.forEach(([role, src], i) => { const k = ex(p(t, a0 + i * 0.045, a0 + i * 0.045 + 0.4)); const verb = VERBS[(Math.floor(t * 1.6 + i * 0.7)) % VERBS.length];
      grid += `<div style="display:flex;align-items:center;gap:18px;height:84px;padding:0 26px;border-radius:18px;background:#121D38;border:2px solid #1F2E55;opacity:${k};transform:scale(${lerp(0.85, 1, k)})"><i style="width:16px;height:16px;border-radius:50%;background:${C.green};flex:none;opacity:${0.55 + 0.45 * Math.abs(Math.sin(t * 3 + i))}"></i><div style="flex:1;min-width:0;white-space:nowrap;overflow:hidden"><b style="font:700 30px Plex;color:#fff">${role}</b><span style="font:500 28px Plex;color:#8FA2C7"> · ${src}</span></div><span style="font:600 26px Plex;color:${C.gold}">${verb}</span></div>`; });
    html += `<div class="abs" style="left:50px;right:50px;top:470px;display:flex;flex-direction:column;gap:14px;opacity:${1 - 0.82 * dim};filter:blur(${dim * 3}px)">${grid}</div>`;
    const tk = ex(p(t, a0, a0 + 0.35)), ck = ex(p(t, wt('v6', /^clock/) - 0.1, wt('v6', /^clock/) + 0.2));
    html += `<div class="abs" style="left:80px;top:170px;opacity:${1 - dim}"><div style="font:700 150px/0.95 Barlow;color:#fff;opacity:${tk};filter:blur(${(1 - tk) * 6}px)">Dozens of agents</div><div style="font:600 46px Plex;color:${C.gold};margin-top:16px;opacity:${ck}">open-source intelligence, 24/7</div></div>`;
    let ci = -1; CATS.forEach(([r], i) => { if (t >= wt('v7', r) - 0.08) ci = i; });
    if (ci >= 0) { const t0 = wt('v7', CATS[ci][0]) - 0.08; const k = ex(p(t, t0, t0 + 0.22)); const nx = CATS[ci + 1] ? wt('v7', CATS[ci + 1][0]) - 0.08 : sc.t1; const o = 1 - p(t, nx - 0.1, nx);
      const lines = CATS[ci][1].split(' ');
      html += `<div class="abs" style="left:70px;right:70px;top:640px;opacity:${o}">${lines.map((w, j) => `<div style="font:700 ${j === lines.length - 1 ? 250 : 190}px/0.92 Barlow;color:${j === lines.length - 1 ? C.gold : '#fff'};transform:translateX(${(1 - k) * (j % 2 ? 120 : -120)}px);filter:blur(${(1 - k) * 8}px);opacity:${k}">${w}</div>`).join('')}</div>`;
      html += `<div class="abs" style="left:80px;top:1460px;display:flex;gap:12px;opacity:${dim}">${CATS.map((_, i) => `<i style="width:64px;height:10px;border-radius:5px;background:${i <= ci ? C.gold : '#24345A'}"></i>`).join('')}</div>`; }
  } else if (sc.id === 'analyze') {
    ground = C.light; $('root').style.setProperty('--accent', C.deep);
    const r = wt('v8', /^read/), tr = wt('v8', /^translate/), s = wt('v8', /^score/), sv = wt('v8', /^serve/), lf = wt('v8', /^lift/);
    const ent = ex(p(lt, 0, 0.4)); const scan = p(t, r - 0.05, tr - 0.1); const trk = io(p(t, tr - 0.05, tr + 0.35)); const sk = ex(p(t, s - 0.05, s + 0.6)); const up = ex(p(t, sv - 0.05, sv + 0.5)); const lk = ex(p(t, lf - 0.1, lf + 0.3));
    const fr = `<div style="font:600 30px Plex;color:#6B7891">Avis de marché · Resah, France</div><div style="font:700 64px/1.05 Plex;color:${C.ink};margin-top:12px">Équipements d'ophtalmologie</div><div style="font:500 32px/1.4 Plex;color:#3C475C;margin-top:16px">Fourniture d'équipements d'ophtalmologie pour les établissements de santé. Date limite de réception des offres&nbsp;: 26 jours.</div>`;
    const en = `<div style="font:600 30px Plex;color:#6B7891">Contract notice · Resah, France</div><div style="font:700 64px/1.05 Plex;color:${C.ink};margin-top:12px">Ophthalmology equipment</div><div style="font:500 32px/1.4 Plex;color:#3C475C;margin-top:16px">Supply of ophthalmology equipment to health facilities. Bids due in 26 days.</div>`;
    html += `<div class="abs" style="left:60px;width:960px;top:${lerp(560, 420, up) + (1 - ent) * 400}px;background:#fff;border-radius:40px;padding:48px 50px;box-shadow:0 ${30 + 40 * up}px ${80 + 60 * up}px rgba(11,19,36,${0.12 + 0.12 * up});opacity:${ent}">
      <div style="position:relative;height:420px"><div class="abs" style="inset:0;opacity:${1 - trk};filter:blur(${trk * 6}px)">${fr}</div><div class="abs" style="inset:0;opacity:${trk};filter:blur(${(1 - trk) * 6}px)">${en}</div>
      <div class="abs" style="left:-50px;right:-50px;top:${scan * 400}px;height:6px;background:${C.deep};opacity:${scan > 0 && scan < 1 ? 0.8 : 0}"></div></div>
      <div style="display:flex;align-items:center;gap:30px;border-top:2px solid #E1E6EF;padding-top:34px;opacity:${sk}">${ring(62, 13, 0.736 * sk, C.deep).replace('#2A3656', '#E4E9F2')}<div><div class="num" style="font:700 110px/1 Barlow;color:${C.ink}">${(73.6 * sk).toFixed(1)}</div><div style="font:600 32px Plex;color:#6B7891">fit score · ranked first of 34,644</div></div></div></div>`;
    html += `<div class="abs" style="left:80px;top:170px;font:700 120px/1 Barlow;color:${C.ink}">${trk < 0.5 ? words('Read. Translated.', r - sc.t0 - 0.1, lt) : words('Read. Translated. Scored.', r - sc.t0 - 0.1, lt, { gold: [2] })}</div>`;
    html += `<div class="abs" style="left:60px;right:60px;top:1430px;display:flex;justify-content:center;opacity:${lk}"><div style="background:${C.green};color:#fff;font:700 64px Barlow;letter-spacing:2px;padding:20px 48px;border-radius:22px;transform:scale(${lerp(1.4, 1, lk)})">READY TO LIFT</div></div>`;
  } else if (sc.id === 'build') {
    ground = C.light; $('root').style.setProperty('--accent', C.deep);
    const one = wt('v11', /^Signal/) - 0.1; const col = io(p(t, one, one + 0.7));
    const ITEMS = [[/^suppliers/, 'Suppliers', '3 matched · 2 proven by award records'], [/^price/, 'Price to win', '$157.3M to $166.4M, from the published budget'], [/^Freight/, 'Freight, duty, landed cost', 'Duty 0%, EU internal supply · freight estimated'], [/^RFQ/, 'RFQ', 'Drafted to 3 suppliers · waiting for your approval'], [/^odds/, 'Your odds', '15% win chance · expected value $1.74M']];
    const hk = ex(p(lt, 0, 0.35));
    html += `<div class="abs" style="left:80px;top:150px;display:flex;align-items:center;gap:20px;opacity:${hk * (1 - col)}">${flag('fr', 64)}<span style="font:600 38px Plex;color:#3C475C">Ophthalmology equipment · Resah · $182.9M</span></div>`;
    html += `<div class="abs" style="left:80px;top:220px;font:700 120px/1 Barlow;color:${C.ink};opacity:${1 - col}">${words('Build the deal', 0.05, lt)}</div>`;
    let rows = ''; ITEMS.forEach(([r, h, d], i) => { const t0 = wt('v10', r) - 0.08; const k = ex(p(t, t0, t0 + 0.4)); const ck2 = p(t, t0 + 0.3, t0 + 0.55);
      rows += `<div style="display:flex;align-items:center;gap:26px;padding:30px 34px;border-top:${i ? '2px solid #E1E6EF' : 'none'};opacity:${k};transform:translateX(${(1 - k) * 80}px)">${check(ck2, 62)}<div style="flex:1"><div style="font:700 44px Plex;color:${C.ink}">${h}</div><div style="font:500 30px/1.3 Plex;color:#3C475C;margin-top:4px">${d}</div></div></div>`; });
    const sx = lerp(1, 0.52, col), sy = lerp(0, 120, col);
    html += `<div class="abs" style="left:60px;width:960px;top:${400 + sy}px;transform-origin:50% 0;transform:scale(${sx});background:#fff;border-radius:40px;box-shadow:0 30px 80px rgba(11,19,36,.14);opacity:${ex(p(lt, 0.2, 0.6)) * (1 - p(col, 0.75, 1))}">${rows}<div style="padding:16px 34px 26px;font:500 28px Plex;color:#6B7891">Supplier names and freight are illustrative</div></div>`;
    if (col > 0) { phone(540, lerp(1500, 1110, col), 0.84, p(col, 0.3, 0.8)); ui(70); const bk3 = ex(p(t, wt('v11', /^screen/) - 0.1, wt('v11', /^screen/) + 0.3));
      html += `<div class="abs" style="left:80px;top:180px;font:700 130px/1 Barlow;color:${C.ink};opacity:${p(col, 0.5, 1)}">One screen.</div><div class="abs" style="left:80px;top:320px;font:600 44px Plex;color:${C.deep};opacity:${bk3}">From signal to bid.</div>`; }
  } else if (sc.id === 'meet') {
    const fl = io(p(lt, 0, 0.45)); ground = mix(C.light, C.tg, fl);
    const q1 = wt('v12', /^Ask/) + 0.1, a1 = wt('v13', /^Supplier/) + 0.05, a2 = wt('v13', /^contact/) + 0.05, a3 = wt('v13', /^price/) + 0.05;
    phone(540, lerp(1900, 1130, ex(p(lt, 0.1, 0.6))), 0.84, 1);
    const chat = [[q1, 'me', "Arabica exporters in Uganda, and today's price?"], [a1, 'bot', '<b>Elgon Highland Coffee</b>, Mbale<br><span style="color:#7E8CA6">listed exporter · check before use</span>'], [a2, 'bot', 'Export manager<br><span style="color:#7E8CA6">email on file</span>'], [a3, 'bot', `Bugisu AA <b style="color:#B07A0E">$2.72/lb</b> FOT Kampala<br><span style="color:#7E8CA6;font-size:26px">Uganda Coffee Development Authority, 6 Nov</span>`]];
    let h = ''; for (const [tc, w, x] of chat) { const k = ex(p(t, tc, tc + 0.3)); if (k <= 0) continue; const st = `opacity:${k};transform:translateY(${(1 - k) * 30}px)`;
      h += w === 'me' ? `<div style="${st};align-self:flex-end;max-width:84%;background:#EEFFDE;color:#0B1324;padding:20px 24px;border-radius:30px 30px 8px 30px;font:500 32px/1.3 Plex">${x}<span style="font-size:22px;color:#5FA84A;margin-left:10px">14:21 ✓✓</span></div>`
        : `<div style="${st};align-self:flex-start;max-width:88%;background:#fff;color:#0B1324;padding:20px 24px;border-radius:30px 30px 30px 8px;font:500 32px/1.3 Plex">${x}<span style="font-size:22px;color:#9AA6BA;margin-left:10px">14:21</span></div>`; }
    for (const [tc, w] of chat) { if (w === 'me') continue; if (t > tc - 0.55 && t < tc) { h += `<div style="align-self:flex-start;background:#fff;padding:22px 26px;border-radius:30px;display:flex;gap:10px">${[0, 1, 2].map((j) => `<i style="width:14px;height:14px;border-radius:50%;background:#9AA6BA;opacity:${0.35 + 0.65 * Math.abs(Math.sin(t * 8 + j))}"></i>`).join('')}</div>`; break; } }
    scr(`<div class="abs" style="inset:0;background:#C9DCEB"><div style="height:190px;padding-top:80px;background:#fff;display:flex;align-items:center;gap:20px;padding-left:30px;border-bottom:1px solid #DDE3EC"><div style="border-radius:50%;overflow:hidden;width:76px;height:76px">${MARK(76, 't')}</div><div><div style="font:700 34px Plex;color:#0B1324">Sinder Deal Agent</div><div style="font:500 26px Plex;color:#2481CC">bot</div></div></div><div class="abs" style="left:0;right:0;top:190px;bottom:0;padding:26px;display:flex;flex-direction:column;justify-content:flex-end;gap:14px">${h}</div></div>`);
    const ik = ex(p(lt, 0.2, 0.6));
    html += `<div class="abs" style="left:80px;top:150px;font:600 36px Plex;color:#EAF6FE;opacity:${ik}">14:21 · in a meeting with a buyer</div><div class="abs" style="left:80px;top:205px;display:flex;align-items:center;gap:26px;opacity:${ik}"><div style="width:112px;height:112px;border-radius:50%;background:#fff;display:flex;align-items:center;justify-content:center;transform:scale(${lerp(0.6, 1, bk(ik))})">${icon('telegram', 112, C.tg)}</div><span style="font:700 112px/1 Barlow;color:#fff">Ask mid-meeting</span></div>`;
  } else if (sc.id === 'yes') {
    ground = C.tg; const tap = wt('v14', /^yes/) - 0.05; const pr = p(t, tap - 0.08, tap) - p(t, tap, tap + 0.1); const ok = t >= tap; const k = ex(p(lt, 0, 0.35)); const g = ex(p(t, tap, tap + 0.3));
    html += `<div class="abs" style="left:80px;top:180px;font:700 150px/0.95 Barlow;color:#fff">${words('Your call. Always.', 0.1, lt, { gold: [] })}</div>
      <div class="abs" style="left:60px;right:60px;top:560px;background:#fff;border-radius:40px;padding:40px;opacity:${k};transform:translateY(${(1 - k) * 60}px)"><div style="font:500 36px/1.35 Plex;color:#0B1324">Send the RFQ to 3 suppliers?</div><div style="font:500 30px Plex;color:#6B7891;margin-top:8px">Ophthalmology equipment · Resah</div>
      <div style="display:flex;gap:18px;margin-top:34px"><div style="flex:1;text-align:center;padding:36px;border-radius:26px;background:${ok ? C.green : C.tg};color:#fff;font:700 54px Barlow;letter-spacing:2px;transform:scale(${1 - 0.06 * pr + 0.04 * g * (1 - g) * 4})">${ok ? 'APPROVED' : 'APPROVE'}</div><div style="flex:1;text-align:center;padding:36px;border-radius:26px;background:#EEF2F7;color:#2481CC;font:700 54px Barlow;letter-spacing:2px">REJECT</div></div></div>
      <div class="abs" style="left:80px;top:1060px;font:600 42px Plex;color:#EAF6FE;opacity:${ex(p(t, tap + 0.2, tap + 0.6))}">Nothing leaves without your yes.</div>`;
  } else if (sc.id === 'cta') {
    ground = mix(C.tg, C.navy, io(p(lt, 0, 0.4))); const s1 = wt('v15', /^Sinder/) - sc.t0, lf = wt('v15', /^Lift/) - sc.t0, lt0 = wt('v16', /^let/) - sc.t0, pa = wt('v16', /^Partners/) - sc.t0;
    const mk = ex(p(lt, s1 - 0.1, s1 + 0.4)), wm = ex(p(lt, s1 + 0.05, s1 + 0.45)), stp = p(lt, s1 + 0.6, s1 + 0.8), lk = ex(p(lt, lf - 0.08, lf + 0.3)), out1 = 1 - p(lt, pa - 0.3, pa);
    html += `<div class="abs" style="left:0;right:0;top:220px;display:flex;align-items:center;justify-content:center;gap:34px"><div style="transform:scale(${lerp(1.6, 1, mk)});opacity:${cl(mk * 3)}">${MARK(190, 'c', io(p(lt, s1 - 0.1, s1 + 0.6)))}</div><div style="font:700 190px/1 Barlow;letter-spacing:4px;color:#fff;clip-path:inset(0 ${100 - wm * 100}% 0 0)">SINDER</div></div>
      <div class="abs" style="left:80px;right:80px;top:560px;opacity:${out1}"><div style="font:700 120px/1 Barlow;color:#9FB1D3;opacity:${stp};text-decoration:line-through;text-decoration-thickness:8px">Chasing deals</div><div style="font:700 260px/1 Barlow;color:${C.gold};opacity:${lk};transform:scale(${lerp(1.3, 1, lk)});transform-origin:left center;margin-top:10px">Lift them.</div></div>`;
    const k2 = ex(p(lt, pa - 0.1, pa + 0.35)), k3 = ex(p(lt, lt0 - 0.05, lt0 + 0.3)), k4 = ex(p(lt, lt0 + 0.4, lt0 + 0.8));
    html += `<div class="abs" style="left:80px;right:80px;top:600px;opacity:${k2};font:700 110px/1.02 Barlow;color:#fff">Partners and investors</div>
      <div class="abs" style="left:0;right:0;top:800px;text-align:center;font:700 250px/1 Barlow;color:${C.gold};opacity:${k3};filter:blur(${(1 - k3) * 10}px)">Let's talk.</div>
      <div class="abs" style="left:0;right:0;top:1150px;display:flex;justify-content:center;opacity:${k4}"><div style="font:600 64px Plex;color:${C.navy};background:${C.gold};padding:30px 60px;border-radius:24px;transform:scale(${lerp(0.9, 1, k4)})">Etamar@sinder.pro</div></div>
      <div class="abs" style="left:0;right:0;top:1330px;text-align:center;font:600 40px Plex;color:#9FB1D3;opacity:${k4}">sinder.pro</div>
      <div class="abs" style="left:0;right:0;top:1820px;text-align:center;font:500 28px Plex;color:#5E6E90;opacity:${k4}">Music: Future Business, Marco Margna, CC BY 3.0</div>`;
    $('black').style.opacity = p(lt, D - 0.45, D);
  }
  $('ground').style.background = ground; drawMap(t, mapO); $('fx').innerHTML = html;
  $('subs').innerHTML = sc.id === 'cta' && t >= wt('v16', /^let/) - 0.1 ? '' : subtitle(t);

}
const tl = gsap.timeline({ paused: true });
const clock = { t: 0 };
tl.to(clock, { t: TL.total, duration: TL.total, ease: 'none', onUpdate: () => render(tl.time()) }, 0);
render(0);
window.__timelines = window.__timelines || {};
window.__timelines['main'] = tl;
