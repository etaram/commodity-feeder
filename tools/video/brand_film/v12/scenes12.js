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
function benefit(h, t0, lt0, col = C.ink) { return `<div class="abs" style="left:80px;right:80px;top:170px;font:700 140px/0.95 Barlow;color:${col};text-shadow:${col === '#fff' ? '0 4px 30px rgba(0,0,0,.5)' : 'none'}">${words(h, t0, lt0, { gap: 0.09 })}</div>`; }
// a pain question that gets struck through when the fix lands, then the fix headline
function painFix(q, fix, tq, tf, lt0) {
  const qk = ex(p(lt0, tq, tq + 0.25)), st = io(p(lt0, tf - 0.05, tf + 0.25)), fk = ex(p(lt0, tf, tf + 0.3));
  return `<div class="abs" style="left:80px;right:80px;top:150px"><div style="position:relative;display:inline-block;font:700 92px/1 Barlow;color:${mix('#0B1324', '#9AA6BA', st)};opacity:${qk};filter:blur(${(1 - qk) * 6}px)">${q}<i class="abs" style="left:0;top:52%;height:9px;width:${st * 100}%;background:${RED};border-radius:5px"></i></div>
    <div style="font:700 128px/1 Barlow;color:${C.ink};margin-top:14px;opacity:${fk};filter:blur(${(1 - fk) * 8}px)">${fix}</div></div>`;
}

// ---------- photo and footage layer: [file, focus x 0..1, zoom from, zoom to, tint colour, tint top, tint bottom]
const MEDIA = {
  hook: ['v:port_night', 0.5, 1.15, 1.05, '#2A0508', 0.55, 0.8],
  noise: ['iss_a', 0.55, 1.0, 1.14, '#0B1324', 0.55, 0.25],
  reveal: ['black_marble', 0.35, 1.18, 1.0, '#0B1324', 0.62, 0.62],
  army: ['iss_c', 0.45, 1.0, 1.1, '#0B1324', 0.72, 0.72],
  rank: ['port_cranes', 0.3, 1.05, 1.15, '#0B1324', 0.62, 0.45],
  sup: ['port_reykjavik', 0.7, 1.12, 1.0, '#0B1324', 0.6, 0.4],
  contacts: ['port_miami', 0.35, 1.0, 1.12, '#0B1324', 0.6, 0.4],
  build: ['ship_cmacgm', 0.62, 1.0, 1.1, '#0B1324', 0.62, 0.35],
  cta: ['iss_d', 0.5, 1.12, 1.0, '#0B1324', 0.72, 0.72],
};
const ring_ = (r, w, f, col) => `<svg width="${2 * r}" height="${2 * r}" style="position:absolute;left:0;top:0;transform:rotate(-90deg)"><circle cx="${r}" cy="${r}" r="${r - w / 2}" fill="none" stroke="#E4E9F2" stroke-width="${w}"/><circle cx="${r}" cy="${r}" r="${r - w / 2}" fill="none" stroke="${col}" stroke-width="${w}" stroke-linecap="round" stroke-dasharray="${2 * Math.PI * (r - w / 2)}" stroke-dashoffset="${2 * Math.PI * (r - w / 2) * (1 - cl(f))}"/></svg>`;
function setMedia(id, lt, D) {
  const m = MEDIA[id]; document.querySelectorAll('.bgm').forEach((el) => { el.style.opacity = 0; });
  const tint = $('tint'); if (!m) { tint.style.opacity = 0; return false; }
  const [f, fx, z0, z1, col, a0, a1] = m; const el = $('m_' + f.replace('v:', '')); if (!el) return false;
  const k = io(cl(lt / D)); const z = lerp(z0, z1, k); const W = el.dataset.w * 1920 / el.dataset.h;
  const x = -(W - 1080) * fx; el.style.width = W + 'px'; el.style.opacity = 1;
  el.style.transform = `translate(${x}px,0) scale(${z})`; el.style.transformOrigin = `${-x + 540}px 960px`;
  tint.style.opacity = 1; tint.style.background = `linear-gradient(180deg, ${col}${Math.round(a0 * 255).toString(16).padStart(2, '0')} 0%, ${col}${Math.round(((a0 + a1) / 2) * 255).toString(16).padStart(2, '0')} 50%, ${col}${Math.round(a1 * 255).toString(16).padStart(2, '0')} 100%)`;
  return true;
}
function render(t) {
  const sc = Object.values(SC).find((s) => t >= s.t0 && t < s.t1) || SC.cta; const lt = t - sc.t0, D = sc.t1 - sc.t0;
  let ground = C.navy, html = '', mapO = null; phone(0, 0, 1, 0); $('root').style.setProperty('--accent', C.gold); $('black').style.opacity = 0;
  const L = (k) => TL.lines[k].t - sc.t0;

  if (sc.id === 'hook') {
    ground = '#14080A'; const lo = wt('v1', /^lost/), nv0 = wt('v1', /^never/), sw = wt('v1', /^saw/);
    const nv = ex(p(t, nv0 - 0.05, nv0 + 0.3)); const ck = ex(p(t, 0, 0.35));
    html += `<div class="abs" style="left:80px;right:80px;top:170px;font:700 150px/0.95 Barlow;color:#fff">You never<br><span style="color:#FF5A4E;opacity:${0.3 + 0.7 * nv}">saw it.</span></div>
      <div class="abs" style="left:60px;width:960px;top:${lerp(700, 620, ck)}px;opacity:${ck}">${lostCard(0)}</div>`;
    // the same deal gets buried under other live notices, one after another
    let pile = ''; for (let i = 0; i < 14; i++) { const t0 = lo - 0.1 + i * 0.075; const k = ex(p(t, t0, t0 + 0.32)); if (k <= 0) continue;
      const x = 60 + ((i * 53) % 70) - 35, y = 600 + ((i * 41) % 90) - 30, r = ((i * 37) % 13) - 6;
      let ln = ''; for (let l = 0; l < 6; l++) ln += `<div style="height:16px;margin-top:20px;width:${[88, 64, 92, 70, 80, 56][(l + i) % 6]}%;border-radius:4px;background:#C3CAD6"></div>`;
      pile += `<div class="abs" style="left:${x}px;top:${lerp(1950, y, k)}px;width:960px;height:430px;background:${i % 2 ? '#E4E8EF' : '#D7DDE6'};border-radius:40px;padding:40px 46px;transform:rotate(${r * k}deg);box-shadow:0 -20px 60px rgba(0,0,0,.35)"><div style="height:30px;width:40%;border-radius:6px;background:#AEB7C6"></div>${ln}</div>`; }
    html += pile;
    const bk = ex(p(t, sw - 0.15, sw + 0.25));
    html += `<div class="abs" style="left:80px;right:80px;top:1150px;opacity:${bk};transform:translateY(${(1 - bk) * 30}px)"><span style="display:inline-block;font:700 60px/1.1 Barlow;color:#fff;background:#C62D23;padding:14px 28px;border-radius:16px;white-space:nowrap">Buried among 34,644 live tenders</span></div>`;
  } else if (sc.id === 'noise') {
    const c1 = wt('v2', /^thousand/) + 0.25, lv = wt('v2', /^live/), nf = wt('v2', /^ninety/); const n = lerp(0, 34644, ex(p(t, sc.t0, c1)));
    const zo = pin(p(lt, D - 0.01, D)); mapO = { cx: 1085, my0: 470, cy: 1300, z: lerp(2.9, 3.1, io(p(lt, 0, D))), alpha: 1, reveal: lerp(0.3, 1.25, ex(p(t, sc.t0, nf + 0.4))), live: p(t, lv, lv + 0.45) };
    const lk = ex(p(t, lv - 0.05, lv + 0.25)), k195 = ex(p(t, nf - 0.1, nf + 0.25));
    html += `<div class="abs" style="left:80px;top:170px"><div class="num" style="font:700 300px/0.9 Barlow;letter-spacing:-6px;color:${C.gold}">${fmt(n)}</div>
      <div style="display:flex;align-items:center;gap:22px;margin-top:20px"><span style="font:600 50px Plex;color:#fff">tenders</span><span style="display:inline-flex;align-items:center;gap:12px;background:${C.green};color:#fff;font:700 40px Plex;letter-spacing:2px;padding:8px 22px;border-radius:14px;opacity:${lk};transform:scale(${lerp(1.6, 1, lk)})"><i style="width:16px;height:16px;border-radius:50%;background:#fff"></i>LIVE</span></div>
      <div style="margin-top:30px;opacity:${k195};filter:blur(${(1 - k195) * 6}px)"><span class="num" style="font:700 130px/1 Barlow;color:#fff">195</span><span style="font:600 44px Plex;color:#9FB1D3;margin-left:18px">countries</span></div></div>`;
    { const cn = wt('v2', /^countries/); const nM = Math.round(lerp(0, 14, p(t, lv - 0.05, lv + 0.4)) + lerp(0, 60, p(t, nf - 0.1, cn + 0.4))); let mk = '';
      for (let i = 0; i < nM; i++) { const x = 70 + ((i * 263 + 41) % 940), y = 900 + ((i * 157 + 23) % 740); const b = (t * 1.6 + i * 0.37) % 1;
        mk += `<div class="abs" style="left:${x}px;top:${y}px;width:0;height:0"><i class="abs" style="left:-9px;top:-9px;width:18px;height:18px;border-radius:50%;background:${i < 14 ? C.green : C.gold};box-shadow:0 0 0 4px rgba(0,0,0,.25)"></i><i class="abs" style="left:${-9 - 30 * b}px;top:${-9 - 30 * b}px;width:${18 + 60 * b}px;height:${18 + 60 * b}px;border-radius:50%;border:3px solid ${i < 14 ? C.green : C.gold};opacity:${1 - b}"></i></div>`; }
      html += mk; }
  } else if (sc.id === 'chaos') {
    ground = C.navy; const W3 = [[/^portals/, 'Different portals'], [/^languages/, 'Different languages'], [/^Endless/, 'Endless PDFs']];
    let ci = 0; W3.forEach(([r], i) => { if (t >= wt('v3', r) - 0.35) ci = i; });
    const PORTALS = ['TED', 'SAM.gov', 'PNCP', 'SECOP II', 'Prozorro', 'Etimad', 'AusTender', 'CanadaBuys', 'BOAMP', 'Find a Tender', 'UNGM', 'DGCP', 'MyProcurement', 'simap.ch', 'mr.gov.il', 'eTenders'];
    const LANG = ['Avis de marché', 'Aviso de licitação', 'Licitación pública', 'Оголошення про закупівлю', 'مناقصة عامة', 'Ausschreibung', 'Bando di gara', 'Przetarg', 'Ihale ilanı', 'Zabun', 'מכרז פומבי', '招标公告'];
    let field = ''; const items = ci === 0 ? PORTALS : ci === 1 ? LANG : null; const t0c = wt('v3', W3[ci][0]) - 0.35;
    if (items) items.forEach((s, i) => { const a = i * 2.399 + ci, r = 230 + ((i * 97) % 300); const k = ex(p(t, t0c + i * 0.03, t0c + i * 0.03 + 0.3)); const x = cl(540 + Math.cos(a) * r * 0.75, 300, 780), y = cl(1150 + Math.sin(a) * r * 1.35, 760, 1560);
      field += `<div class="abs" style="left:${x}px;top:${y}px;transform:translate(-50%,-50%) rotate(${((i * 37) % 14) - 7}deg) scale(${lerp(1.4, 1, k)});opacity:${k};font:700 ${ci ? 44 : 50}px Plex,DV;color:#fff;background:${i % 3 ? '#1B2847' : '#2A3B66'};padding:16px 26px;border-radius:16px;white-space:nowrap">${s}</div>`; });
    else for (let i = 0; i < 22; i++) { const k = ex(p(t, t0c + i * 0.035, t0c + i * 0.035 + 0.3)); const x = 140 + ((i * 263) % 800), y = 780 + ((i * 151) % 820);
      field += `<div class="abs" style="left:${x}px;top:${y}px;transform:translate(-50%,-50%) rotate(${((i * 29) % 30) - 15}deg) scale(${lerp(1.5, 1, k)});opacity:${k}">${appIcon('pdf', 150)}</div>`; }
    const k = ex(p(t, t0c, t0c + 0.25));
    html += `<div class="abs" style="inset:0">${field}</div><div class="abs" style="left:80px;right:80px;top:180px;font:700 150px/0.95 Barlow;color:#fff;opacity:${k};filter:blur(${(1 - k) * 8}px)">${W3[ci][1].replace(' ', '<br>')}</div>`;
  } else if (sc.id === 'flood') {
    ground = C.ground_gold; let n = 0; for (let i = 0; i < NOTI.length; i++) if (t >= notiT(i)) n++;
    const last = n ? notiT(n - 1) : -9; const sh = Math.exp(-(t - last) * 16) * (n ? 1 : 0); const enter = ex(p(lt, 0, 0.35));
    const sw = pin(p(t, T5 - 0.55, T5 - 0.3)); const zi = pin(p(t, T5 - 0.3, T5));
    phone(540 + Math.sin(t * 95) * 10 * sh, lerp(1750, 1120, enter), 0.86 * (1 + zi * 7), 1); scr(sw < 1 ? lockScreen(t, n, sw) : homeScreen(t, p(t, T5 - 0.32, T5 - 0.25), 1));
    const fk = ex(p(t, wt('v4', /^slip/) - 0.05, wt('v4', /^slip/) + 0.3));
    html += `<div class="abs" style="left:80px;top:150px;color:${C.ink};opacity:${1 - zi}"><span class="num" style="font:700 170px/1 Barlow;letter-spacing:-3px">${n >= NOTI.length ? '99+' : String(n * 11 + (n ? 3 : 0))}</span><span style="font:700 76px Barlow;margin-left:18px">unread</span></div>
      <div class="abs" style="left:80px;top:340px;font:700 64px Barlow;color:${C.ink};opacity:${fk * (1 - zi)}">What you don't see, you lose.</div>`;
    { const sl = wt('v4', /^slip/), us = wt('v4', /^unseen/); const FIT = [['fr', 'Ophthalmology equipment', '73.6', 700], ['gb', 'Hygiene services', '61.4', 980], ['dk', 'Pharmaceutical products', '46.9', 1260]]; let f = '';
      FIT.forEach(([cc, ti, sc_, y], i) => { const k = p(t, sl - 0.35 + i * 0.18, us + 0.1 + i * 0.12); if (k <= 0 || k >= 1) return; const x = lerp(-900, 1150, io(k)); const g = p(t, us - 0.1, us + 0.3);
        f += `<div class="abs" style="left:${x}px;top:${y}px;width:760px;display:flex;align-items:center;gap:20px;background:${mix('#FFFFFF', '#8E97A8', g)};border:4px solid ${mix(C.green, '#8E97A8', g)};border-radius:26px;padding:22px 28px;filter:blur(${Math.abs(Math.sin(Math.PI * io(k))) * 2}px);box-shadow:0 30px 60px rgba(0,0,0,.35)">${flag(cc, 60)}<div style="flex:1"><div style="font:600 26px Plex;color:#0B1324">live tender · fits you</div><div style="font:700 38px Plex;color:#0B1324">${ti}</div></div><span style="font:700 40px Plex;color:#fff;background:${mix(C.green, '#6B7891', g)};padding:6px 16px;border-radius:12px">${sc_}</span></div>`; });
      html += f; }
    html += `<div class="abs" style="inset:0;background:${C.navy};opacity:${p(zi, 0.6, 1)}"></div>`;
  } else if (sc.id === 'reveal') {
    ground = C.navy; const k = ex(p(t, T5, T5 + 0.5)); const s1 = wt('v5', /^Sinder/); const wm = ex(p(t, s1 - 0.05, s1 + 0.3));
    const bi = ex(p(t, wt('v5', /^Business/) - 0.08, wt('v5', /^Business/) + 0.25)), os = ex(p(t, wt('v5', /^OSINT/) - 0.08, wt('v5', /^OSINT/) + 0.25)), cp = ex(p(t, wt('v5', /^co-pilot/) - 0.08, wt('v5', /^co-pilot/) + 0.25));
    html += `<div class="abs" style="left:0;right:0;top:330px;display:flex;align-items:center;justify-content:center;gap:34px;transform:scale(${lerp(1.5, 1, k)});opacity:${cl(k * 3)}">${MARK(200, 'b', io(p(t, T5, T5 + 0.6)))}<div style="font:700 200px/1 Barlow;letter-spacing:5px;color:#fff;clip-path:inset(0 ${100 - wm * 100}% 0 0)">SINDER</div></div>
      <div class="abs" style="left:80px;right:80px;top:700px">
        <div style="font:700 120px/1 Barlow;color:#fff;opacity:${bi};filter:blur(${(1 - bi) * 8}px)">Business intelligence</div>
        <div style="display:flex;gap:18px;margin-top:30px;opacity:${os};transform:scale(${lerp(1.3, 1, os)});transform-origin:left center"><span style="font:700 70px Barlow;letter-spacing:3px;color:#0B1324;background:${C.gold};padding:10px 30px;border-radius:16px">OSINT</span><span style="font:700 70px Barlow;letter-spacing:3px;color:#fff;border:3px solid #3A4E7E;padding:7px 28px;border-radius:16px">AI AGENTS</span></div>
        <div style="font:700 130px/1 Barlow;color:${C.gold};margin-top:60px;opacity:${cp};filter:blur(${(1 - cp) * 8}px)">The deal co-pilot</div></div>`;
  } else if (sc.id === 'army') {
    ground = C.navy; const a0 = wt('v6', /^army/) - 0.1;
    let grid = ''; AGENTS.slice(0, 12).forEach(([role, src], i) => { const k = ex(p(t, a0 + i * 0.04, a0 + i * 0.04 + 0.35)); const verb = VERBS[(Math.floor(t * 1.8 + i * 0.7)) % VERBS.length];
      grid += `<div style="display:flex;align-items:center;gap:18px;height:84px;padding:0 26px;border-radius:18px;background:#121D38;border:2px solid #1F2E55;opacity:${k};transform:scale(${lerp(0.85, 1, k)})"><i style="width:16px;height:16px;border-radius:50%;background:${C.green};flex:none"></i><div style="flex:1;min-width:0;white-space:nowrap;overflow:hidden"><b style="font:700 30px Plex;color:#fff">${role}</b><span style="font:500 28px Plex;color:#8FA2C7"> · ${src}</span></div><span style="font:600 26px Plex;color:${C.gold}">${verb}</span></div>`; });
    const tk = ex(p(t, a0, a0 + 0.3)), ok = ex(p(t, wt('v6', /^agents/) - 0.1, wt('v6', /^agents/) + 0.25)), ck = ex(p(t, wt('v6', /^clock/) - 0.1, wt('v6', /^clock/) + 0.25));
    html += `<div class="abs" style="left:80px;top:160px"><div style="font:700 150px/0.95 Barlow;color:#fff;opacity:${tk};filter:blur(${(1 - tk) * 6}px)">An AI army</div><div style="display:flex;gap:16px;margin-top:22px"><span style="font:700 40px Plex;color:#0B1324;background:${C.gold};padding:8px 20px;border-radius:12px;opacity:${ok}">OSINT</span><span style="font:700 40px Plex;color:#fff;background:${C.green};padding:8px 20px;border-radius:12px;opacity:${ck}">24/7</span></div></div>
      <div class="abs" style="left:50px;right:50px;top:470px;display:flex;flex-direction:column;gap:14px">${grid}</div>`;
    { const wk = wt('v6', /^working/); const kk = bk(p(t, wk - 0.1, wk + 0.3)); const a = (t - wk) * 900; let tk = ''; for (let h = 0; h < 12; h++) tk += `<i class="abs" style="left:107px;top:14px;width:6px;height:22px;background:#9FB1D3;transform-origin:3px 96px;transform:rotate(${h * 30}deg)"></i>`;
      if (kk > 0) html += `<div class="abs" style="left:790px;top:150px;width:220px;height:220px;border-radius:50%;background:#fff;border:8px solid ${C.gold};transform:scale(${kk});box-shadow:0 20px 50px rgba(0,0,0,.4)">${tk.replace(/#9FB1D3/g, '#0B1324')}
        <i class="abs" style="left:101px;top:50px;width:10px;height:62px;border-radius:5px;background:#0B1324;transform-origin:5px 56px;transform:rotate(${a / 12}deg)"></i><i class="abs" style="left:103px;top:22px;width:6px;height:90px;border-radius:3px;background:${C.deep};transform-origin:3px 84px;transform:rotate(${a}deg)"></i><i class="abs" style="left:94px;top:94px;width:16px;height:16px;border-radius:50%;background:#0B1324"></i></div>`; }
  } else if (sc.id === 'rank') {
    // Every live tender -> read (scan + fields pulled out) -> translated (FR to EN) -> ranked by fit (climbs to #1)
    ground = C.navy; const W_ = (r) => wt('f1', r);
    const tE = W_(/^Every/), tR = W_(/^read/), tT = W_(/^translated/), tK = W_(/^ranked/), tF = W_(/^fit/);
    const pull = ex(p(t, tR - 0.55, tR - 0.1)); const fold = io(p(t, tK - 0.35, tK - 0.05));
    // 1. the feed: notices from everywhere stream past
    const FEED = [['fr', "Équipements d'ophtalmologie"], ['br', 'Aquisição de transformadores'], ['de', 'Lieferung von Laborgeräten'], ['gb', 'Hygiene services and equipment'], ['dk', 'Lægemidler, rammeaftale'], ['ke', 'Supply of solar water pumps'], ['nl', 'Levering medische apparatuur'], ['se', 'Medicinteknisk utrustning'], ['vn', 'Cung cấp thiết bị y tế'], ['il', 'מכרז לרכישת ציוד רפואי'], ['do', 'Transformadores de potencia'], ['ug', 'Supply of coffee seedlings']];
    const feedK = 1 - p(t, tR - 0.5, tR - 0.15);
    if (feedK > 0) { let f = ''; for (let i = 0; i < 36; i++) { const col = i % 3, row = Math.floor(i / 3); const [cc, ti] = FEED[(i * 5) % FEED.length];
        const y = 560 + row * 175 - (t - sc.t0) * 520 - col * 70; if (y < 380 || y > 1560) continue; const k = ex(p(t, tE - 0.1 + i * 0.02, tE + 0.2 + i * 0.02));
        f += `<div class="abs" style="left:${60 + col * 330}px;top:${y}px;width:300px;height:140px;background:rgba(255,255,255,.94);border-radius:22px;padding:18px 20px;opacity:${k * feedK};box-shadow:0 12px 30px rgba(0,0,0,.3)"><div style="display:flex;align-items:center;gap:10px">${flag(cc, 36)}<span style="font:600 20px Plex;color:#6B7891">live tender</span></div><div style="font:700 24px/1.2 Plex,DV;color:#0B1324;margin-top:8px;overflow:hidden;height:58px">${ti}</div></div>`; }
      html += f; }
    // header: the line, then three steps that light up as they are spoken
    const hk = 1 - p(t, tR - 0.45, tR - 0.2);
    if (hk > 0) html += `<div class="abs" style="left:80px;right:80px;top:150px;opacity:${hk}"><div style="font:700 140px/0.95 Barlow;color:#fff;text-shadow:0 4px 30px rgba(0,0,0,.6)">Every live tender</div><div style="display:inline-block;margin-top:24px;font:700 44px Plex;color:#0B1324;background:${C.gold};padding:8px 24px;border-radius:14px">34,644 right now</div></div>`;
    const STEPS = [['Read', tR - 0.1, tT - 0.05], ['Translate', tT - 0.05, tK - 0.1], ['Rank', tK - 0.1, tF + 0.35]];
    if (hk < 1) { let st = ''; STEPS.forEach(([nm, a, b], i) => { const on = t >= a, done = t >= b; const k = ex(p(t, tR - 0.35 + i * 0.07, tR - 0.05 + i * 0.07));
        st += `<div style="flex:1;display:flex;align-items:center;justify-content:center;gap:14px;height:120px;border-radius:26px;opacity:${k};transform:scale(${on && !done ? 1.06 : 1});background:${done ? C.green : on ? C.gold : 'rgba(255,255,255,.12)'};border:3px solid ${done ? C.green : on ? C.gold : 'rgba(255,255,255,.25)'}">${done ? check(1, 52, '#fff').replace('background:#fff', 'background:rgba(255,255,255,.25)') : ''}<span style="font:700 64px Barlow;color:${on || done ? (done ? '#fff' : '#0B1324') : '#fff'}">${nm}</span></div>`; });
      html += `<div class="abs" style="left:60px;right:60px;top:170px;display:flex;gap:18px;opacity:${1 - hk}">${st}</div>`; }
    // 2. the notice: scanned, fields pulled out, then translated
    if (pull > 0 && fold < 1) {
      const sc0 = tR - 0.05, sc1 = tR + 0.55; const scan = p(t, sc0, sc1);
      const tr = (i) => io(p(t, tT + i * 0.09, tT + 0.3 + i * 0.09));
      const sw = (fr, en, i) => { const k = tr(i); return k <= 0 ? fr : k >= 1 ? en : `<span style="filter:blur(${Math.sin(Math.PI * k) * 7}px);opacity:${0.4 + 0.6 * Math.abs(1 - 2 * k)}">${k < 0.5 ? fr : en}</span>`; };
      const L2 = [["Objet : fourniture d'équipements d'ophtalmologie pour les établissements de santé", 'Scope: supply of ophthalmology equipment for healthcare facilities', 0.16],
        ['Valeur estimée : 182,9 M$', 'Estimated value: $182.9M', 0.36], ['Date limite de remise des offres : dans 26 jours', 'Bid deadline: in 26 days', 0.52], ['Acheteur : Resah, centrale d’achat hospitalière', 'Buyer: Resah, hospital purchasing body', 0.68], ['Lots : 4 · Durée : 48 mois', 'Lots: 4 · Term: 48 months', 0.84]];
      let body = ''; L2.forEach(([fr, en, y], i) => { const hit = scan >= y; body += `<div style="font:500 34px/1.35 Plex;color:#2A3346;margin-top:22px;padding:6px 10px;border-radius:10px;background:${hit && i > 0 && i < 4 ? 'rgba(240,207,122,.38)' : 'transparent'}">${sw(fr, en, i + 2)}</div>`; });
      const lang = tr(0) > 0.5 ? 'EN' : 'FR';
      const card = `<div style="background:#fff;border-radius:40px;padding:44px 46px;position:relative;overflow:hidden;box-shadow:0 40px 90px rgba(0,0,0,.45)">
        <div style="display:flex;align-items:center;gap:16px">${flag('fr', 56)}<span style="font:600 32px Plex;color:#5F6B80">Resah · France</span><span style="margin-left:auto;font:700 32px Plex;color:#fff;background:${lang === 'EN' ? C.green : '#2E62B8'};padding:6px 18px;border-radius:12px;transform:scale(${1 + 0.25 * Math.sin(Math.PI * tr(0))});display:inline-block">${lang}</span></div>
        <div style="font:700 28px Plex;letter-spacing:3px;color:#6B7891;margin-top:28px">${sw('AVIS DE MARCHÉ', 'CONTRACT NOTICE', 0)}</div>
        <div style="font:700 64px/1.08 Plex;color:#0B1324;margin-top:10px">${sw("Équipements d'ophtalmologie", 'Ophthalmology equipment', 1)}</div>${body}
        ${scan > 0 && scan < 1 ? `<div class="abs" style="left:0;right:0;top:${lerp(150, 880, scan)}px;height:8px;background:${C.gold};box-shadow:0 0 0 6px rgba(240,207,122,.25)"></div>` : ''}</div>`;
      const s0 = lerp(0.35, 1, pull) * lerp(1, 0.6, fold);
      html += `<div class="abs" style="left:60px;width:960px;top:${lerp(900, 360, pull) + fold * 120}px;transform:scale(${s0});transform-origin:50% 0;opacity:${cl(pull * 2) * (1 - fold)}">${card}</div>`;
      // fields pulled out by the read
      const FL = [['Buyer', 'Resah'], ['Value', '$182.9M'], ['Deadline', '26 days'], ['Product', 'HS 9018.50']];
      let ch = ''; FL.forEach(([a, b], i) => { const k = bk(p(t, sc0 + 0.15 + i * 0.12, sc0 + 0.45 + i * 0.12)); ch += `<div style="width:468px;background:${C.card};border:2px solid ${C.gold};border-radius:22px;padding:18px 24px;opacity:${cl(k * 2)};transform:scale(${lerp(0.6, 1, k)})"><div style="font:600 26px Plex;color:#9FB1D3">${a}</div><div style="font:700 44px Plex;color:#fff">${b}</div></div>`; });
      html += `<div class="abs" style="left:60px;width:960px;top:1340px;display:flex;flex-wrap:wrap;gap:24px;opacity:${(1 - fold)}">${ch}</div>`;
    }
    // 3. ranked by fit: the notice becomes a row, gets its score and climbs to the top
    if (fold > 0) {
      const ring = p(t, tK - 0.05, tK + 0.45), climb = io(p(t, tF - 0.2, tF + 0.25)), found = ex(p(t, tF + 0.2, tF + 0.45));
      const R = [['gb', 'Hygiene services and equipment', 'Scotland Excel · $112.4M', 61.4], ['dk', 'Pharmaceutical products', 'Amgros, Denmark · $118.3M', 46.9], ['fr', 'Ophthalmology equipment', 'Resah, France · $182.9M · 26 days', 73.6]];
      const H = 190; const pos = [lerp(0, 1, climb), lerp(1, 2, climb), lerp(2, 0, climb)];
      let rows = ''; R.forEach(([cc, ti, sub, sc_], i) => { const me = i === 2; const v = me ? sc_ * ring : sc_; const k = ex(p(t, tK - 0.35 + i * 0.08, tK - 0.05 + i * 0.08));
        const rk = Math.round(pos[i]) + 1;
        rows += `<div class="abs" style="left:0;right:0;top:${pos[i] * H}px;height:${H}px;display:flex;align-items:center;gap:24px;padding:0 34px;border-top:${pos[i] > 0.5 ? '2px solid #E1E6EF' : 'none'};background:${me ? `rgba(240,207,122,${0.35 * found})` : 'transparent'};opacity:${k};z-index:${me ? 2 : 1}">
          <div style="font:700 70px/1 Barlow;color:${rk === 1 ? C.deep : '#9AA6BA'};width:50px">${rk}</div>
          <div style="position:relative;width:110px;height:110px;flex:none">${ring_(55, 9, v / 100, me ? C.deep : '#9AA6BA')}<div class="abs" style="inset:0;display:flex;align-items:center;justify-content:center;font:700 34px Plex;color:#0B1324">${v.toFixed(1)}</div></div>
          <div style="flex:1;min-width:0"><div style="display:flex;align-items:center;gap:14px"><span style="font:700 40px Plex;color:#0B1324;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${ti}</span>${me ? `<span style="flex:none;font:700 28px Plex;color:#fff;background:${C.green};padding:4px 14px;border-radius:10px;opacity:${found}">FOUND</span>` : ''}</div>
          <div style="display:flex;align-items:center;gap:10px;margin-top:6px">${flag(cc, 36)}<span style="font:500 28px Plex;color:#5F6B80">${sub}</span></div></div></div>`; });
      html += `<div class="abs" style="left:60px;width:960px;top:${lerp(560, 420, fold)}px;height:${3 * H + 70}px;background:#fff;border-radius:40px;overflow:hidden;box-shadow:0 40px 90px rgba(0,0,0,.45);opacity:${fold}">${rows}<div class="abs" style="left:34px;bottom:20px;font:500 28px Plex;color:#6B7891">Ranked by fit to your profile · fit score out of 100</div></div>`;
    }
  } else if (sc.id === 'sup') {
    ground = C.navy; const W_ = (r) => wt('f2', r); const tRe = W_(/^Real/), tPr = W_(/^proven/), tAw = W_(/^award/), tCu = W_(/^customs/), tRc = W_(/^records/);
    html += benefit('Real manufacturers', tRe - sc.t0 - 0.1, lt, '#fff');
    const mk = ex(p(t, tRe + 0.1, tRe + 0.5)); const ok = p(t, tRc, tRc + 0.3);
    html += `<div class="abs" style="left:60px;width:960px;top:${lerp(900, 480, mk)}px;opacity:${mk};background:#fff;border-radius:36px;padding:34px 40px;box-shadow:0 30px 80px rgba(0,0,0,.4);border:5px solid ${ok > 0 ? C.green : '#fff'}">
      <div style="display:flex;align-items:center;gap:22px"><div style="width:96px;height:96px;border-radius:22px;background:#EEF1F6;display:flex;align-items:center;justify-content:center"><svg width="64" height="64" viewBox="0 0 24 24"><path d="M2 20V9l6 4V9l6 4V4h4l1 9v7z" fill="#0B1324"/></svg></div>
      <div style="flex:1"><div style="display:flex;align-items:center;gap:12px">${flag('de', 40)}<span style="font:600 28px Plex;color:#6B7891">Manufacturer · Germany</span></div><div style="font:700 50px Plex;color:#0B1324">Optix Medical GmbH</div><div style="font:500 30px Plex;color:#3C475C">ophthalmic instruments</div></div>
      <span style="font:700 ${ok > 0 ? 44 : 30}px ${ok > 0 ? 'Barlow' : 'Plex'};letter-spacing:${ok > 0 ? 3 : 0}px;color:#fff;background:${ok > 0 ? C.green : '#9AA6BA'};padding:8px 20px;border-radius:14px;transform:scale(${ok > 0 ? lerp(1.5, 1, ex(ok)) : 1});display:inline-block">${ok > 0 ? 'PROVEN' : 'claimed'}</span></div></div>`;
    const DOCS = [[tAw, 60, 'AWARD RECORD', 'Supplied ophthalmic equipment to 6 public hospitals', 'public award notices', -1], [tCu, 560, 'CUSTOMS RECORD', 'Exports under HS 9018.50, every month', 'trade and customs data', 1]];
    DOCS.forEach(([tw, x, h, d, src, dir]) => { const k = ex(p(t, tw - 0.15, tw + 0.3)); if (k <= 0) return; const ln = p(t, tw + 0.1, tw + 0.4);
      html += `<div class="abs" style="left:${x + 220}px;top:${780}px;width:6px;height:${110 * ln}px;background:${C.gold}"></div>
        <div class="abs" style="left:${x + dir * (1 - k) * 500}px;top:890px;width:460px;opacity:${k};background:#FFFDF6;border-radius:24px;padding:28px 30px;box-shadow:0 30px 60px rgba(0,0,0,.4);transform:rotate(${dir * (1 - k) * 8}deg)">
        <div style="display:flex;align-items:center;justify-content:space-between"><span style="font:700 34px Barlow;letter-spacing:2px;color:${C.deep}">${h}</span>${check(p(t, tRc, tRc + 0.3), 50)}</div>
        <div style="font:600 32px/1.3 Plex;color:#0B1324;margin-top:14px">${d}</div>${[70, 90, 60].map((w) => `<div style="height:12px;width:${w}%;border-radius:4px;background:#E2E6EE;margin-top:14px"></div>`).join('')}
        <div style="font:500 24px Plex;color:#6B7891;margin-top:16px">source: ${src}</div></div>`; });
    html += `<div class="abs" style="left:60px;top:1470px;font:500 28px Plex;color:#C9D3E6;opacity:${mk}">Company name illustrative</div>`;
  } else if (sc.id === 'contacts') {
    ground = C.navy; const W_ = (r) => wt('f3', r); const tEx = W_(/^Export/), tSa = W_(/^sales/), tSt = W_(/^straight/), tOw = W_(/^own/);
    html += benefit('Export and sales desks', tEx - sc.t0 - 0.1, lt, '#fff');
    const bk_ = ex(p(t, tEx - 0.2, tEx + 0.2));
    const hiE = p(t, tEx, tEx + 0.25), hiS = p(t, tSa, tSa + 0.25); const own = ex(p(t, tSt, tSt + 0.35)); const ow2 = p(t, tOw, tOw + 0.3);
    html += `<div class="abs" style="left:60px;width:960px;top:${lerp(900, 480, bk_)}px;opacity:${bk_};background:#fff;border-radius:30px;overflow:hidden;box-shadow:0 30px 80px rgba(0,0,0,.45);outline:${own > 0 ? `${6 * own}px solid ${C.gold}` : 'none'}">
      <div style="height:76px;background:#EEF1F6;display:flex;align-items:center;gap:12px;padding:0 26px"><i style="width:16px;height:16px;border-radius:50%;background:#E5534B"></i><i style="width:16px;height:16px;border-radius:50%;background:#E9B949"></i><i style="width:16px;height:16px;border-radius:50%;background:#3EC28A"></i><div style="margin-left:14px;flex:1;height:48px;border-radius:12px;background:#fff;font:500 30px/48px Plex;color:#3C475C;padding:0 18px">🔒 optix-medical.example/contact</div></div>
      <div style="padding:30px 40px 36px"><div style="font:700 50px Plex;color:#0B1324">Contact us</div>
      <div style="font:600 34px Plex;color:#0B1324;margin-top:20px;padding:8px 12px;border-radius:10px;background:rgba(240,207,122,${0.6 * hiE})">Export department</div><div style="font:500 30px Plex;color:#6B7891;padding:0 12px">export@ ••••••.de</div>
      <div style="font:600 34px Plex;color:#0B1324;margin-top:16px;padding:8px 12px;border-radius:10px;background:rgba(240,207,122,${0.6 * hiS})">Sales</div><div style="font:500 30px Plex;color:#6B7891;padding:0 12px">+49 ••• ••• •••• · WhatsApp</div></div></div>`;
    if (own > 0) html += `<div class="abs" style="left:560px;top:440px;transform:rotate(-6deg) scale(${lerp(1.6, 1, own)});opacity:${own};font:700 40px Barlow;letter-spacing:2px;color:#0B1324;background:${C.gold};padding:10px 22px;border-radius:14px;white-space:nowrap;box-shadow:0 12px 30px rgba(0,0,0,.35)">SUPPLIER'S OWN SITE</div>`;
    const OUT = [[tEx + 0.15, 'gmail', 'Export desk', 'export@ ••••••.de'], [tSa + 0.15, 'whatsapp', 'Sales desk', '+49 ••• ••• ••••']];
    OUT.forEach(([tw, ic, h, v], i) => { const k = ex(p(t, tw, tw + 0.45)); if (k <= 0) return;
      html += `<div class="abs" style="left:60px;width:960px;top:${lerp(800, 1160 + i * 150, k)}px;opacity:${k}">${`<div style="display:flex;align-items:center;gap:22px;background:${C.card};border:3px solid ${C.gold};border-radius:28px;padding:22px 30px">${appIcon(ic, 76)}<div style="flex:1"><div style="font:700 40px Plex;color:#fff">${h}</div><div style="font:500 30px Plex;color:#9FB1D3">${v}</div></div><span style="font:600 28px Plex;color:#0B1324;background:${C.gold};padding:6px 16px;border-radius:12px;opacity:${ow2}">from their own site ✓</span></div>`}</div>`; });
    html += `<div class="abs" style="left:60px;top:1480px;font:500 28px Plex;color:#C9D3E6;opacity:${bk_}">Contacts masked · company illustrative</div>`;
  } else if (sc.id === 'reverse') {
    ground = C.navy; const W_ = (r) => wt('f4', r); const tD = W_(/^Drop/), tDl = W_(/^deal/), tRd = W_(/^redacted/), tG = W_(/^Get/), tB = W_(/^blueprint/);
    html += `<div class="abs" style="left:80px;right:80px;top:150px;font:700 130px/0.95 Barlow;color:#fff">${words('Deal reverse engineering', tD - sc.t0 - 0.2, lt, { gap: 0.08 })}</div>`;
    const zk = ex(p(t, tD - 0.25, tD + 0.1)); const side = io(p(t, tG - 0.15, tG + 0.35));
    const fall = p(t, tD + 0.05, tDl + 0.15); const land = fall >= 1 ? 1 : E.back ? bk(fall) : ex(fall);
    // drop zone
    html += `<div class="abs" style="left:${lerp(110, 40, side)}px;top:520px;width:${lerp(860, 420, side)}px;height:760px;border:5px dashed ${fall >= 1 ? C.gold : '#4A5F94'};border-radius:40px;opacity:${zk};background:rgba(255,255,255,.03)">
      <div class="abs" style="left:0;right:0;bottom:30px;text-align:center;font:600 ${lerp(36, 26, side)}px Plex;color:#9FB1D3">Drop a deal here</div></div>`;
    // the contract falls in, then gets redacted bar by bar
    let doc = `<div style="font:700 30px Plex;color:#0B1324;letter-spacing:1px">PURCHASE CONTRACT</div>`; const RD = [1, 3, 4, 6, 8];
    for (let i = 0; i < 10; i++) { const w = [92, 70, 84, 60, 88, 75, 50, 82, 66, 72][i]; const r = RD.indexOf(i); const rk = r < 0 ? 0 : p(t, tRd - 0.25 + r * 0.08, tRd + r * 0.08);
      doc += `<div style="position:relative;height:20px;margin-top:22px;width:${w}%;border-radius:4px;background:#D3DAE6"><div class="abs" style="left:0;top:-4px;height:28px;width:${rk * 100}%;background:#0B1324;border-radius:3px"></div></div>`; }
    html += `<div class="abs" style="left:${lerp(220, 70, side)}px;top:${lerp(-700, 590, land)}px;width:${lerp(640, 360, side)}px;transform:rotate(${lerp(-12, -3, land)}deg);background:#fff;border-radius:22px;padding:${lerp(40, 26, side)}px;box-shadow:0 40px 80px rgba(0,0,0,.5)">${doc}</div>`;
    if (t >= tRd - 0.2 && side < 0.5) html += `<div class="abs" style="left:640px;top:460px;transform:rotate(8deg);font:700 46px Barlow;letter-spacing:3px;color:#fff;background:#C62D23;padding:8px 22px;border-radius:12px;opacity:${ex(p(t, tRd, tRd + 0.2)) * (1 - side * 2)}">REDACTED</div>`;
    // the blueprint comes back
    const R = [['Product', 'ophthalmic instruments, HS 9018.50'], ['Parties', 'buyer and seller hints'], ['Proven suppliers', '3, from award records'], ['Benchmark price', 'from import records'], ['Your way in', 'supply the winning bidder']];
    if (side > 0) { let rows = ''; R.forEach(([h, d], i) => { const k = ex(p(t, tB - 0.1 + i * 0.13, tB + 0.25 + i * 0.13)); rows += `<div style="padding:14px 0;border-top:${i ? '2px solid #22305A' : 'none'};opacity:${k};transform:translateX(${(1 - k) * 40}px)"><div style="font:600 24px Plex;color:#8FA2C7">${h}</div><div style="font:700 30px Plex;color:#fff">${d}</div></div>`; });
      html += `<div class="abs" style="left:${lerp(1100, 490, side)}px;top:520px;width:550px;background:${C.card};border:3px solid ${C.gold};border-radius:30px;padding:24px 30px">
        <div style="font:700 48px Barlow;color:${C.gold};letter-spacing:2px">THE BLUEPRINT</div>${rows}</div>`;
      html += `<div class="abs" style="left:450px;top:840px;font:700 70px Barlow;color:${C.gold};opacity:${side}">→</div>`; }
    html += `<div class="abs" style="left:60px;top:1330px;font:500 28px Plex;color:#8FA2C7">Illustrative example</div>`;
  } else if (sc.id === 'price') {
    ground = C.light; const tf = L('f5') + 0.05;
    html += benefit('Origin price intelligence', tf - 0.1, lt);
    const G = [['Bugisu AA', 2.7215], ['Bugisu A', 2.7115], ['Wugar', 2.7015], ['Drugar', 2.5115], ['Robusta Screen 18', 1.8563]];
    const ck = ex(p(lt, tf, tf + 0.4)); let rows = ''; G.forEach(([g, v], i) => { const q = ex(p(lt, tf + 0.2 + i * 0.06, tf + 0.6 + i * 0.06)); rows += `<div style="display:flex;align-items:center;gap:20px;margin-top:20px;opacity:${q}"><div style="width:290px;font:600 32px Plex;color:#D5DDEB">${g}</div><div style="flex:1;height:18px;border-radius:9px;background:#1E2B48"><div style="width:${q * (v / 2.8) * 100}%;height:100%;border-radius:9px;background:${i === 0 ? C.gold : '#4A5E8C'}"></div></div><div class="num" style="width:120px;text-align:right;font:700 36px Plex;color:#fff">$${v.toFixed(2)}</div></div>`; });
    html += `<div class="abs" style="left:60px;width:960px;top:${lerp(1500, 500, ck)}px;background:${C.card};border-radius:40px;padding:44px 46px;opacity:${ck}">
      <div style="display:flex;align-items:center;gap:18px">${flag('ug', 60)}<span style="font:600 34px Plex;color:#AFC0DD">Arabica coffee · Kampala, Uganda</span></div>
      <div style="display:flex;align-items:baseline;gap:18px;margin-top:8px"><span class="num" style="font:700 210px/1 Barlow;color:${C.gold};letter-spacing:-4px">$${(2.72 * ex(p(lt, tf, tf + 0.7))).toFixed(2)}</span><span style="font:700 56px Barlow;color:#fff">per lb</span></div>${rows}
      <div style="font:500 28px Plex;color:#8FA2C7;margin-top:26px">Uganda Coffee Development Authority, 6 Nov 2026</div></div>`;
    { const SRC = ['UCDA Uganda', 'World Bank', 'IMF', 'FAO', 'ICO', 'USDA', 'USDA AMS', 'USDA FV', 'US Census', 'Eurostat', 'EU Commission', 'UN Comtrade', 'China NBS', 'Statistics Norway', 'Spices Board India', 'MPOB', 'Global Dairy Trade', 'LME'];
      const tf0 = wt('f5', /^from/), te = wt('f5', /^eighteen/), to = wt('f5', /^sources/); const nOn = Math.round(lerp(0, 18, p(t, tf0, to)));
      let g = ''; SRC.forEach((nm, i) => { const k = ex(p(t, tf0 + i * ((to - tf0) / 18), tf0 + i * ((to - tf0) / 18) + 0.25));
        g += `<div style="font:600 24px Plex;color:${i < nOn ? '#0B1324' : '#9AA6BA'};background:${i < nOn ? (i === 0 ? C.gold : '#fff') : 'rgba(255,255,255,.4)'};border:2px solid ${i < nOn ? '#D6DCE6' : 'transparent'};padding:8px 14px;border-radius:12px;opacity:${0.3 + 0.7 * k};transform:scale(${lerp(0.8, 1, k)})">✓ ${nm}</div>`; });
      html += `<div class="abs" style="left:60px;width:960px;top:1270px;opacity:${ex(p(t, tf0 - 0.2, tf0 + 0.1))}"><div style="font:700 56px Barlow;color:${C.ink}"><span class="num" style="color:${C.deep}">${nOn}</span> official price sources</div><div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:14px">${g}</div></div>`; }
  } else if (sc.id === 'odds') {
    ground = C.light; const tf = L('f6') + 0.05; const bd = wt('f6', /^bid/) - sc.t0;
    html += benefit('AI win probability', tf - 0.1, lt); html += `<div class="abs" style="left:80px;top:330px;display:flex;align-items:center;gap:14px;font:600 36px Plex;color:#3C475C;opacity:${ex(p(lt, tf, tf + 0.4))}">${flag('fr', 44)}Resah · France · $182.9M</div>`;
    const tO = wt('f6', /^odds/) - sc.t0, tI = wt('f6', /^incumbent/) - sc.t0, tX = wt('f6', /^expected/) - sc.t0;
    const win = lerp(0, 0.154, io(p(lt, tO - 0.2, tO + 0.5))), ev = lerp(0, 1.744, io(p(lt, tX - 0.05, tX + 0.6))); const evk = ex(p(lt, tX - 0.15, tX + 0.15)); const ink = ex(p(lt, tI - 0.1, tI + 0.25)); const R = 300, Cc = Math.PI * R, k = ex(p(lt, tf - 0.05, tf + 0.35));
    html += `<div class="abs" style="left:60px;width:960px;top:${lerp(1500, 420, k)}px;height:1000px;background:#fff;border-radius:40px;box-shadow:0 30px 80px rgba(11,19,36,.12);opacity:${k}">
      <svg class="abs" style="left:${480 - R - 24}px;top:60px" width="${2 * R + 48}" height="${R + 48}"><path d="M24 ${R + 24} A${R} ${R} 0 0 1 ${2 * R + 24} ${R + 24}" fill="none" stroke="#E4E9F2" stroke-width="38" stroke-linecap="round"/><path d="M24 ${R + 24} A${R} ${R} 0 0 1 ${2 * R + 24} ${R + 24}" fill="none" stroke="${C.deep}" stroke-width="38" stroke-linecap="round" stroke-dasharray="${Cc}" stroke-dashoffset="${Cc * (1 - win)}"/></svg>
      <div class="abs" style="left:0;right:0;top:220px;text-align:center"><div class="num" style="font:700 160px/1 Barlow;color:${C.ink}">${Math.round(win * 100)}%</div><div style="font:600 32px Plex;color:#6B7891">win chance · 2 expected bidders</div></div>
      <div class="abs" style="left:60px;right:60px;top:440px;display:flex;align-items:center;gap:18px;padding:18px 22px;border-radius:20px;background:#F1F4F9;opacity:${ink};transform:translateX(${(1 - ink) * 60}px)">${check(p(lt, tI + 0.1, tI + 0.4), 48)}<span style="font:600 32px Plex;color:#0B1324">Incumbent and buyer history checked</span></div>
      <div class="abs" style="left:60px;top:560px;opacity:${evk}"><div style="font:600 32px Plex;color:#6B7891">Expected value</div><div class="num" style="font:700 190px/1 Barlow;color:${C.deep};letter-spacing:-3px">$${ev.toFixed(2)}M</div></div>
      <div class="abs" style="left:60px;right:60px;top:820px;padding-top:28px;border-top:2px solid #E1E6EF;display:flex;align-items:center;justify-content:space-between"><span style="font:600 32px Plex;color:#6B7891">Before you bid</span><span style="font:700 64px Barlow;letter-spacing:3px;color:#fff;background:${C.green};padding:4px 30px;border-radius:14px;opacity:${p(lt, bd, bd + 0.1)};transform:scale(${lerp(1.5, 1, ex(p(lt, bd, bd + 0.3)))});display:inline-block">PURSUE</span></div></div>`;
  } else if (sc.id === 'build') {
    ground = C.light; const ITEMS = ['Tender, ranked', 'Suppliers, with proof', 'Price at source', 'Freight, duty, landed cost', 'RFQ, drafted', 'Odds and expected value'];
    const b0 = L('v11'), one = wt('v11', /^one/) - sc.t0; const col = io(p(lt, one, one + 0.6));
    let rows = ''; ITEMS.forEach((s, i) => { const k = ex(p(lt, b0 + i * 0.12, b0 + i * 0.12 + 0.3)); rows += `<div style="display:flex;align-items:center;gap:24px;padding:22px 34px;border-top:${i ? '2px solid #E1E6EF' : 'none'};opacity:${k}">${check(p(lt, b0 + i * 0.12 + 0.15, b0 + i * 0.12 + 0.4), 52)}<span style="font:700 40px Plex;color:${C.ink}">${s}</span></div>`; });
    html += `<div class="abs" style="left:80px;top:170px;font:700 140px/0.95 Barlow;color:#fff;text-shadow:0 4px 30px rgba(0,0,0,.5);opacity:${1 - p(col, 0, 0.4)}">The whole deal</div>`;
    html += `<div class="abs" style="left:60px;width:960px;top:${lerp(560, 760, col)}px;transform-origin:50% 0;transform:scale(${lerp(1, 0.5, col)});background:#fff;border-radius:40px;box-shadow:0 30px 80px rgba(11,19,36,.14);opacity:${1 - p(col, 0.7, 1)}">${rows}</div>`;
    if (col > 0) { phone(540, lerp(1500, 1110, col), 0.84, p(col, 0.3, 0.8)); ui(70); html += `<div class="abs" style="left:80px;top:170px;font:700 140px/0.95 Barlow;color:#fff;text-shadow:0 4px 30px rgba(0,0,0,.5);opacity:${p(col, 0.4, 1)}">One screen.</div>`; }
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
  } else if (sc.id === 'period') {
    ground = mix(C.tg, C.navy, io(p(lt, 0, 0.35))); const nw = TL.lines.n1.words;
    html += `<div class="abs" style="left:80px;right:80px;top:560px;font:700 150px/1 Barlow;color:#fff">${nw.map(([w, wt0], i) => { const k = ex(p(t, wt0 - 0.06, wt0 + 0.12)); return `<span style="display:inline-block;margin-right:28px;opacity:${k};filter:blur(${(1 - k) * 8}px);color:${i >= 4 ? C.gold : '#fff'}">${w}</span>` + (i === 3 ? '<br>' : ''); }).join('')}</div>`;
  } else if (sc.id === 'cta') {
    ground = C.navy; const s1 = wt('v14', /^Sinder/) - sc.t0, sf = wt('v14', /^See/) - sc.t0, pa = wt('v15', /^Partners/) - sc.t0, lt0 = wt('v15', /^let/) - sc.t0;
    const mk = ex(p(lt, s1 - 0.1, s1 + 0.35)), wm = ex(p(lt, s1, s1 + 0.35)), sk = ex(p(lt, sf - 0.05, sf + 0.3)), out1 = 1 - p(lt, pa - 0.25, pa);
    html += `<div class="abs" style="left:0;right:0;top:220px;display:flex;align-items:center;justify-content:center;gap:34px"><div style="transform:scale(${lerp(1.6, 1, mk)});opacity:${cl(mk * 3)}">${MARK(190, 'c', io(p(lt, s1 - 0.1, s1 + 0.5)))}</div><div style="font:700 190px/1 Barlow;letter-spacing:4px;color:#fff;clip-path:inset(0 ${100 - wm * 100}% 0 0)">SINDER</div></div>
      <div class="abs" style="left:80px;right:80px;top:560px;font:700 150px/0.95 Barlow;color:${C.gold};opacity:${sk * out1};filter:blur(${(1 - sk) * 8}px)">Nothing slips<br>past you.</div>`;
    const k2 = ex(p(lt, pa - 0.1, pa + 0.3)), k3 = ex(p(lt, lt0 - 0.05, lt0 + 0.3)), k4 = ex(p(lt, lt0 + 0.35, lt0 + 0.7));
    html += `<div class="abs" style="left:80px;right:80px;top:600px;opacity:${k2};font:700 110px/1.02 Barlow;color:#fff">Partners and investors</div>
      <div class="abs" style="left:0;right:0;top:800px;text-align:center;font:700 250px/1 Barlow;color:${C.gold};opacity:${k3};filter:blur(${(1 - k3) * 10}px)">Let's talk.</div>
      <div class="abs" style="left:0;right:0;top:1150px;display:flex;justify-content:center;opacity:${k4}"><div style="font:600 64px Plex;color:${C.navy};background:${C.gold};padding:30px 60px;border-radius:24px">Etamar@sinder.pro</div></div>
      <div class="abs" style="left:0;right:0;top:1330px;text-align:center;font:600 40px Plex;color:#9FB1D3;opacity:${k4}">sinder.pro</div>
      <div class="abs" style="left:0;right:0;top:1790px;text-align:center;font:500 26px/1.35 Plex;color:#5E6E90;opacity:${k4}">Music: Future Business, Marco Margna, CC BY 3.0<br>Images: NASA · FILMING CORK, CC BY 3.0 · Quintin Soloviev, CC BY 4.0 · Wikimedia Commons (public domain, CC0)</div>`;
    $('black').style.opacity = p(lt, D - 0.4, D);
  }
  const hasM = setMedia(sc.id, lt, D); $('ground').style.background = (hasM && MEDIA[sc.id][0].startsWith('v:')) ? 'transparent' : ground; drawMap(t, hasM && sc.id !== 'reveal' && sc.id !== 'cta' ? null : mapO); $('fx').innerHTML = html;
  $('subs').innerHTML = (sc.id === 'period' || (sc.id === 'cta' && t >= wt('v15', /^let/) - 0.1)) ? '' : subtitle(t);
}
const tl = gsap.timeline({ paused: true });
const clock = { t: 0 };
tl.to(clock, { t: TL.total, duration: TL.total, ease: 'none', onUpdate: () => render(tl.time()) }, 0);
render(0);
window.__timelines = window.__timelines || {};
window.__timelines['main'] = tl;
