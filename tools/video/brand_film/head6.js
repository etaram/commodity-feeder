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
const W = Object.fromEntries(Object.entries(TL.lines).map(([k, l]) => [k, l.words]));
const wt = (k, re) => { const w = W[k].find((x) => re.test(x[0])); return w ? w[1] : TL.lines[k].t; };
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
const notiT = (i) => { const s = SC.flood; const a = s.t0 + 0.05, b = wt('v4', /^whoever/); const u = i / (NOTI.length - 1); return a + (b - a) * (1 - Math.pow(1 - u, 1.5)); };
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
