// Sinder brand film, vertical. Everything on screen is a function of timeline time t (render(t)), driven by one paused GSAP timeline.
const $ = (id) => document.getElementById(id);
const cl = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x)), p = (t, a, b) => cl((t - a) / (b - a)), lerp = (a, b, k) => a + (b - a) * k;
const E = { expo: gsap.parseEase('expo.out'), p4o: gsap.parseEase('power4.out'), io: gsap.parseEase('power2.inOut'), p3i: gsap.parseEase('power3.in'), p3o: gsap.parseEase('power3.out'), back: gsap.parseEase('back.out(1.5)') };
const ex = (x) => E.expo(cl(x)), io = (x) => E.io(cl(x)), pin = (x) => E.p3i(cl(x)), bk = (x) => E.back(cl(x));
const fmt = (n) => Math.round(n).toLocaleString('en-US');
const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const mix = (a, b, k) => { const A = hex(a), B = hex(b); return `rgb(${A.map((v, i) => Math.round(lerp(v, B[i], cl(k)))).join(',')})`; };
const C = { navy: '#0B1324', gold: '#F0CF7A', ground_gold: '#E9B949', light: '#EDF0F5', card: '#101A30', tg: '#1E88C7', green: '#22A565', deep: '#9A6B12', ink: '#0B1324', mute: '#6B7891' };
const TL = window.TL, MAP = window.MAP, ICON = window.ICON;
const SC = Object.fromEntries(TL.scenes.map(([id, t0, t1]) => [id, { id, t0, t1 }]));
const W = TL.words;
const wt = (k, re) => { const w = W[k].find((x) => re.test(x[0])); return w ? w[1] : TL.vo[k][0]; };
const icon = (name, size, fill = '#fff') => { const i = ICON[name]; return `<svg viewBox="0 0 24 24" width="${size}" height="${size}"><path d="${i.path}" fill="${fill}"/></svg>`; };
const MARK = (sz, id, draw = 1) => `<svg viewBox="0 0 64 64" width="${sz}" height="${sz}"><defs><linearGradient id="g${id}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1b2d52"/><stop offset="1" stop-color="#0b1324"/></linearGradient><linearGradient id="d${id}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f0cf7a"/><stop offset="1" stop-color="#b8902e"/></linearGradient></defs><rect width="64" height="64" rx="15" fill="url(#g${id})" stroke="#3a5488" stroke-width="1.2"/><path d="M44 20c-2.5-4-7-6-12-6-7 0-12 4-12 9.5 0 11 24 7 24 18 0 6-5.5 10-13 10-6 0-10.5-2.5-13-6.5" fill="none" stroke="url(#d${id})" stroke-width="5.5" stroke-linecap="round" stroke-dasharray="120" stroke-dashoffset="${120 * (1 - draw)}"/><circle cx="45" cy="16.5" r="3.4" fill="#f0cf7a" opacity="${cl(draw * 3 - 2)}"/><circle cx="19" cy="47.5" r="3.4" fill="#f0cf7a" opacity="${cl(draw * 3 - 2)}"/></svg>`;
const flag = (c, w) => `<img src="assets/flags/${c}.svg" style="width:${w}px;height:${w * 0.75}px;border-radius:${w * 0.08}px;object-fit:cover;flex:none">`;

// ---------- per-word titles: blur 6 -> 0, opacity, 0.067 s apart, no translate ----------
function words(text, t0, t, opts = {}) {
  const { gap = 0.067, gold = [], out = 0 } = opts;
  return text.split(' ').map((w, i) => { const k = p(t, t0 + i * gap, t0 + i * gap + 0.13); const o = k * (1 - out);
    return `<span style="display:inline-block;opacity:${o};filter:blur(${(1 - k) * 6 + out * 8}px);color:${gold.includes(i) ? 'var(--accent)' : 'inherit'}">${w}</span>`; }).join(' ');
}
// ---------- subtitles: phrases of up to 5 words from the narration word times ----------
const PHR = [];
for (const [k, ws] of Object.entries(W)) { let cur = []; ws.forEach((w, i) => { cur.push(w); const end = /[.,?]$/.test(w[0]); if (cur.length >= 5 || (end && cur.length >= 2) || i === ws.length - 1) { PHR.push(cur); cur = []; } }); }
function subtitle(t) {
  let ph = null; for (const c of PHR) { const a = c[0][1] - 0.05, b = c[c.length - 1][1] + c[c.length - 1][2] + 0.25; if (t >= a && t < b) ph = c; }
  if (!ph) return '';
  return `<div class="sub">${ph.map((w) => `<span style="opacity:${t >= w[1] - 0.03 ? 1 : 0.42}">${w[0]}</span>`).join(' ')}</div>`;
}
// ---------- the dot map ----------
function drawMap(t, o) {
  const c = $('map'), x = c.getContext('2d'); x.clearRect(0, 0, 1080, 1920); if (!o || o.alpha <= 0) return;
  const { cx, my0, cy, z, alpha, reveal = 99, focus = null, live = 0, ilR = 0 } = o;
  x.save(); x.globalAlpha = alpha;
  for (const [mx, my, h, f] of MAP.dots) {
    const X = 540 + (mx - cx) * z, Y = cy + (my - my0) * z; if (X < -20 || X > 1100 || Y < -20 || Y > 1940) continue;
    const r0 = Math.max(1.4, 0.9 * z * 0.62);
    if (h > 0 && f * 0.85 < reveal) { const k = cl((reveal - f * 0.85) / 0.25); const blink = live ? 1 - 0.55 * Math.sin(Math.PI * cl(live)) : 1;
      x.fillStyle = `rgba(240,207,122,${(0.55 + 0.45 * h) * k * blink})`; x.beginPath(); x.arc(X, Y, r0 * (1 + 1.6 * h), 0, 6.2832); x.fill(); }
    else { x.fillStyle = '#2C3D66'; x.beginPath(); x.arc(X, Y, r0, 0, 6.2832); x.fill(); }
  }
  if (focus) { const X = 540 + (focus[0] - cx) * z, Y = cy + (focus[1] - my0) * z; x.fillStyle = '#F0CF7A'; x.beginPath(); x.arc(X, Y, focus[2], 0, 6.2832); x.fill(); }
  x.restore();
}
// ---------- phone ----------
const PH = { w: 704, h: 1490, sw: 676, sh: 1462 };
function phone(x, y, s, o = 1, extra = '') { const el = $('phone'); el.style.opacity = o; el.style.transform = `translate(${x - PH.w / 2}px,${y - PH.h / 2}px) scale(${s}) ${extra}`; el.style.display = o > 0 ? 'block' : 'none'; }
let curUI = -1;
function ui(n, dim = 0) { if (n !== curUI) { const imgs = $('uiwrap').children; for (let i = 0; i < imgs.length; i++) imgs[i].style.opacity = i === n ? 1 : 0; curUI = n; } $('uiwrap').style.opacity = 1; $('uiwrap').style.filter = dim ? `brightness(${1 - dim})` : 'none'; $('scrhtml').innerHTML = ''; }
function scr(html) { $('uiwrap').style.opacity = 0; curUI = -1; $('scrhtml').innerHTML = html; }

// ---------- content ----------
const NOTI = [['whatsapp', 'WhatsApp', 'Supplier, Lagos', 'price??'], ['gmail', 'Gmail', 'Buyer, Nairobi', 'Re: Re: Re: quotation'], ['pdf', 'Files', 'RFQ_final_v7.pdf', 'Downloaded 2 min ago'], ['whatsapp', 'WhatsApp', 'Agent', 'who makes this?'], ['gmail', 'Gmail', 'Forwarder', 'FOB or CFR?'], ['call', 'Phone', 'Missed call', 'Buyer, Dar es Salaam'], ['whatsapp', 'WhatsApp', 'Buyer', 'deadline is Friday'], ['doc', 'Files', 'Tender_EN(2).docx', 'Shared with you'], ['gmail', 'Gmail', 'Bank', 'LC draft attached'], ['whatsapp', 'WhatsApp', 'Supplier', 'is this supplier real?']];
const notiT = (i) => { const s = SC.problem; const a = s.t0 + 0.35, b = wt('r2', /^PDFs/) + 0.2; const u = i / (NOTI.length - 1); return a + (b - a) * (1 - Math.pow(1 - u, 1.5)); };
function appIcon(kind, sz) {
  if (kind === 'whatsapp') return `<div class="ai" style="width:${sz}px;height:${sz}px;background:#25D366">${icon('whatsapp', sz * 0.62)}</div>`;
  if (kind === 'gmail') return `<div class="ai" style="width:${sz}px;height:${sz}px;background:#fff">${icon('gmail', sz * 0.62, '#EA4335')}</div>`;
  if (kind === 'call') return `<div class="ai" style="width:${sz}px;height:${sz}px;background:#34C759"><svg viewBox="0 0 24 24" width="${sz * 0.56}" height="${sz * 0.56}"><path fill="#fff" d="M6.6 10.8c1.4 2.8 3.8 5.1 6.6 6.6l2.2-2.2c.3-.3.7-.4 1-.2 1.1.4 2.3.6 3.6.6.6 0 1 .4 1 1V20c0 .6-.4 1-1 1C10.6 21 3 13.4 3 4c0-.6.4-1 1-1h3.5c.6 0 1 .4 1 1 0 1.3.2 2.5.6 3.6.1.3 0 .7-.2 1z"/></svg></div>`;
  const red = kind === 'pdf'; return `<div class="ai" style="width:${sz}px;height:${sz}px;background:${red ? '#E2382F' : '#2B579A'};flex-direction:column"><svg viewBox="0 0 24 24" width="${sz * 0.42}" height="${sz * 0.42}"><path fill="#fff" d="M6 2h8l6 6v14H6z" opacity=".95"/><path fill="${red ? '#E2382F' : '#2B579A'}" d="M14 2v6h6"/></svg><b style="font:700 ${sz * 0.2}px Plex;color:#fff;margin-top:${sz * 0.03}px">${red ? 'PDF' : 'DOCX'}</b></div>`;
}
function lockScreen(t, n, swipe = 0) {
  let h = `<div class="abs" style="inset:0;background:linear-gradient(180deg,#1B2A4A,#0B1324)"><div style="text-align:center;margin-top:150px;font:600 34px Plex;color:#C9D3E6">Monday 9 November</div><div style="text-align:center;font:600 210px/1 Barlow;color:#fff;letter-spacing:-2px;margin-top:6px">08:12</div>
  <div class="abs" style="left:24px;right:24px;bottom:56px;display:flex;flex-direction:column-reverse;gap:14px">`;
  for (let i = 0; i < n; i++) { const k = ex(p(t, notiT(i), notiT(i) + 0.4)); const [kind, app, who, msg] = NOTI[i]; const sx = swipe * (1300 + i * 40);
    h += `<div style="background:rgba(236,240,247,.94);border-radius:34px;padding:22px 24px;display:flex;gap:20px;align-items:center;opacity:${k};transform:translate(${sx}px,${(1 - k) * -40}px) scale(${lerp(0.94, 1, k)})">${appIcon(kind, 76)}<div style="flex:1;min-width:0"><div style="display:flex;justify-content:space-between;font:600 26px Plex;color:#5F6B80"><span>${app}</span><span>now</span></div><div style="font:700 31px Plex;color:#0B1324;margin-top:2px">${who}</div><div style="font:500 31px Plex;color:#2A3346;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${msg}</div></div></div>`; }
  return h + '</div></div>';
}
function homeScreen(t, press, o) { return `<div class="abs" style="inset:0;opacity:${o};background:linear-gradient(180deg,#1B2A4A,#0B1324)"><div class="abs" style="left:0;right:0;top:560px;display:flex;flex-direction:column;align-items:center;gap:18px"><div style="transform:scale(${1 - 0.1 * press});border-radius:44px;box-shadow:0 18px 40px rgba(0,0,0,.4)">${MARK(190, 'h')}</div><div style="font:600 32px Plex;color:#fff">Sinder</div></div></div>`; }
function ring(r, w, frac, col) { const C = 2 * Math.PI * r; return `<svg width="${2 * (r + w)}" height="${2 * (r + w)}" style="flex:none"><circle cx="${r + w}" cy="${r + w}" r="${r}" fill="none" stroke="#2A3656" stroke-width="${w}"/><circle cx="${r + w}" cy="${r + w}" r="${r}" fill="none" stroke="${col}" stroke-width="${w}" stroke-linecap="round" stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - frac)}" transform="rotate(-90 ${r + w} ${r + w})"/></svg>`; }
function tenderCard(k, score) {
  return `<div style="background:${C.card};border-radius:40px;padding:44px 46px;color:#fff;box-shadow:0 40px 90px rgba(11,19,36,.28)">
    <div style="display:flex;gap:34px;align-items:center"><div style="position:relative">${ring(64, 12, 0.736 * score, '#F0CF7A')}<div class="abs" style="inset:0;display:flex;align-items:center;justify-content:center;font:700 50px Barlow;color:#F0CF7A">${(73.6 * score).toFixed(1)}</div></div>
    <div style="flex:1"><div style="display:flex;align-items:center;gap:14px">${flag('fr', 52)}<span style="font:600 30px Plex;color:#AFC0DD">France · Resah, hospital buyer</span></div>
    <div style="font:700 46px/1.15 Plex;margin-top:14px">Laboratory, optical and precision equipment</div></div></div>
    <div style="display:flex;gap:16px;margin-top:34px"><div class="kv"><b>$182.9M</b><span>stated value</span></div><div class="kv"><b>26 days</b><span>to deadline</span></div><div class="kv" style="background:#123826;border-color:#1F6B47"><b style="color:#5BE29A">Pursue</b><span style="color:#8FD1AE">engine decision</span></div></div></div>`;
}
const SRC = ['TED (EU)', 'World Bank', 'PNCP Brazil', 'SECOP II Colombia', 'BOAMP France', 'Find a Tender UK', 'Prozorro Ukraine', 'MyProcurement Malaysia', 'AIIB', 'UNGM', 'DNCP Paraguay', 'MTender Moldova', 'simap.ch', 'mr.gov.il', 'Uganda Coffee (UCDA)', 'FNC Colombia', 'MPOB Malaysia', 'US EIA', 'ECX Ethiopia', 'AfDB', 'EBRD', 'IDB', 'Etimad Saudi Arabia', 'AusTender', 'CanadaBuys', 'DGCP Dominican Rep.', 'Tridge directory', 'Contracts Finder UK', 'oeffentlichevergabe.de', 'PLACSP Spain', 'IsDB', 'ADB', 'MPOB', 'DTN fertilizer', 'Kenya coffee auction', 'Energy-Charts', 'EU Oil Bulletin', 'AHDB dairy'];

// ---------- the frame ----------
function render(t) {
  const sc = Object.values(SC).find((s) => t >= s.t0 && t < s.t1) || SC.cta; const lt = t - sc.t0, D = sc.t1 - sc.t0;
  let ground = C.navy, html = '', mapO = null; phone(0, 0, 1, 0); $('root').style.setProperty('--accent', C.gold);
  const chip = (txt, y, col = '#0B1324', k = 1) => `<div class="abs" style="left:80px;top:${y}px;font:600 34px Plex;color:${col};opacity:${k};filter:blur(${(1 - k) * 6}px)">${txt}</div>`;

  if (sc.id === 'hook') {
    const zo = pin(p(lt, D - 0.65, D)); const z = lerp(2.75, 3.0, io(p(lt, 0, D - 0.7))) * Math.pow(26, zo);
    const c0 = wt('r1', /^Thirty/) - sc.t0, c1 = wt('r1', /^tenders/) - sc.t0 + 0.35, lv = wt('r1', /^live/) - sc.t0;
    mapO = { cx: lerp(1085, 1123, zo), my0: lerp(470, 407, zo), cy: lerp(1230, 1000, zo), z, alpha: 1, reveal: lerp(0.35, 1.2, ex(p(lt, 0, c1 + 0.5))), live: p(lt, lv, lv + 0.5), focus: [1123, 407, lerp(0, 1, p(lt, D - 0.65, D - 0.5)) * 4 * Math.pow(26, zo)] };
    const n = lerp(28950, 34644, ex(p(lt, c0 - 0.1, c1))); const out = 1 - p(lt, D - 0.6, D - 0.35); const lk = p(lt, lv - 0.1, lv + 0.15);
    html += `<div class="abs" style="left:80px;top:190px;opacity:${out}"><div class="num" style="font:700 300px/0.9 Barlow;letter-spacing:-6px;color:${C.gold}">${fmt(n)}</div>
      <div style="font:600 46px Plex;color:#fff;margin-top:22px">active tenders</div>
      <div style="display:flex;align-items:center;gap:16px;margin-top:14px;font:600 40px Plex;color:#8FA2C7"><i style="width:22px;height:22px;border-radius:50%;background:${lk > 0 ? C.green : '#3A4A6E'};display:inline-block"></i><span style="color:${lk > 0 ? '#6FE3A1' : '#8FA2C7'}">live</span><span>·</span><span>open right now</span></div></div>`;
    if (zo > 0) ground = C.navy;
    if (lt > D - 0.12) ground = C.ground_gold;
  } else if (sc.id === 'problem') {
    ground = C.ground_gold; let n = 0; for (let i = 0; i < NOTI.length; i++) if (t >= notiT(i)) n++;
    const last = n ? notiT(n - 1) : -9; const sh = Math.exp(-(t - last) * 16) * (n ? 1 : 0);
    const enter = ex(p(lt, 0, 0.6)); const sw = pin(p(lt, D - 1.15, D - 0.75)); const press = p(lt, D - 0.45, D - 0.3) - p(lt, D - 0.3, D - 0.2); const zoomIcon = pin(p(lt, D - 0.25, D));
    phone(540 + Math.sin(t * 95) * 10 * sh, lerp(1700, 1080, enter) + zoomIcon * 0, lerp(0.86, 0.86, 0) * (1 + zoomIcon * 6), 1);
    scr(sw < 1 ? lockScreen(t, n, sw) : homeScreen(t, press, 1));
    const unread = n >= NOTI.length ? '99+' : String(n * 11 + (n ? 3 : 0));
    const uk = p(lt, 0.25, 0.5); const out = 1 - p(lt, D - 1.1, D - 0.8);
    html += `<div class="abs" style="left:80px;top:150px;opacity:${uk * out};color:${C.ink}"><span class="num" style="font:700 170px/1 Barlow;letter-spacing:-3px;display:inline-block;transform:scale(${1 + 0.06 * sh});transform-origin:left bottom">${unread}</span><span style="font:700 76px Barlow;margin-left:18px">unread</span></div>`;
    if (zoomIcon > 0) { ground = C.ground_gold; html += `<div class="abs" style="inset:0;background:${C.navy};opacity:${p(zoomIcon, 0.55, 1)}"></div>`; }
  } else if (sc.id === 'brand') {
    ground = C.navy; const s1 = wt('r3', /^Sinder/) - sc.t0; const draw = io(p(lt, 0.05, 0.9)); const wm = ex(p(lt, s1 - 0.05, s1 + 0.45));
    const carry = io(p(lt, D - 0.6, D)); const mx = lerp(540, 125, carry), my = lerp(720, 368, carry), ms = lerp(1, 0.13, carry);
    html += `<div class="abs" style="left:${mx}px;top:${my}px;transform:translate(-50%,-50%) scale(${ms});opacity:${1 - p(carry, 0.85, 1)}">${MARK(360, 'b', draw)}</div>
      <div class="abs" style="left:0;right:0;top:960px;text-align:center;font:700 230px/1 Barlow;letter-spacing:4px;color:#fff;clip-path:inset(0 ${100 - wm * 100}% 0 0);opacity:${1 - carry}">SINDER</div>
      <div class="abs" style="left:0;right:0;top:1220px;text-align:center;font:600 44px Plex;color:#9FB1D3;opacity:${p(lt, wt('r3', /^runs/) - sc.t0, wt('r3', /^runs/) - sc.t0 + 0.3) * (1 - carry)}">Deal Desk</div>`;
    if (carry > 0) { ground = mix(C.navy, C.light, io(p(carry, 0.2, 0.9))); phone(540, 1080, 0.86, p(carry, 0.4, 0.9)); ui(4); }
  } else if (sc.id === 'tend') {
    ground = C.light; const lift = 1.45; const k = ex(p(lt, lift, lift + 0.6));
    let f = lt < 1.1 ? Math.round(lerp(4, 39, io(p(lt, 0.05, 1.1)))) : 53;
    phone(540, lerp(1080, 1500, io(p(lt, lift + 0.1, lift + 0.8))), 0.86, 1 - 0.6 * p(lt, lift + 0.1, lift + 0.8)); ui(f, 0.35 * p(lt, lift, lift + 0.6));
    html += chip('09:12', 150, C.mute, p(lt, 0.1, 0.35));
    html += `<div class="abs" style="left:80px;top:200px;font:700 120px/1 Barlow;color:${C.ink}">${words('Ranked by fit', 0.15, lt, { gold: [] })}</div>`;
    if (lt >= lift) { const x0 = 540 - 300 * 0.86, y0 = 1080 - 731 * 0.86 + 690 * 0.86; const X = lerp(x0, 60, k), Y = lerp(y0, 420, k), Wd = lerp(600, 960, k);
      html += `<div class="abs" style="left:${X}px;top:${Y}px;width:960px;transform-origin:0 0;transform:scale(${Wd / 960})">${tenderCard(k, ex(p(lt, lift + 0.2, lift + 1.1)))}</div>`; }
  } else if (sc.id === 'sup') {
    ground = C.light; const up = ex(p(lt, 0, 0.5));
    html += chip('09:40', 150, C.mute, 1 - p(lt, 0, 0.2)) + chip('09:40', 150, C.mute, p(lt, 0.15, 0.4));
    html += `<div class="abs" style="left:60px;top:${lerp(420, 140, up)}px;width:960px;transform-origin:0 0;transform:scale(${lerp(1, 0.78, up)})">${tenderCard(1, 1)}</div>`;
    const SUP = [['de', 'Optix Medical GmbH', 'Sold ophthalmic equipment to 6 public hospitals', 'award records', 1], ['fr', 'Clarion Ophthalmique SAS', 'Supplied this buyer before', 'award records', 1], ['se', 'Nordlys Instruments AB', 'Lists the product, not yet proven', 'trade directory', 0]];
    let rows = ''; [/^Finds/, /^really/, /^makes/].forEach((r, i) => { const t0 = wt('r5', r) - sc.t0; const q = ex(p(lt, t0 - 0.05, t0 + 0.4)); const ok = p(lt, t0 + 0.35, t0 + 0.6); const [cc, nm, ev, src, v] = SUP[i];
      rows += `<div style="display:flex;gap:24px;align-items:center;padding:30px 34px;border-top:2px solid #E1E6EF;opacity:${q};filter:blur(${(1 - q) * 6}px)">${flag(cc, 60)}<div style="flex:1"><div style="font:700 38px Plex;color:${C.ink}">${nm}</div><div style="font:500 30px/1.3 Plex;color:#3C475C;margin-top:6px">${ev}</div><div style="font:600 28px Plex;color:${C.mute};margin-top:4px">evidence: ${src}</div></div>
        <div style="width:66px;height:66px;border-radius:50%;background:${v ? C.green : '#D9A21B'};display:flex;align-items:center;justify-content:center;transform:scale(${bk(ok)});opacity:${ok}"><svg width="38" height="38" viewBox="0 0 24 24"><path d="${v ? 'M4 12.5l5 5L20 6.5' : 'M12 5v9M12 18.5v.6'}" fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/></svg></div></div>`; });
    const pk = ex(p(lt, 0.25, 0.75));
    html += `<div class="abs" style="left:60px;top:${lerp(1400, 720, pk)}px;width:960px;background:#fff;border-radius:40px;box-shadow:0 30px 80px rgba(11,19,36,.12);opacity:${pk}"><div style="padding:34px 34px 20px;font:700 64px Barlow;color:${C.ink}">Matching suppliers</div>${rows}<div style="padding:18px 34px 28px;font:500 28px Plex;color:${C.mute}">Supplier names are illustrative</div></div>`;
  } else if (sc.id === 'price') {
    const wh = ex(p(lt, 0, 0.35)); ground = C.navy; const p0 = wt('r6', /^Prices/) - sc.t0;
    mapO = { cx: 1112, my0: 552, cy: 520, z: lerp(3.4, 3.8, io(p(lt, 0, D))), alpha: 1, reveal: 99, focus: [1112, 552, 14 + 4 * ex(p(lt, 0.2, 0.6))] };
    html += `<div class="abs" style="left:0;right:0;top:0;height:1920px;background:${C.light};transform:translateX(${-1100 * wh}px)"></div>`;
    html += chip('11:40', 150, '#8FA2C7', p(lt, 0.2, 0.45));
    html += `<div class="abs" style="left:80px;top:200px;display:flex;align-items:center;gap:22px;opacity:${p(lt, 0.25, 0.5)}">${flag('ug', 76)}<span style="font:700 78px Barlow;color:#fff">Kampala, Uganda</span></div>`;
    const G = [['Bugisu AA', 2.7215], ['Bugisu A', 2.7115], ['Wugar', 2.7015], ['Drugar', 2.5115], ['Robusta Screen 18', 1.8563], ['Robusta Screen 15', 1.5835]];
    let rows = ''; G.forEach(([g, v], i) => { const q = ex(p(lt, p0 + 0.3 + i * 0.07, p0 + 0.75 + i * 0.07)); rows += `<div style="display:flex;align-items:center;gap:20px;margin-top:22px;opacity:${q}"><div style="width:300px;font:600 32px Plex;color:#D5DDEB">${g}</div><div style="flex:1;height:18px;border-radius:9px;background:#1E2B48"><div style="width:${q * (v / 2.8) * 100}%;height:100%;border-radius:9px;background:${i === 0 ? C.gold : '#4A5E8C'}"></div></div><div class="num" style="width:120px;text-align:right;font:700 36px Plex;color:#fff">$${v.toFixed(2)}</div></div>`; });
    const ck = ex(p(lt, p0 - 0.1, p0 + 0.45));
    html += `<div class="abs" style="left:60px;width:960px;top:${lerp(1500, 860, ck)}px;background:${C.card};border-radius:40px;padding:44px 46px;border:2px solid #22305A;opacity:${ck}">
      <div style="font:600 34px Plex;color:#AFC0DD">Arabica coffee, at origin</div>
      <div style="display:flex;align-items:baseline;gap:18px;margin-top:6px"><span class="num" style="font:700 230px/1 Barlow;color:${C.gold};letter-spacing:-4px">$${(2.72 * ex(p(lt, p0, p0 + 0.9))).toFixed(2)}</span><span style="font:700 60px Barlow;color:#fff">per lb</span></div>
      <div style="font:600 32px Plex;color:#D5DDEB">Bugisu AA · free on truck, Kampala</div>${rows}
      <div style="font:500 28px Plex;color:#8FA2C7;margin-top:28px">Uganda Coffee Development Authority, 6 Nov 2026</div></div>`;
  } else if (sc.id === 'bid') {
    ground = C.light; $('root').style.setProperty('--accent', C.deep); const b0 = wt('r7', /^models/) - sc.t0, d0 = wt('r7', /^dollar/) - sc.t0; const wh = ex(p(lt, 0, 0.35));
    const sl = io(p(lt, b0 - 0.2, d0 - 0.2)); const win = lerp(0.04, 0.154, sl), ev = lerp(0.12, 1.744, sl);
    html += `<div class="abs" style="left:0;right:0;top:0;bottom:0;background:${C.navy};transform:translateX(${-1100 * wh}px)"></div>`;
    html += chip('12:15', 150, C.mute, p(lt, 0.2, 0.45));
    html += `<div class="abs" style="left:80px;top:200px;display:flex;align-items:center;gap:20px;opacity:${p(lt, 0.25, 0.5)}">${flag('fr', 70)}<span style="font:700 78px Barlow;color:${C.ink}">Back to the French tender</span></div>`;
    const R = 330, Cc = Math.PI * R, k = ex(p(lt, 0.2, 0.7));
    html += `<div class="abs" style="left:60px;width:960px;top:${lerp(1400, 380, k)}px;height:1200px;background:#fff;border-radius:40px;box-shadow:0 30px 80px rgba(11,19,36,.12);opacity:${k}">
      <svg class="abs" style="left:${480 - R - 26}px;top:70px" width="${2 * R + 52}" height="${R + 52}"><path d="M26 ${R + 26} A${R} ${R} 0 0 1 ${2 * R + 26} ${R + 26}" fill="none" stroke="#E4E9F2" stroke-width="40" stroke-linecap="round"/><path d="M26 ${R + 26} A${R} ${R} 0 0 1 ${2 * R + 26} ${R + 26}" fill="none" stroke="${C.deep}" stroke-width="40" stroke-linecap="round" stroke-dasharray="${Cc}" stroke-dashoffset="${Cc * (1 - win / 0.3)}"/></svg>
      <div class="abs" style="left:0;right:0;top:250px;text-align:center"><div class="num" style="font:700 170px/1 Barlow;color:${C.ink}">${Math.round(win * 100)}%</div><div style="font:600 34px Plex;color:${C.mute}">win chance · 2 expected bidders</div></div>
      <div class="abs" style="left:60px;right:60px;top:560px"><div style="font:600 34px Plex;color:${C.mute}">Your bid</div><div style="position:relative;height:22px;border-radius:11px;background:#E4E9F2;margin-top:26px"><div style="width:${lerp(8, 70, sl)}%;height:100%;border-radius:11px;background:${C.ink}"></div><div style="position:absolute;left:${lerp(8, 70, sl)}%;top:50%;width:64px;height:64px;border-radius:50%;background:#fff;border:6px solid ${C.ink};transform:translate(-50%,-50%)"></div></div></div>
      <div class="abs" style="left:60px;top:720px"><div style="font:600 34px Plex;color:${C.mute}">Expected value</div><div class="num" style="font:700 200px/1 Barlow;color:${C.deep};letter-spacing:-3px;margin-top:6px">$${ev.toFixed(2)}M</div></div>
      <div class="abs" style="left:60px;right:60px;top:1010px;padding-top:30px;border-top:2px solid #E1E6EF;display:flex;align-items:center;justify-content:space-between"><span style="font:600 32px Plex;color:${C.mute}">Engine decision</span>
        <span style="font:700 70px Barlow;letter-spacing:3px;color:#fff;background:${C.green};padding:6px 34px;border-radius:16px;display:inline-block;opacity:${p(lt, d0, d0 + 0.12)};transform:scale(${lerp(1.5, 1, ex(p(lt, d0, d0 + 0.35)))})">PURSUE</span></div></div>`;
  } else if (sc.id === 'engine') {
    ground = C.navy; const fl = io(p(lt, 0, 0.45)); const STATS = [[/^agents/, 'Dozens', 'of AI agents at work'], [/^sources/, '200+', 'official data sources'], [/^countries/, '195', 'countries covered'], [/^clock/, '24/7', 'live, always collecting']];
    let board = ''; for (let r = 0; r < 18; r++) { const dir = r % 2 ? 1 : -1; const off = ((lt * 70 * dir + r * 173) % 1400 + 1400) % 1400; let row = ''; for (let j = 0; j < 7; j++) { const nm = SRC[(r * 5 + j * 3) % SRC.length]; const lit = (Math.floor(lt * 2.2 + r * 0.7 + j) % 9) === 0; row += `<span style="margin-right:46px;color:${lit ? C.gold : '#33456F'}">${nm}</span>`; }
      board += `<div style="white-space:nowrap;font:600 40px Plex;height:96px;line-height:96px;transform:translateX(${-off}px)">${row}${row}</div>`; }
    html += `<div class="abs" style="left:0;top:${lerp(1920, 0, fl)}px;width:1080px;height:1920px;overflow:hidden;background:${C.navy}">${board}</div>`;
    let si = -1; STATS.forEach(([r], i) => { if (lt >= wt('r8', r) - sc.t0 - 0.05) si = i; });
    if (si >= 0) { const [r, n, l] = STATS[si]; const t0 = wt('r8', r) - sc.t0 - 0.05; const k = ex(p(lt, t0, t0 + 0.3)); const nxt = STATS[si + 1] ? wt('r8', STATS[si + 1][0]) - sc.t0 - 0.05 : D; const o = 1 - p(lt, nxt - 0.15, nxt);
      html += `<div class="abs" style="left:0;right:0;top:560px;height:800px;background:${C.navy};opacity:${0.92 * fl}"></div><div class="abs" style="left:80px;right:80px;top:640px;opacity:${o}"><div class="num" style="font:700 360px/0.9 Barlow;letter-spacing:-6px;color:${C.gold};filter:blur(${(1 - k) * 10}px);opacity:${k}">${n}</div><div style="font:600 58px Plex;color:#fff;margin-top:20px;opacity:${p(lt, t0 + 0.1, t0 + 0.3)}">${l}</div></div>`; }
  } else if (sc.id === 'meet') {
    const fl = io(p(lt, 0, 0.5)); ground = mix(C.navy, C.tg, fl);
    const q1 = wt('r9', /^Ask/) + 0.15, a1 = wt('r9', /^Supplier/) + 0.15, a2 = wt('r9', /^contact/) + 0.15, a3 = wt('r9', /^price/) + 0.15, ap = sc.t1 - 1.0;
    phone(540, lerp(1900, 1130, ex(p(lt, 0.15, 0.75))), 0.84, 1);
    const chat = [[q1, 'me', "Arabica exporters in Uganda, and today's price?"], [a1, 'bot', '<b>Elgon Highland Coffee</b>, Mbale<br><span style="color:#7E8CA6">listed exporter · check before use</span>'], [a2, 'bot', 'Export manager<br><span style="color:#7E8CA6">email on file</span>'], [a3, 'bot', `Bugisu AA <b style="color:#B07A0E">$2.72/lb</b> FOT Kampala<br><span style="color:#7E8CA6;font-size:26px">UCDA, 6 Nov</span>`], [a3 + 1.0, 'draft', 'Send an intro to the exporter?']];
    let h = ''; for (const [tc, w, x] of chat) { const k = ex(p(t, tc, tc + 0.35)); if (k <= 0) continue; const st = `opacity:${k};transform:translateY(${(1 - k) * 30}px)`;
      if (w === 'me') h += `<div style="${st};align-self:flex-end;max-width:84%;background:#EEFFDE;color:#0B1324;padding:20px 24px;border-radius:30px 30px 8px 30px;font:500 32px/1.3 Plex">${x}<span style="font-size:22px;color:#5FA84A;margin-left:10px">14:21 ✓✓</span></div>`;
      else if (w === 'bot') h += `<div style="${st};align-self:flex-start;max-width:88%;background:#fff;color:#0B1324;padding:20px 24px;border-radius:30px 30px 30px 8px;font:500 32px/1.3 Plex">${x}<span style="font-size:22px;color:#9AA6BA;margin-left:10px">14:21</span></div>`;
      else { const a = t >= ap; h += `<div style="${st};align-self:flex-start;width:90%"><div style="background:#fff;color:#0B1324;padding:20px 24px;border-radius:30px 30px 30px 8px;font:500 32px Plex">${x}</div><div style="display:flex;gap:12px;margin-top:12px"><div style="flex:1;text-align:center;padding:22px;border-radius:20px;background:${a ? C.green : 'rgba(255,255,255,.92)'};color:${a ? '#fff' : '#2481CC'};font:700 32px Plex;transform:scale(${t > ap - 0.12 && t < ap + 0.1 ? 0.95 : 1})">${a ? 'Approved ✓' : 'Approve'}</div><div style="flex:1;text-align:center;padding:22px;border-radius:20px;background:rgba(255,255,255,.92);color:#2481CC;font:700 32px Plex">Reject</div></div></div>`; } }
    for (const [tc, w] of chat) { if (w === 'me') continue; if (t > tc - 0.7 && t < tc) { h += `<div style="align-self:flex-start;background:#fff;padding:22px 26px;border-radius:30px;display:flex;gap:10px">${[0, 1, 2].map((j) => `<i style="width:14px;height:14px;border-radius:50%;background:#9AA6BA;opacity:${0.35 + 0.65 * Math.abs(Math.sin(t * 7 + j))}"></i>`).join('')}</div>`; break; } }
    scr(`<div class="abs" style="inset:0;background:#C9DCEB"><div style="height:190px;padding-top:80px;background:#fff;display:flex;align-items:center;gap:20px;padding-left:30px;border-bottom:1px solid #DDE3EC"><div style="border-radius:50%;overflow:hidden;width:76px;height:76px">${MARK(76, 't')}</div><div><div style="font:700 34px Plex;color:#0B1324">Sinder Deal Agent</div><div style="font:500 26px Plex;color:#2481CC">bot</div></div></div><div class="abs" style="left:0;right:0;top:190px;bottom:0;padding:26px;display:flex;flex-direction:column;justify-content:flex-end;gap:14px">${h}</div></div>`);
    const ik = ex(p(lt, 0.3, 0.8));
    html += chip('14:21 · in a meeting with a buyer', 150, '#E6F4FD', p(lt, 0.25, 0.5));
    html += `<div class="abs" style="left:80px;top:200px;display:flex;align-items:center;gap:26px;opacity:${ik}"><div style="width:110px;height:110px;border-radius:50%;background:#fff;display:flex;align-items:center;justify-content:center;transform:scale(${lerp(0.6, 1, bk(ik))})">${icon('telegram', 110, C.tg)}</div><span style="font:700 110px/1 Barlow;color:#fff">${lt > ap - sc.t0 - 1.6 ? 'You approve. It sends.' : 'Ask mid-meeting'}</span></div>`;
  } else if (sc.id === 'cta') {
    ground = mix(C.tg, C.navy, io(p(lt, 0, 0.45))); const lt0 = wt('r10', /^Let/) - sc.t0; const draw = io(p(lt, 0.2, 1.0)); const wm = ex(p(lt, 0.7, 1.2));
    const k2 = ex(p(lt, lt0 - 0.05, lt0 + 0.35)), k3 = ex(p(lt, lt0 + 0.45, lt0 + 0.9)), k4 = p(lt, lt0 + 0.9, lt0 + 1.3);
    html += `<div class="abs" style="left:0;right:0;top:220px;display:flex;align-items:center;justify-content:center;gap:34px"><div style="transform:scale(${lerp(0.7, 1, ex(p(lt, 0.1, 0.6)))});opacity:${p(lt, 0.1, 0.3)}">${MARK(190, 'c', draw)}</div><div style="font:700 190px/1 Barlow;letter-spacing:3px;color:#fff;clip-path:inset(0 ${100 - wm * 100}% 0 0)">SINDER</div></div>
      <div class="abs" style="left:80px;right:80px;top:540px;font:700 110px/1.02 Barlow;color:#fff">${words('Build it with us.', 0.9, lt, { gold: [3] })}</div>
      <div class="abs" style="left:0;right:0;top:880px;text-align:center;font:700 240px/1 Barlow;color:${C.gold};opacity:${k2};filter:blur(${(1 - k2) * 10}px)">Let's talk.</div>
      <div class="abs" style="left:0;right:0;top:1240px;display:flex;justify-content:center;opacity:${k3}"><div style="font:600 64px Plex;color:${C.navy};background:${C.gold};padding:30px 60px;border-radius:24px;transform:scale(${lerp(0.9, 1, k3)})">Etamar@sinder.pro</div></div>
      <div class="abs" style="left:0;right:0;top:1420px;text-align:center;font:600 40px Plex;color:#9FB1D3;opacity:${k4}">sinder.pro</div>
      <div class="abs" style="left:0;right:0;top:1810px;text-align:center;font:500 28px Plex;color:#5E6E90;opacity:${k4}">Music: The Corporate Upbeat, Soundrider/Dope, CC BY 3.0</div>`;
    $('black').style.opacity = p(lt, D - 0.5, D);
  }
  if (sc.id !== 'cta') $('black').style.opacity = 0;
  $('ground').style.background = ground; drawMap(t, mapO); $('fx').innerHTML = html; $('subs').innerHTML = sc.id === 'cta' && t >= wt('r10', /^Let/) - 0.1 ? '' : subtitle(t);
}
const tl = gsap.timeline({ paused: true });
const clock = { t: 0 };
tl.to(clock, { t: TL.total, duration: TL.total, ease: 'none', onUpdate: () => render(tl.time()) }, 0);
render(0);
window.__timelines = window.__timelines || {};
window.__timelines['main'] = tl;
window.__render = render;
