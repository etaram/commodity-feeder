// v10 "The Scope" (creative director's locked brief). Grey-blue = unseen, gold = seen by Sinder.
// Motifs: dot map (behind every navy scene), read-line (exactly 5 sweeps), redaction bars, source threads.
const BEAT = TL.beat, T5 = TL.t5;
const K = { navy: '#0B1324', paper: '#E6EBF2', unseen: '#2C3D66', unseenDot: '#4A5F94', gold: '#DDB45E', goldHi: '#F0CF7A', card: '#15233E', line: '#2A3B60', div: '#22335A', mute: '#93A3C0', ink: '#E8EEF8', tg: '#2AABEE', pg: '#123A27', pgt: '#4BD28D', inkMute: '#5A6782' };
const SPR = (x, z = 0.8, w = 14) => { x = Math.max(0, x); return 1 - Math.exp(-z * w * x) * Math.cos(w * Math.sqrt(1 - z * z) * x); };
const PT = { FRA: [969, 339], ISR: [1123, 407], UGA: [1112, 552], DEU: [1004, 316], GBR: [955, 311], DNK: [1005, 280], KEN: [1136, 554] };
// ---------- the scope: one dot map; seenY = read-line position (dots above it are seen) ----------
function scope(o) {
  const c = $('map'), x = c.getContext('2d'); x.clearRect(0, 0, 1080, 1920); if (!o) return;
  const { cx, my0, cy, z, alpha = 1, seenY = -1, allSeen = 0, lit = [], dimSeen = 1 } = o;
  x.save(); x.globalAlpha = alpha; const r0 = Math.max(1.6, 0.62 * z);
  for (const [mx, my, h] of MAP.dots) {
    const X = 540 + (mx - cx) * z, Y = cy + (my - my0) * z; if (X < -10 || X > 1090 || Y < -10 || Y > 1930) continue;
    const seen = allSeen || Y < seenY;
    if (seen && h > 0) { x.fillStyle = K.goldHi; x.globalAlpha = alpha * dimSeen * (0.55 + 0.45 * h); x.beginPath(); x.arc(X, Y, r0 * (1 + 1.4 * h), 0, 6.2832); x.fill(); x.globalAlpha = alpha; }
    else { x.fillStyle = seen ? '#3B4C78' : K.unseenDot; x.beginPath(); x.arc(X, Y, r0, 0, 6.2832); x.fill(); }
  }
  for (const [mx, my, k] of lit) { if (k <= 0) continue; const X = 540 + (mx - cx) * z, Y = cy + (my - my0) * z; x.globalAlpha = alpha * k; x.fillStyle = K.goldHi; x.beginPath(); x.arc(X, Y, 8, 0, 6.2832); x.fill(); x.strokeStyle = 'rgba(240,207,122,.45)'; x.lineWidth = 2; x.beginPath(); x.arc(X, Y, 18, 0, 6.2832); x.stroke(); }
  if (seenY > 0 && seenY < 1920 && !allSeen) { x.globalAlpha = alpha; x.fillStyle = K.goldHi; x.fillRect(0, seenY - 2, 1080, 4); }
  x.restore();
}
const scr2 = (o, mx, my) => [540 + (mx - o.cx) * o.z, o.cy + (my - o.my0) * o.z];
// a source thread: orthogonal 2 px gold line from (x1,y1) to (x2,y2), drawn to fraction k
function thread(x1, y1, x2, y2, k) { if (k <= 0) return ''; const my = y1 + (y2 - y1) * 0.5; const L1 = Math.abs(my - y1), L2 = Math.abs(x2 - x1), L3 = Math.abs(y2 - my), T = L1 + L2 + L3; const d = `M${x1} ${y1} V${my} H${x2} V${y2}`;
  return `<svg class="abs" style="left:0;top:0" width="1080" height="1920"><path d="${d}" fill="none" stroke="${K.goldHi}" stroke-width="3" stroke-linecap="round" stroke-dasharray="${T}" stroke-dashoffset="${T * (1 - cl(k))}"/><circle cx="${x2}" cy="${y2}" r="${7 * cl(k * 3 - 2)}" fill="${K.goldHi}"/></svg>`; }
// ---------- captions: the voice, 2-5 word chunks, no box ----------
const CH = []; for (const [k, l] of Object.entries(TL.lines)) { let cur = []; l.words.forEach((w, i) => { cur.push(w); const s = cur.map((c) => c[0]).join(' '); const end = /[.,?]$/.test(w[0]); if (cur.length >= 5 || s.length > 24 || (end && cur.length >= 2) || i === l.words.length - 1) { CH.push(cur); cur = []; } }); }
function caption(t, dark, by = 1310, plate = false) { let c = null; for (const ch of CH) { const a = ch[0][1] - 0.05, b = ch[ch.length - 1][1] + ch[ch.length - 1][2] + 0.2; if (t >= a && t < b) c = ch; } if (!c) return '';
  const col = dark ? '#FFFFFF' : K.navy, mut = dark ? 'rgba(255,255,255,.42)' : 'rgba(11,19,36,.38)';
  return `<div style="position:absolute;left:64px;right:64px;bottom:${1920 - by}px;text-align:center;font:600 44px/1.2 Plex;${plate ? 'background:rgba(11,19,36,.94);border-radius:24px;padding:18px 24px;' : ''}${dark ? 'text-shadow:0 2px 12px rgba(11,19,36,.9)' : ''}">${c.map((w) => `<span style="color:${t >= w[1] - 0.03 ? col : mut}">${w[0]}</span>`).join(' ')}</div>`; }
// ---------- product card in the real app skin ----------
const card = (inner, w = 952, extra = '') => `<div style="width:${w}px;background:${K.card};border:2px solid ${K.line};border-radius:40px;color:${K.ink};${extra}">${inner}</div>`;
const chip = (txt, kind = 'days') => { const S = { days: ['#1A2B52', '#34508F', '#7FA6F0'], pursue: [K.pg, '#1E6B43', K.pgt], gold: [K.gold, K.gold, '#161200'], mute: ['transparent', K.line, K.mute] }[kind]; return `<span style="display:inline-block;font:600 30px Plex;padding:6px 18px;border-radius:14px;background:${S[0]};border:2px solid ${S[1]};color:${S[2]}">${txt}</span>`; };
const sring = (score, r = 48, k = 1) => { const C2 = 2 * Math.PI * r; return `<div style="position:relative;width:${2 * r + 16}px;height:${2 * r + 16}px;flex:none"><svg width="${2 * r + 16}" height="${2 * r + 16}"><circle cx="${r + 8}" cy="${r + 8}" r="${r}" fill="none" stroke="#3A4766" stroke-width="8"/><circle cx="${r + 8}" cy="${r + 8}" r="${r}" fill="none" stroke="${K.gold}" stroke-width="8" stroke-linecap="round" stroke-dasharray="${C2}" stroke-dashoffset="${C2 * (1 - (score / 100) * k)}" transform="rotate(-90 ${r + 8} ${r + 8})"/></svg><div class="abs" style="inset:0;display:flex;align-items:center;justify-content:center;font:600 32px Plex;color:${K.gold}">${(score * k).toFixed(1)}</div></div>`; };
const check = (k, sz = 48) => `<div style="width:${sz}px;height:${sz}px;border-radius:50%;background:#1C8A54;display:flex;align-items:center;justify-content:center;flex:none;transform:scale(${lerp(0.4, 1, SPR(k * 0.6))});opacity:${cl(k * 3)}"><svg width="${sz * 0.6}" height="${sz * 0.6}" viewBox="0 0 24 24"><path d="M4 12.5l5 5L20 6.5" fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/></svg></div>`;
const T = (h, t0, lt0, col = K.ink, size = 132) => `<div class="abs" style="left:64px;right:64px;top:300px;font:700 ${size}px/0.95 Barlow;color:${col}">${words(h, t0, lt0, { gap: 0.07 })}</div>`;

function render(t) {
  const sc = Object.values(SC).find((s) => t >= s.t0 && t < s.t1) || SC.cta; const lt = t - sc.t0, D = sc.t1 - sc.t0;
  let ground = K.navy, html = '', map = null, dark = true; phone(0, 0, 1, 0); $('black').style.opacity = 0; $('root').style.setProperty('--accent', K.goldHi);
  const L = (k) => TL.lines[k].t; const W2 = (k, re) => wt(k, re);
  if (sc.id === 'hook') {
    ground = K.paper; dark = false;
    const lost = W2('v1', /^lost/), nev = W2('v1', /^never/); const grey = io(p(t, nev, nev + 0.45));
    const pb = p(lt, D - 0.5, D); const s = pb > 0 ? Math.pow(0.012, E.p3i(pb)) : 1; const fr = [969, 339]; const tx = lerp(540, 540 + (fr[0] - 1000) * 1.0, E.p3i(pb)), ty = lerp(960, 1000 + (fr[1] - 470) * 1.0, E.p3i(pb));
    if (pb > 0) { ground = K.navy; map = { cx: 1000, my0: 470, cy: 1000, z: 1.0, alpha: E.p3i(pb) }; }
    const bar = (i, y, h) => { const k = E.p4o(p(t, lost + i * 0.08, lost + i * 0.08 + 0.12)); return `<div class="abs" style="left:52px;top:${y}px;width:${976 * k}px;height:${h}px;background:${K.navy}"></div>`; };
    let body = ''; for (let i = 0; i < 14; i++) body += `<div style="height:20px;margin:0 0 26px;width:${[92, 70, 84, 60, 88, 75, 66][i % 7]}%;border-radius:4px;background:#D3DAE6"></div>`;
    html += `<div class="abs" style="left:0;top:0;width:1080px;height:1920px;transform-origin:${fr[0] - 1000 + 540}px ${fr[1] - 470 + 1000}px;transform:translate(${0}px,0) scale(${s});filter:blur(${pb * 6}px)">
      <div class="abs" style="left:0;right:0;top:0;bottom:0;background:${K.paper}"></div>
      <div class="abs" style="left:64px;width:952px;top:220px;height:1700px;background:#fff;border-radius:24px 24px 0 0;box-shadow:0 30px 70px -10px rgba(11,19,36,.25)"></div>
      <div class="abs" style="left:112px;top:270px;display:flex;align-items:center;gap:20px">${flag('fr', 64)}<span style="font:600 36px Plex,DV;color:#5F6B80">Resah · France · public tender</span></div>
      <div class="abs" style="left:112px;right:112px;top:350px;font:700 52px/1.05 Plex;color:${K.navy};white-space:nowrap">Équipements d'ophtalmologie</div>
      <div class="abs num" style="left:104px;top:450px;font:700 300px/0.9 Barlow;letter-spacing:-6px;color:${K.navy}">$182.9M</div>
      <div class="abs" style="left:112px;top:740px;font:700 96px Barlow;color:${K.navy}">26 days <span style="font:600 38px Plex;color:#6B7891">to deadline</span></div>
      ${bar(0, 342, 72)}${bar(1, 442, 290)}${bar(2, 732, 112)}${bar(3, 262, 80)}
      <div class="abs" style="left:64px;width:952px;top:1300px;padding:0 48px">${body}</div>
      <div class="abs" style="left:64px;width:952px;top:220px;height:1700px;background:${K.unseen};opacity:${0.88 * grey};mix-blend-mode:multiply;border-radius:24px 24px 0 0"></div>
      <div class="abs" style="left:0;right:0;top:860px;height:490px;background:${K.navy}"></div>
      <div class="abs" style="left:64px;top:905px;font:700 160px/0.92 Barlow;color:#fff">${words('You never', -1, t < 1.7 ? 0 : -1, {})}<br>saw it.</div></div>`;
  } else if (sc.id === 'noise') {
    const o = { cx: 1030, my0: 470, cy: 1060, z: 1.25, alpha: 1 }; map = o;
    const c0 = W2('v2', /^thirty/), c1 = W2('v2', /^thousand/) + 0.25, lv = W2('v2', /^live/), nf = W2('v2', /^ninety/);
    const n = lerp(0, 34644, ex(p(t, c0 - 0.15, c1))); const out = 1 - p(t, L('v3') - 0.3, L('v3'));
    const lk = ex(p(t, lv - 0.05, lv + 0.25)), k195 = ex(p(t, nf - 0.1, nf + 0.2));
    if (out > 0) html += `<div class="abs" style="left:64px;top:300px;opacity:${out}"><div class="num" style="font:700 240px/0.9 Barlow;letter-spacing:-4px;color:#fff">${fmt(n)}</div>
      <div style="display:flex;align-items:center;gap:22px;margin-top:18px"><span style="font:600 48px Plex;color:${K.ink}">live tenders</span><span style="display:inline-flex;align-items:center;gap:12px;font:700 40px Plex;letter-spacing:2px;color:#fff;opacity:${lk};transform:scale(${lerp(1.4, 1, lk)})"><i style="width:18px;height:18px;border-radius:50%;background:#fff;opacity:${0.55 + 0.45 * Math.cos(t * 6)}"></i>LIVE</span></div>
      <div style="margin-top:26px;opacity:${k195};filter:blur(${(1 - k195) * 6}px)"><span class="num" style="font:700 132px/1 Barlow;color:#fff">195</span><span style="font:600 44px Plex;color:${K.mute};margin-left:18px">countries</span></div></div>`;
    // fragments flare out of unseen dots, then fade back to grey
    const FR = [[/^portals/, ['TED', 'PNCP', 'Prozorro', 'SECOP II', 'Etimad', 'AusTender', 'CanadaBuys', 'UNGM', 'BOAMP', 'Find a Tender']], [/^languages/, ['Avis de marché', 'Aviso de licitação', 'Licitación pública', 'Оголошення', 'مناقصة عامة', 'Ausschreibung', 'Bando di gara', 'Przetarg', 'מכרז פומבי', '招标公告']], [/^PDFs/, null]];
    const PTS = [[970, 340], [700, 620], [1180, 330], [690, 520], [1180, 470], [1580, 760], [520, 300], [1130, 560], [960, 360], [990, 300]];
    FR.forEach(([r, list], gi) => { const t0 = W2('v3', r) - 0.35; const nx = FR[gi + 1] ? W2('v3', FR[gi + 1][0]) - 0.35 : L('v4') + 0.2; if (t < t0 || t > nx + 0.3) return;
      for (let i = 0; i < 10; i++) { const [mx, my] = PTS[(i * 3 + gi) % PTS.length]; const [X, Y] = scr2(o, mx, my); const k = ex(p(t, t0 + i * 0.05, t0 + i * 0.05 + 0.25)); const f = 1 - p(t, nx - 0.1, nx + 0.25);
        let px = cl(X, 160, 920), py = cl(Y - 40 - (i % 3) * 70, 560, 1180); if (list) { px = (i % 2 ? 790 : 290) + ((i * 37) % 60 - 30); py = 600 + Math.floor(i / 2) * 128 + (i % 2) * 40; }
        html += list ? `<div class="abs" style="left:${px}px;top:${py}px;transform:translate(-50%,-50%) scale(${lerp(0.6, 1, k)});opacity:${k * f};font:600 36px Plex,DV;color:${K.navy};background:#fff;padding:10px 20px;border-radius:12px;white-space:nowrap">${list[i]}</div>`
          : `<div class="abs" style="left:${px}px;top:${py}px;transform:translate(-50%,-50%) scale(${lerp(0.6, 1, k)});opacity:${k * f}">${appIcon(i % 3 ? 'pdf' : 'doc', 104)}</div>`; } });
    // "track it all": notices pile up past the frame, then go grey on "unseen"
    const tp = W2('v4', /^Nobody/), us = W2('v4', /^slip/); if (t > tp - 0.1) { html += '<div class="abs" style="left:0;top:0;width:1080px;height:1180px;overflow:hidden">'; for (let i = 0; i < 18; i++) { const k = ex(p(t, tp + i * 0.08, tp + i * 0.08 + 0.4)); const g = io(p(t, us + i * 0.03, us + i * 0.03 + 0.35)); const y = lerp(1300, 1000 - i * 50, k) - p(t, us, T5 - 0.3) * 300; const xx = 64 + ((i * 137) % 260);
      html += `<div class="abs" style="left:${xx}px;top:${y}px;width:${700}px;height:150px;background:${mix('#FFFFFF', K.unseen, g)};border-radius:18px;box-shadow:0 20px 40px rgba(0,0,0,.35);padding:22px 28px;opacity:${k}"><div style="height:18px;width:60%;border-radius:4px;background:${mix('#C9D2E0', '#3B4C78', g)}"></div><div style="height:14px;width:85%;margin-top:18px;border-radius:4px;background:${mix('#DCE2EC', '#3B4C78', g)}"></div><div style="height:14px;width:45%;margin-top:14px;border-radius:4px;background:${mix('#DCE2EC', '#3B4C78', g)}"></div></div>`; } html += '</div>'; }
    const hold = p(t, T5 - 0.32, T5 - 0.3); if (hold > 0) html = `<div class="abs" style="inset:0;background:${K.navy};opacity:${0.5 * hold}"></div>` + html;
  } else if (sc.id === 'reveal') {
    const sw = E.p3o(p(lt, 0, 0.75)); const o = { cx: 1030, my0: 470, cy: 1060, z: 1.25, seenY: lerp(0, 1940, sw), allSeen: sw >= 1 ? 1 : 0, dimSeen: lerp(1, 0.55, p(lt, 1.2, 2)) }; map = o;
    const lk = ex(p(lt, 0.55, 1.0)); const wm = ex(p(t, W2('v5', /^Sinder/) - 0.05, W2('v5', /^Sinder/) + 0.35));
    const bi = ex(p(t, W2('v5', /^Business/) - 0.08, W2('v5', /^Business/) + 0.2)), os = ex(p(t, W2('v5', /^OSINT/) - 0.08, W2('v5', /^OSINT/) + 0.2)), cp = ex(p(t, W2('v5', /^co-pilot/) - 0.08, W2('v5', /^co-pilot/) + 0.2));
    html += `<div class="abs" style="left:0;right:0;top:300px;display:flex;align-items:center;justify-content:center;gap:30px;opacity:${cl(lk * 2)};transform:scale(${lerp(1.25, 1, lk)})">${MARK(190, 'b', io(p(lt, 0.55, 1.1)))}<div style="font:700 190px/1 Barlow;letter-spacing:5px;color:#fff;clip-path:inset(0 ${100 - wm * 100}% 0 0)">SINDER</div></div>
      <div class="abs" style="left:64px;right:64px;top:600px;background:rgba(11,19,36,.82);padding:30px 0">
        <div style="font:600 72px/1 Barlow;color:${K.ink};opacity:${bi};filter:blur(${(1 - bi) * 6}px)">Business intelligence</div>
        <div style="display:flex;gap:16px;margin-top:26px;opacity:${os}">${chip('OSINT', 'gold')}${chip('AI agents', 'mute')}</div>
        <div style="font:700 132px/1 Barlow;color:#fff;margin-top:34px;opacity:${cp};filter:blur(${(1 - cp) * 6}px)">Deal <span style="color:${K.goldHi}">co-pilot</span></div></div>`;
  } else if (sc.id === 'army') {
    map = { cx: 1030, my0: 470, cy: 1060, z: 1.25, allSeen: 1, dimSeen: 0.45, alpha: 0.8 };
    const AG = [['Tender hunter', 'TED (EU)'], ['Tender hunter', 'PNCP Brazil'], ['Award tracker', 'World Bank'], ['Trade records', 'customs data'], ['Registry check', 'LEI registry'], ['Price scout', 'UCDA Uganda'], ['News watch', 'GDELT'], ['Supplier finder', 'Tridge directory'], ['Tender hunter', 'Prozorro Ukraine'], ['Award tracker', 'SECOP II Colombia']];
    const VB = ['reading', 'translating', 'scoring', 'matching', 'checking', 'filing'];
    const pull = io(p(lt, 0.15, 1.45)); const sc2 = lerp(2.0, 1, pull); const rl = p(lt, 1.6, 2.6); const ry = lerp(470, 1290, rl);
    let rows = ''; AG.forEach(([n, s], i) => { const y0 = 470 + i * 68; const on = ry > y0 + 30 || rl >= 1; const vb = VB[(Math.floor(t * 1.5 + i * 0.7)) % VB.length];
      rows += `<div style="display:flex;align-items:center;gap:16px;height:68px;padding:0 30px;border-top:${i ? '2px solid ' + K.div : 'none'}"><i style="width:14px;height:14px;border-radius:50%;background:${on ? K.goldHi : K.unseen};flex:none"></i><b style="font:600 32px Plex;color:${K.ink};white-space:nowrap">${n}</b><span style="font:500 30px Plex;color:${K.mute};flex:1;white-space:nowrap;overflow:hidden">· ${s}</span><span style="font:600 30px Plex;color:${on ? K.gold : K.unseen}">${on ? vb : 'queued'}</span></div>`; });
    html += `<div class="abs" style="left:64px;top:470px;width:952px;transform-origin:540px 34px;transform:scale(${sc2});opacity:${ex(p(lt, 0, 0.3))}">${card(rows)}</div>`;
    if (rl > 0 && rl < 1) html += `<div class="abs" style="left:0;right:0;top:${ry}px;height:4px;background:${K.goldHi}"></div>`;
    html += `<div class="abs" style="left:64px;top:300px;font:700 132px/0.95 Barlow;color:#fff;opacity:${p(lt, 0.9, 1.3)}">AI agents <span style="color:${K.goldHi}">24/7</span></div>`;
  } else if (sc.id === 'rank') {
    ground = K.paper; dark = false; const rk = W2('f1', /^ranked/), tr = W2('f1', /^translated/);
    const climb = io(p(t, rk - 0.05, rk + 0.45)); const rl = p(t, tr - 0.15, tr + 0.45); const en = rl > 0.5;
    const R = [{ s: 61.4, f: 'gb', h: 'Hygiene services and equipment', b: 'Scotland Excel · $112.4M', d: '25 days' }, { s: 46.9, f: 'dk', h: 'Pharmaceutical products', b: 'Amgros · Denmark · $118.3M', d: '37 days' }];
    const FRr = { s: 73.6, f: 'fr', h: en ? 'Ophthalmology equipment' : "Équipements d'ophtalmologie", b: 'Resah · France · $182.9M', d: '26 days' };
    const rowH = 200; const yFr = lerp(2 * rowH, 0, climb); const yUK = lerp(0, rowH, climb), yDK = lerp(rowH, 2 * rowH, climb);
    const row = (r, y, hl, n) => `<div class="abs" style="left:0;right:0;top:${y}px;height:${rowH}px;display:flex;align-items:center;gap:26px;padding:0 40px;border-top:2px solid ${K.div};background:${hl ? '#1A2A4A' : 'transparent'}"><div style="font:700 64px Barlow;color:${hl ? K.gold : K.mute};width:44px">${n}</div>${sring(r.s, 46)}<div style="flex:1;min-width:0"><div style="display:flex;align-items:center;gap:12px">${flag(r.f, 40)}<span style="font:500 30px Plex;color:${K.mute};white-space:nowrap">${r.b}</span></div><div style="font:600 42px/1.15 Plex;color:${K.ink};margin-top:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${r.h}</div><div style="margin-top:10px;display:flex;gap:10px">${chip(r.d)}${hl ? chip('Pursue', 'pursue') : ''}</div></div></div>`;
    const ck = ex(p(lt, 0, 0.45));
    html += T('Ranked by fit', 0.05, lt, K.navy);
    html += `<div class="abs" style="left:64px;top:${lerp(1500, 520, ck)}px;width:952px;height:${3 * rowH + 4}px;background:${K.card};border:2px solid ${K.line};border-radius:40px;overflow:hidden;box-shadow:0 2px 0 rgba(11,19,36,.1),0 30px 70px -10px rgba(11,19,36,.35)">${row(R[0], yUK, 0, climb > 0.5 ? 2 : 1)}${row(R[1], yDK, 0, climb > 0.5 ? 3 : 2)}${row(FRr, yFr, climb > 0.5, climb > 0.5 ? 1 : 3)}
      ${rl > 0 && rl < 1 ? `<div class="abs" style="left:0;right:0;top:${lerp(0, 3 * rowH, rl)}px;height:6px;background:${K.goldHi}"></div>` : ''}</div>`;
    html += `<div class="abs" style="left:64px;top:1170px;font:500 30px Plex;color:${K.inkMute};opacity:${ck}">From 34,644 live tenders, any language</div>`;
  } else if (sc.id === 'sup') {
    const o = { cx: 1004, my0: 316, cy: 1560, z: 3.0, allSeen: 1, dimSeen: 0.4, lit: [[1004, 316, ex(p(lt, 0.3, 0.6))], [969, 339, ex(p(lt, 0.4, 0.7))]] }; map = o;
    const aw = W2('f2', /^award/), cu = W2('f2', /^customs/); const ck = ex(p(lt, 0, 0.45));
    html += T('Proven makers', 0.05, lt, '#fff');
    html += `<div class="abs" style="left:64px;top:${lerp(1500, 520, ck)}px">${card(`<div style="padding:40px 44px"><div style="display:flex;align-items:center;gap:16px">${flag('de', 48)}<span style="font:500 30px Plex;color:${K.mute}">Germany · manufacturer</span><span style="margin-left:auto">${check(p(t, cu + 0.2, cu + 0.6), 56)}</span></div><div style="font:600 56px Plex;color:#fff;margin-top:14px">Optix Medical GmbH</div><div style="font:500 34px Plex;color:${K.ink};margin-top:10px">Ophthalmic equipment for public hospitals</div></div>`)}</div>`;
    const slip = (y, txt, sub, k) => `<div class="abs" style="left:${lerp(1100, 64, k)}px;top:${y}px;width:952px;opacity:${k}">${card(`<div style="display:flex;align-items:center;gap:20px;padding:26px 40px"><i style="width:14px;height:14px;border-radius:50%;background:${K.goldHi}"></i><div><div style="font:600 40px Plex;color:#fff">${txt}</div><div style="font:500 30px Plex;color:${K.mute}">${sub}</div></div></div>`)}</div>`;
    const ak = ex(p(t, aw - 0.08, aw + 0.35)), ck2 = ex(p(t, cu - 0.08, cu + 0.35));
    html += slip(840, 'Award records', 'sold to 6 public hospitals', ak) + slip(985, 'Customs data', 'exports under HS 9018.50', ck2);
    const [dx, dy] = scr2(o, 1004, 316); html += thread(dx, dy - 20, 1000, 1080, p(t, cu + 0.1, cu + 0.6)) + thread(dx - 60, dy - 20, 1000, 930, p(t, aw + 0.1, aw + 0.6));
    html += `<div class="abs" style="left:64px;top:1135px;font:500 28px Plex;color:${K.mute};opacity:${ck}">Company name illustrative</div>`;
  } else if (sc.id === 'contacts') {
    ground = K.paper; dark = false; const ck = ex(p(lt, 0, 0.45)); const scan = p(t, W2('f3', /^straight/) - 0.2, W2('f3', /^sites/) + 0.2);
    html += T('Contacts, mapped', 0.05, lt, K.navy);
    html += `<div class="abs" style="left:64px;top:${lerp(1500, 490, ck)}px;width:952px;height:380px;background:#fff;border-radius:32px;overflow:hidden;box-shadow:0 2px 0 rgba(11,19,36,.1),0 30px 70px -10px rgba(11,19,36,.3)">
      <div style="height:64px;background:#EEF1F6;display:flex;align-items:center;gap:12px;padding:0 24px"><i style="width:14px;height:14px;border-radius:50%;background:#E5534B"></i><i style="width:14px;height:14px;border-radius:50%;background:#E9B949"></i><i style="width:14px;height:14px;border-radius:50%;background:#3EC28A"></i><div style="margin-left:16px;flex:1;height:40px;border-radius:10px;background:#fff;font:500 28px/40px Plex;color:#5A6782;padding:0 16px">optix-medical.example/contact</div></div>
      <div style="padding:30px 40px;font:700 44px Plex;color:${K.navy}">Contact us</div><div style="padding:0 40px;font:500 30px/1.6 Plex;color:#3C475C">Export department · Sales · Service<br>Headquarters, Germany</div>
      <div class="abs" style="left:0;right:0;top:${64 + scan * 316}px;height:6px;background:${K.goldHi};opacity:${scan > 0 && scan < 1 ? 1 : 0}"></div></div>`;
    const B2 = [['gmail', 'Export desk', 'export@ ••••••.de'], ['whatsapp', 'Sales', '+49 ••• ••• ••••']];
    B2.forEach(([ic, h, v], i) => { const k = ex(p(t, W2('f3', i ? /^sales/ : /^Export/) + 0.1, W2('f3', i ? /^sales/ : /^Export/) + 0.5));
      html += `<div class="abs" style="left:64px;top:${890 + i * 142}px;width:952px;opacity:${k};transform:translateY(${(1 - k) * 40}px)">${card(`<div style="display:flex;align-items:center;gap:22px;padding:24px 36px">${appIcon(ic, 64)}<div><div style="font:600 40px Plex;color:#fff">${h}</div><div style="font:500 32px Plex;color:${K.mute}">${v}</div></div><span style="margin-left:auto">${chip('own website', 'mute')}</span></div>`)}</div>`; });
    html += `<div class="abs" style="left:64px;top:1215px;font:500 28px Plex;color:${K.inkMute};opacity:${ck}">Numbers masked · company illustrative</div>`;
  } else if (sc.id === 'reverse') {
    map = { cx: 1030, my0: 470, cy: 1060, z: 1.25, allSeen: 1, dimSeen: 0.35, alpha: 0.7 };
    const wipe = E.io(p(lt, 0, 0.4)); const bp = W2('f4', /^blueprint/); const rl = p(t, bp - 0.15, bp + 0.9); const ry = 470 + rl * 700;
    html += T('Deal blueprint', 0.3, lt, '#fff');
    const F = [['Product', 'Ophthalmic instruments, HS 9018.50'], ['Parties', 'Buyer and seller hints'], ['Proven suppliers', '3, from award records'], ['Benchmark price', 'From import records'], ['Your way in', 'Supply the winning bidder']];
    let rows = ''; F.forEach(([h, v], i) => { const y0 = 470 + 110 + i * 116; const on = ry > y0 + 40; rows += `<div style="padding:16px 44px;height:116px;border-top:2px solid ${on ? K.div : '#E1E6EF'}"><div style="font:500 30px Plex;color:${on ? K.mute : '#6B7891'}">${h}</div>${on ? `<div style="font:600 40px Plex;color:${K.goldHi};margin-top:6px">${v}</div>` : `<div style="height:40px;width:${[78, 60, 70, 55, 82][i]}%;margin-top:10px;background:${K.navy}"></div>`}</div>`; });
    const dk = ex(p(lt, 0.3, 0.75)); const flipped = rl > 0.05;
    html += `<div class="abs" style="left:64px;top:${lerp(1500, 470, dk)}px;width:952px;border-radius:24px;overflow:hidden;background:${flipped ? K.card : '#fff'};border:2px solid ${flipped ? K.line : '#fff'}"><div style="padding:30px 44px;height:110px;font:700 44px Barlow;letter-spacing:2px;color:${flipped ? K.goldHi : K.navy}">${flipped ? 'THE BLUEPRINT' : 'PURCHASE CONTRACT'}</div>${rows}</div>`;
    if (rl > 0 && rl < 1) html += `<div class="abs" style="left:0;right:0;top:${ry}px;height:5px;background:${K.goldHi}"></div>`;
    html += `<div class="abs" style="left:64px;top:1200px;font:500 28px Plex;color:${K.mute};opacity:${dk}">Illustrative example</div>`;
    if (wipe < 1) html += `<div class="abs" style="left:0;top:0;width:${(1 - wipe) * 1080}px;height:1920px;margin-left:${wipe * 1080}px;background:${K.paper}"></div>`;
  } else if (sc.id === 'price') {
    const o = { cx: 1112, my0: 552, cy: 1560, z: 3.0, allSeen: 1, dimSeen: 0.4, lit: [[1112, 552, ex(p(lt, 0.2, 0.5))]] }; map = o;
    const e18 = W2('f5', /^eighteen/); const n18 = Math.round(lerp(0, 18, ex(p(t, e18 - 0.2, e18 + 0.3))));
    html += `<div class="abs" style="left:64px;top:300px;font:600 34px Plex;color:${K.mute};opacity:${p(lt, 0.1, 0.3)}">Another deal · Arabica coffee</div>
      <div class="abs" style="left:64px;top:350px;display:flex;align-items:baseline;gap:20px;opacity:${p(t, e18 - 0.25, e18)}"><span class="num" style="font:700 132px/1 Barlow;color:#fff">${n18}</span><span style="font:600 44px Plex;color:${K.ink}">official price sources</span></div>`;
    const G = [['Bugisu AA', 2.7215], ['Bugisu A', 2.7115], ['Wugar', 2.7015], ['Drugar', 2.5115]];
    const ck = ex(p(lt, 0.15, 0.6)); let rows = ''; G.forEach(([g, v], i) => { const q = ex(p(lt, 0.5 + i * 0.1, 0.9 + i * 0.1)); rows += `<div style="display:flex;align-items:center;gap:20px;margin-top:18px;opacity:${q}"><div style="width:220px;font:500 32px Plex;color:${K.ink}">${g}</div><div style="flex:1;height:16px;border-radius:8px;background:${K.div}"><div style="width:${q * (v / 2.8) * 100}%;height:100%;border-radius:8px;background:${i ? '#4A5E8C' : K.gold}"></div></div><div class="num" style="width:110px;text-align:right;font:600 34px Plex;color:#fff">$${v.toFixed(2)}</div></div>`; });
    html += `<div class="abs" style="left:64px;top:${lerp(1500, 520, ck)}px">${card(`<div style="padding:40px 44px"><div style="display:flex;align-items:center;gap:16px">${flag('ug', 48)}<span style="font:500 30px Plex;color:${K.mute}">Kampala, Uganda · free on truck</span></div><div style="display:flex;align-items:baseline;gap:16px;margin-top:6px"><span class="num" style="font:700 200px/1 Barlow;color:${K.goldHi};letter-spacing:-4px">$${(2.72 * ex(p(lt, 0.3, 1.0))).toFixed(2)}</span><span style="font:600 64px Barlow;color:#fff">/lb</span></div>${rows}<div id="srcline" style="font:500 30px Plex;color:${K.mute};margin-top:24px">Uganda Coffee Development Authority, 6 Nov 2026</div></div>`)}</div>`;
    const [ux, uy] = scr2(o, 1112, 552); html += thread(ux, uy - 20, 900, 1180, p(lt, 0.9, 1.6));
  } else if (sc.id === 'odds') {
    ground = K.paper; dark = false; const ev = W2('f6', /^expected/), bd = W2('f6', /^bid/), inc = W2('f6', /^incumbent/);
    const fl = io(p(t, ev - 0.1, ev + 0.3)); const ck = ex(p(lt, 0, 0.45)); const win = 0.154 * ex(p(lt, 0.2, 1.2));
    if (fl > 0) ground = mix(K.paper, K.goldHi, fl);
    if (fl < 1) { const R = 300, Cc = Math.PI * R;
      html += T('Your odds', 0.05, lt, K.navy); html += `<div class="abs" style="left:64px;top:446px;display:flex;align-items:center;gap:14px;font:600 34px Plex;color:#3C475C;opacity:${ck}">${flag('fr', 40)}Resah · France · $182.9M</div>`;
      html += `<div class="abs" style="left:64px;top:${lerp(1500, 520, ck) + fl * 300}px;opacity:${1 - fl}">${card(`<div style="position:relative;height:640px"><svg class="abs" style="left:${476 - R - 22}px;top:50px" width="${2 * R + 44}" height="${R + 44}"><path d="M22 ${R + 22} A${R} ${R} 0 0 1 ${2 * R + 22} ${R + 22}" fill="none" stroke="${K.div}" stroke-width="36" stroke-linecap="round"/><path d="M22 ${R + 22} A${R} ${R} 0 0 1 ${2 * R + 22} ${R + 22}" fill="none" stroke="${K.gold}" stroke-width="36" stroke-linecap="round" stroke-dasharray="${Cc}" stroke-dashoffset="${Cc * (1 - win)}"/></svg>
        <div class="abs" style="left:0;right:0;top:190px;text-align:center"><div class="num" style="font:700 200px/1 Barlow;color:#fff">${Math.round(win * 100)}%</div><div style="font:500 32px Plex;color:${K.mute}">win chance · 2 expected bidders</div></div>
        <div class="abs" style="left:44px;right:44px;top:500px;padding-top:26px;border-top:2px solid ${K.div};display:flex;align-items:center;gap:16px;opacity:${p(t, inc - 0.05, inc + 0.25)}">${check(p(t, inc, inc + 0.4), 48)}<span style="font:600 36px Plex,DV;color:#fff">Incumbent and buyer history checked</span></div></div>`)}</div>`; }
    if (fl > 0) { const k = ex(p(t, ev, ev + 0.6)); const pk = p(t, bd - 0.05, bd + 0.15);
      html += `<div class="abs" style="left:64px;top:430px;opacity:${fl}"><div style="font:600 44px Plex;color:${K.navy}">expected value</div><div class="num" style="font:700 300px/0.95 Barlow;letter-spacing:-6px;color:${K.navy}">$${(1.744 * k).toFixed(2)}M</div>
        <div style="font:500 32px Plex;color:#3A3015;margin-top:8px">Ophthalmology equipment · Resah</div><div style="margin-top:40px;opacity:${pk};transform:scale(${lerp(1.3, 1, SPR(pk * 0.5))});transform-origin:left center;display:inline-block">${chip('Pursue', 'pursue').replace('30px', '48px').replace('6px 18px', '12px 34px')}</div></div>`; dark = false; }
  } else if (sc.id === 'build') {
    map = { cx: 1030, my0: 470, cy: 1060, z: 1.25, allSeen: 1, dimSeen: 0.35, alpha: 0.7 };
    const one = W2('v11', /^one/); const ph = ex(p(lt, 0, 0.5)); phone(540, lerp(1900, 1250, ph), 0.84, 1); ui(70);
    html += `<div class="abs" style="left:64px;top:300px;font:700 132px/0.95 Barlow;color:#fff">${words('One screen', one - sc.t0 - 0.1, lt)}</div>`;
    const P2 = [['#1 · 73.6', 120, 470], ['Optix ✓', 600, 470], ['$2.72/lb', 120, 590], ['EV $1.74M', 600, 590]];
    P2.forEach(([txt, x0, y0], i) => { const k = io(p(lt, 0.35 + i * 0.12, 0.95 + i * 0.12)); const x = lerp(x0, 540, k), y = lerp(y0, 1000, k), s = lerp(1, 0.25, k);
      html += `<div class="abs" style="left:${x}px;top:${y}px;transform:translate(-50%,-50%) scale(${s});opacity:${1 - p(k, 0.85, 1)};filter:blur(${Math.sin(Math.PI * k) * 5}px)">${chip(txt, i === 3 ? 'gold' : 'days').replace('30px', '40px')}</div>`; });
  } else if (sc.id === 'tg') {
    ground = K.tg; dark = false; const q = L('v12') + 0.2, yes = W2('v13', /^yes/) - 0.08;
    phone(540, lerp(1950, 1180, ex(p(lt, 0, 0.45))), 0.84, 1);
    const chat = [[q, 'me', "What's our win chance on the Resah tender?"], [q + 0.8, 'bot', `<b>15%</b> · 2 expected bidders<br>Expected value <b style="color:#B07A0E">$1.74M</b>`], [L('v13') - 0.3, 'ask', 'Send the RFQ to 3 suppliers?']];
    let h = ''; for (const [tc, w, x] of chat) { const k = ex(p(t, tc, tc + 0.3)); if (k <= 0) continue; const st = `opacity:${k};transform:translateY(${(1 - k) * 30}px)`;
      if (w === 'me') h += `<div style="${st};align-self:flex-end;max-width:84%;background:#EEFFDE;color:#0B1324;padding:22px 26px;border-radius:30px 30px 8px 30px;font:500 34px/1.3 Plex">${x}</div>`;
      else if (w === 'bot') h += `<div style="${st};align-self:flex-start;max-width:86%;background:#fff;color:#0B1324;padding:22px 26px;border-radius:30px 30px 30px 8px;font:500 34px/1.35 Plex">${x}</div>`;
      else { const a = t >= yes; const pr = p(t, yes - 0.08, yes) - p(t, yes, yes + 0.1); h += `<div style="${st};align-self:flex-start;width:88%"><div style="background:#fff;color:#0B1324;padding:22px 26px;border-radius:30px 30px 30px 8px;font:500 34px Plex">${x}</div><div style="display:flex;gap:10px;margin-top:10px"><div style="flex:1;text-align:center;padding:24px;border-radius:20px;background:${a ? '#1C8A54' : 'rgba(11,19,36,.28)'};color:#fff;font:600 36px Plex,DV;transform:scale(${1 - 0.06 * pr})">${a ? 'Approved ✓' : 'Approve'}</div><div style="flex:1;text-align:center;padding:24px;border-radius:20px;background:rgba(11,19,36,.28);color:#fff;font:600 36px Plex">Reject</div></div></div>`; } }
    scr(`<div class="abs" style="inset:0;background:#C9DCEB"><div style="height:190px;padding-top:80px;background:#fff;display:flex;align-items:center;gap:20px;padding-left:30px;border-bottom:1px solid #DDE3EC"><div style="border-radius:50%;overflow:hidden;width:76px;height:76px">${MARK(76, 't')}</div><div><div style="font:700 34px Plex;color:#0B1324">Sinder Deal Agent</div><div style="font:500 26px Plex;color:#2481CC">bot</div></div></div><div class="abs" style="left:0;right:0;top:190px;bottom:0;padding:26px;display:flex;flex-direction:column;justify-content:flex-end;gap:14px">${h}</div></div>`);
    html += `<div class="abs" style="left:64px;top:300px;display:flex;align-items:center;gap:24px;opacity:${ex(p(lt, 0.1, 0.4))}"><div style="width:104px;height:104px;border-radius:50%;background:#fff;display:flex;align-items:center;justify-content:center">${icon('telegram', 104, K.tg)}</div><span style="font:700 120px/1 Barlow;color:${K.navy}">On Telegram</span></div>`;
    const ir = E.p3i(p(lt, D - 0.36, D)); if (ir > 0) html += `<div class="abs" style="inset:0;background:${K.navy};clip-path:circle(${ir * 2100}px at 400px 1500px)"></div>`;
  } else if (sc.id === 'cta') {
    map = { cx: 1030, my0: 470, cy: 1400, z: 1.25, allSeen: 1, dimSeen: lerp(1, 0.4, p(t, W2('v14', /^Sinder/), W2('v14', /^Sinder/) + 0.6)) };
    const s1 = W2('v14', /^Sinder/), se = W2('v14', /^See/), pa = W2('v15', /^Partners/), lt0 = W2('v15', /^let/);
    const rl = p(t, s1 - 0.1, s1 + 0.5); const lk = ex(p(t, s1, s1 + 0.4));
    const nw = TL.lines.n1.words; const nOut = 1 - p(t, s1 - 0.4, s1 - 0.1);
    if (nOut > 0) html += `<div class="abs" style="left:64px;right:64px;top:560px;text-align:center;font:700 128px/1 Barlow;color:#fff;opacity:${nOut}">${nw.map(([w, wt0], i) => { const k = ex(p(t, wt0 - 0.06, wt0 + 0.1)); return `<span style="display:inline-block;margin:0 14px;opacity:${k};filter:blur(${(1 - k) * 6}px);color:${i >= 4 ? K.goldHi : '#fff'}">${w}</span>` + (i === 3 ? '<br>' : ''); }).join('')}</div>`;
    html += `<div class="abs" style="left:0;right:0;top:340px;display:flex;align-items:center;justify-content:center;gap:28px;clip-path:inset(0 ${100 - rl * 100}% 0 0)">${MARK(150, 'c', io(rl))}<div style="font:700 150px/1 Barlow;letter-spacing:5px;color:#fff">SINDER</div></div>
      ${rl > 0 && rl < 1 ? `<div class="abs" style="left:${rl * 1080}px;top:300px;width:5px;height:240px;background:${K.goldHi}"></div>` : ''}
      <div class="abs" style="left:64px;right:64px;top:600px;text-align:center;font:700 132px/1 Barlow;color:#fff">${words('See every deal.', se - sc.t0 - 0.08, lt, { gold: [1] })}</div>
      <div class="abs" style="left:64px;right:64px;top:800px;text-align:center;font:600 64px Barlow;color:${K.mute};opacity:${ex(p(t, pa - 0.1, pa + 0.3))}">Partners and investors</div>
      <div class="abs" style="left:0;right:0;top:880px;text-align:center;font:700 200px/1 Barlow;color:${K.goldHi};opacity:${ex(p(t, lt0 - 0.05, lt0 + 0.3))}">Let's talk.</div>
      <div class="abs" style="left:0;right:0;top:1110px;display:flex;justify-content:center;align-items:center;gap:20px;opacity:${ex(p(t, lt0 + 0.3, lt0 + 0.7))}">${appIcon('gmail', 64)}<span style="font:600 56px Plex;color:#fff">Etamar@sinder.pro</span></div>
      <div class="abs" style="left:0;right:0;top:1230px;text-align:center;font:500 28px Plex;color:${K.mute};opacity:${p(t, lt0 + 0.5, lt0 + 0.9)}">sinder.pro · Music: Future Business, Marco Margna, CC BY 3.0</div>`;
    $('black').style.opacity = p(lt, D - 0.45, D);
  }
  $('ground').style.background = ground; scope(map); $('fx').innerHTML = html;
  const noCap = sc.id === 'cta' && (t >= wt('v15', /^Partners/) - 0.1 || t < wt('v14', /^Sinder/) - 0.1); $('subs').innerHTML = noCap ? '' : caption(t, sc.id === 'hook' ? true : dark, sc.id === 'tg' ? 520 : 1310, sc.id === 'build');
}
const tl = gsap.timeline({ paused: true });
const clock = { t: 0 };
tl.to(clock, { t: TL.total, duration: TL.total, ease: 'none', onUpdate: () => render(tl.time()) }, 0);
render(0);
window.__timelines = window.__timelines || {};
window.__timelines['main'] = tl;
