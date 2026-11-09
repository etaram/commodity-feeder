// Sinder film - CTO helpers. Pure functions of time (no state, no Date, no Math.random), safe to call
// from render(t) inside the paused GSAP timeline's onUpdate. Paste after head8.js's `cl/p/lerp` block.
// Every helper returns numbers or CSS strings; render(t) decides where they go.
// Conventions: t, t0, dur in seconds; k in 0..1; px in CSS px of the 1080x1920 stage.

const HX = (() => {
  const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
  const prog = (t, a, b) => clamp((t - a) / (b - a));
  const mixN = (a, b, k) => a + (b - a) * k;
  const smooth = (x) => { x = clamp(x); return x * x * (3 - 2 * x); };

  // ---------------------------------------------------------------------------------------------
  // 1. Closed-form damped spring (unit step response). Seekable: value depends on t only.
  //    t: seconds since the spring was released (t<=0 returns 0).
  //    zeta: damping ratio (0.35 bouncy, 0.6 lively UI, 0.8 premium settle, 1 critical, >1 sluggish).
  //    freq: undamped natural frequency in Hz (1.5-3 typical for UI; higher = snappier).
  //    v0: initial velocity in units/s (0 = released from rest).
  //    Returns x(t) going 0 -> 1. Use lerp(from, to, spring(...)).
  function spring(t, zeta = 0.7, freq = 2, v0 = 0) {
    if (t <= 0) return 0;
    const w = 2 * Math.PI * freq;
    // displacement e = x - 1, e(0) = -1, e'(0) = v0
    let e;
    if (zeta < 1) {
      const wd = w * Math.sqrt(1 - zeta * zeta);
      const A = -1, B = (v0 + zeta * w * A) / wd;
      e = Math.exp(-zeta * w * t) * (A * Math.cos(wd * t) + B * Math.sin(wd * t));
    } else if (zeta === 1) {
      const A = -1, B = v0 + w * A;
      e = Math.exp(-w * t) * (A + B * t);
    } else {
      const s = w * Math.sqrt(zeta * zeta - 1), r1 = -zeta * w + s, r2 = -zeta * w - s;
      // e = c1 e^{r1 t} + c2 e^{r2 t}; c1 + c2 = -1; r1 c1 + r2 c2 = v0
      const c2 = (v0 + r1) / (r2 - r1), c1 = -1 - c2;
      e = c1 * Math.exp(r1 * t) + c2 * Math.exp(r2 * t);
    }
    return 1 + e;
  }
  // Velocity of the same spring (units/s), by central difference; used for velocity blur.
  const springVel = (t, zeta = 0.7, freq = 2, v0 = 0, h = 1 / 240) =>
    (spring(t + h, zeta, freq, v0) - spring(t - h, zeta, freq, v0)) / (2 * h);
  // Time until |x-1| stays below eps (for planning holds). Envelope bound, conservative.
  const springSettle = (zeta = 0.7, freq = 2, eps = 0.005) =>
    zeta >= 1 ? 6 / (2 * Math.PI * freq) : -Math.log(eps) / (zeta * 2 * Math.PI * freq);

  // ---------------------------------------------------------------------------------------------
  // 2. Read-line sweep. A gold line travels from `from` to `to` (px along the sweep axis) between
  //    t0 and t0+dur, on `ease` (0..1 -> 0..1). Returns the line position and a per-item factor.
  //    seen(pos) is 0 before the line reaches pos, 1 after it passed by `soft` px (smoothstep edge),
  //    so dots/rows/words flip unseen -> seen exactly when the line crosses them.
  //    Usage: const S = readLine(t, T0, 1.4, 260, 1700); row.style.opacity = lerp(.35, 1, S.seen(rowY));
  function readLine(t, t0, dur, from, to, { ease = smooth, soft = 18 } = {}) {
    const k = ease(prog(t, t0, t0 + dur));
    const pos = mixN(from, to, k);
    const dir = to >= from ? 1 : -1;
    const seen = (x) => smooth((dir * (pos - x)) / soft + 0.5);
    // glow on the line itself: 1 at the line, falls off over `w` px (use for row highlight)
    const glow = (x, w = 60) => { const d = Math.abs(pos - x) / w; return k > 0 && k < 1 ? Math.max(0, 1 - d * d) : 0; };
    return { k, pos, seen, glow, active: k > 0 && k < 1 };
  }
  // CSS for the line itself (horizontal line sweeping down). Gold core + soft bloom, no layout cost.
  const readLineCSS = (pos, { x0 = 0, x1 = 1080, alpha = 1, color = '240,207,122' } = {}) =>
    `position:absolute;left:${x0}px;width:${x1 - x0}px;top:${pos - 1.5}px;height:3px;` +
    `background:rgba(${color},${alpha});box-shadow:0 0 18px 4px rgba(${color},${0.55 * alpha}),0 0 60px 10px rgba(${color},${0.25 * alpha})`;
  // Counter tied to the sweep: value follows the line, with optional integer stepping.
  // counter(S.k, 0, 34654) -> '34,654' ; per-row counts: count rows with S.seen(y) > .5.
  const counter = (k, a, b, { decimals = 0, locale = 'en-US' } = {}) =>
    (mixN(a, b, clamp(k))).toLocaleString(locale, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  // Count items already passed by the line (pure, sorted not required).
  const seenCount = (S, positions) => positions.reduce((n, x) => n + (S.seen(x) > 0.5 ? 1 : 0), 0);

  // ---------------------------------------------------------------------------------------------
  // 3. Redaction bars. k in 0..1. In: scaleX 0->1 from the left. Out: scaleX 1->0 toward the right
  //    (origin flips so the bar wipes off in the reading direction). Use as an absolutely
  //    positioned span over the text; text underneath stays in layout, so nothing reflows.
  //    redactK(t, tIn, tOut, dur) gives the combined 0..1..0 envelope (state 'in' or 'out').
  function redactK(t, tIn, tOut = Infinity, dur = 0.28, ease = (x) => 1 - Math.pow(1 - x, 3)) {
    if (t < tOut) return { k: ease(prog(t, tIn, tIn + dur)), phase: 'in' };
    return { k: 1 - ease(prog(t, tOut, tOut + dur)), phase: 'out' };
  }
  function redactBarCSS(r, { color = '#0B1324', pad = 6, radius = 4 } = {}) {
    const origin = r.phase === 'in' ? '0% 50%' : '100% 50%';
    return `position:absolute;left:${-pad}px;right:${-pad}px;top:8%;bottom:8%;background:${color};border-radius:${radius}px;` +
      `transform-origin:${origin};transform:scaleX(${r.k.toFixed(4)});${r.k <= 0 ? 'visibility:hidden;' : ''}`;
  }
  // Staggered per-line redaction: line i starts `stagger` later. Returns redactK for line i.
  const redactLine = (t, i, tIn, tOut, { stagger = 0.06, dur = 0.28 } = {}) => redactK(t, tIn + i * stagger, tOut + i * stagger, dur);
  // Full-frame redaction wipe transition: N horizontal bars, each scaleX from left, staggered
  // top->bottom, cover by mid, then leave to the right. Cut the scene underneath at `cutAt`
  // (returned) when coverage is 100%. Returns an HTML string for #fx (or a dedicated layer).
  function redactWipe(t, t0, dur = 0.7, { bars = 12, color = '#0B1324', accent = '240,207,122', stagger = 0.35 } = {}) {
    const u = prog(t, t0, t0 + dur);
    if (u <= 0 || u >= 1) return { html: '', covered: false, cutAt: t0 + dur * 0.5 };
    const h = 1920 / bars; let html = '', covered = true;
    for (let i = 0; i < bars; i++) {
      const off = (i / (bars - 1)) * stagger * 0.5;          // each bar's local window
      const a = prog(u, off, off + 0.5 - stagger * 0.5 + 1e-6);  // 0..1 cover in first half
      const b = prog(u, 0.5 + off, 0.5 + off + 0.5 - stagger * 0.5 + 1e-6); // 0..1 uncover in second half
      const inK = 1 - Math.pow(1 - a, 3), outK = Math.pow(b, 3);
      const k = u < 0.5 ? inK : 1 - outK, origin = u < 0.5 ? '0% 50%' : '100% 50%';
      if (k < 0.999) covered = false;
      // thin gold leading edge while moving
      const edge = (k > 0.02 && k < 0.98) ? `box-shadow:inset ${u < 0.5 ? -4 : 4}px 0 0 rgba(${accent},.9)` : '';
      html += `<div style="position:absolute;left:0;top:${(i * h).toFixed(2)}px;width:1080px;height:${(h + 1).toFixed(2)}px;background:${color};transform-origin:${origin};transform:scaleX(${k.toFixed(4)});${edge}"></div>`;
    }
    return { html, covered, cutAt: t0 + dur * 0.5 };
  }

  // ---------------------------------------------------------------------------------------------
  // 4. Iris (clip-path circle from a tap point). Opens to the farthest frame corner exactly.
  //    k 0..1 (ease it yourself, e.g. ex() or power3.inOut). close=true runs it backwards.
  function irisRadius(cx, cy, w = 1080, h = 1920) {
    return Math.hypot(Math.max(cx, w - cx), Math.max(cy, h - cy));
  }
  const irisCSS = (k, cx, cy, { w = 1080, h = 1920, minR = 0 } = {}) =>
    `clip-path:circle(${mixN(minR, irisRadius(cx, cy, w, h) + 2, clamp(k)).toFixed(2)}px at ${cx}px ${cy}px)`;
  // Optional rim ring that rides the iris edge (same radius, so it never drifts from the clip).
  const irisRimCSS = (k, cx, cy, { w = 1080, h = 1920, color = '240,207,122', width = 4 } = {}) => {
    const r = irisRadius(cx, cy, w, h) * clamp(k), a = clamp(k * 6) * (1 - clamp((k - 0.7) / 0.3));
    return `position:absolute;left:${cx - r}px;top:${cy - r}px;width:${2 * r}px;height:${2 * r}px;border-radius:50%;` +
      `box-shadow:0 0 0 ${width}px rgba(${color},${a.toFixed(3)}),0 0 40px 6px rgba(${color},${(0.35 * a).toFixed(3)});pointer-events:none`;
  };

  // ---------------------------------------------------------------------------------------------
  // 5. Two-phase zoom with matched speed at the seam (log-space, C1 continuous).
  //    Zoom is perceived in log-scale, so we interpolate L = ln(scale). Phase A runs sA0 -> sSeam over
  //    [t0, tc] easing IN (accelerating), phase B runs sSeam' -> sB1 over [tc, t1] easing OUT, and the
  //    log-velocity at tc is identical on both sides, so the cut is invisible as a speed change.
  //    Phase B may live in a different coordinate space (e.g. A = page DOM scale, B = canvas map z):
  //    pass sB0 for its starting scale; only its log-speed is matched.
  //    Uses power curves: A: L = LA0 + dA * u^pA  (u = (t-t0)/(tc-t0)), velocity at seam = pA*dA/TA
  //                       B: L = LB0 + dB * (1-(1-v)^pB), velocity at seam = pB*dB/TB
  //    Given everything but pB, we solve pB so velocities match (clamped to [1.2, 8]).
  //    Returns { s, phase, logVel } where logVel = d ln(s)/dt (use it for zoom blur strength).
  function zoom2(t, { t0, tc, t1, sA0, sA1, sB0, sB1, pA = 3 }) {
    const TA = tc - t0, TB = t1 - tc;
    const dA = Math.log(sA1 / sA0), dB = Math.log(sB1 / sB0);
    const vSeam = (pA * dA) / TA;                         // log-units per second at the cut
    const pB = clamp(Math.abs(dB) > 1e-9 ? (vSeam * TB) / dB : 3, 1.2, 8);
    if (t < tc) {
      const u = prog(t, t0, tc), L = Math.log(sA0) + dA * Math.pow(u, pA);
      return { s: Math.exp(L), phase: 'A', logVel: t <= t0 ? 0 : (pA * dA * Math.pow(u, pA - 1)) / TA, pB };
    }
    const v = prog(t, tc, t1), L = Math.log(sB0) + dB * (1 - Math.pow(1 - v, pB));
    return { s: Math.exp(L), phase: 'B', logVel: t >= t1 ? 0 : (pB * dB * Math.pow(1 - v, pB - 1)) / TB, pB };
  }
  // If zoom2 reports pB at a clamp (1.2 or 8) the seam speed is NOT matched: pick phase B's length
  // with this instead (target pB 3 = cubic ease-out): TB = pB*dB / vSeam.
  const zoom2DurB = ({ t0, tc, sA0, sA1, sB0, sB1, pA = 3 }, pB = 3) =>
    (pB * Math.log(sB1 / sB0)) / ((pA * Math.log(sA1 / sA0)) / (tc - t0));
  // Transform for a DOM element zooming about a focal point (fx, fy) in stage px.
  // Keeps (fx,fy) fixed on screen; ox/oy move the focal point to (tx,ty) as k goes 0..1.
  const zoomAboutCSS = (s, fx, fy, { tx = fx, ty = fy } = {}) =>
    `transform-origin:0 0;transform:translate(${(tx - fx * s).toFixed(3)}px,${(ty - fy * s).toFixed(3)}px) scale(${s.toFixed(5)})`;

  // ---------------------------------------------------------------------------------------------
  // 6. Motion blur approximations (when data-motion-blur is unsuitable: innerHTML-rebuilt nodes,
  //    canvas content, zooms). Blur peaks with speed, so it peaks at the cut frame of zoom2.
  //    a) Translation: px/frame -> CSS blur radius. Real shutter smear length = speed * shutter/360.
  //       A gaussian std of ~ smear/2.5 reads like a box smear of that length.
  //       velocity in px/s; fps 30; shutter 180-270 deg. maxPx caps cost and legibility.
  function velBlurPx(velPxPerSec, { fps = 30, shutter = 216, maxPx = 24, minPx = 0.35 } = {}) {
    const smear = Math.abs(velPxPerSec) / fps * (shutter / 360);
    const b = Math.min(maxPx, smear / 2.5);
    return b < minPx ? 0 : b;
  }
  // Velocity of any pure position function f(t) (px) by central difference.
  const vel = (f, t, h = 1 / 240) => (f(t + h) - f(t - h)) / (2 * h);
  // Directional (1-axis) blur via an inline SVG filter is sharper than CSS blur for horizontal
  // whips: put dirBlurSVG(id) once in the DOM, then set the stdDeviation each frame with dirBlurSet.
  const dirBlurSVG = (id) => `<svg width="0" height="0" style="position:absolute"><filter id="${id}" x="-20%" y="-5%" width="140%" height="110%"><feGaussianBlur id="${id}g" stdDeviation="0 0"/></filter></svg>`;
  const dirBlurSet = (id, sx, sy = 0) => { const g = document.getElementById(id + 'g'); if (g) g.setAttribute('stdDeviation', `${sx.toFixed(2)} ${sy.toFixed(2)}`); return sx || sy ? `url(#${id})` : 'none'; };
  //    b) Zoom: blur radius from log-velocity. An element of radius R (px, from zoom centre to its
  //       farthest visible edge) moves its edge at R*logVel px/s. Returns a CSS blur px for DOM layers.
  const zoomBlurPx = (logVel, R = 900, opts = {}) => velBlurPx(R * logVel, { maxPx: 18, ...opts });
  //    c) True zoom-blur for a CANVAS you draw yourself (the dot map): accumulate N draws across the
  //       shutter window. drawAt(tSub, ctx) must draw the scene at sub-time tSub into ctx.
  //       Equal-weight average: each pass is added ('lighter') at alpha 1/N, which is the exact
  //       premultiplied mean (also correct over transparent pixels). scratch = a second canvas with
  //       the same backing size (create it once at setup, not per frame); dpr from hiDPICanvas.
  //       Cost = N x the draw. Use N = 1 when speed is low (returns early), up to 8-12 at the peak.
  function shutterTimes(t, { fps = 30, shutter = 216, n = 8 } = {}) {
    if (n <= 1) return [t];
    const span = (shutter / 360) / fps, out = [];
    for (let i = 0; i < n; i++) out.push(t - span / 2 + (span * (i + 0.5)) / n);
    return out;
  }
  function accumulate(ctx, times, drawAt, scratch, dpr = 1) {
    ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height); ctx.restore();
    if (times.length === 1) { drawAt(times[0], ctx); return; }
    const sc = scratch.getContext('2d'), n = times.length;
    times.forEach((ts) => {
      sc.setTransform(1, 0, 0, 1, 0, 0); sc.clearRect(0, 0, scratch.width, scratch.height);
      sc.setTransform(dpr, 0, 0, dpr, 0, 0);
      drawAt(ts, sc);
      ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalCompositeOperation = 'lighter'; ctx.globalAlpha = 1 / n;
      ctx.drawImage(scratch, 0, 0); ctx.restore();
    });
  }
  // Pick a sample count from pixel speed so slow frames stay single-draw (cheap and crisp).
  const samplesFor = (pxPerFrame, { min = 1, max = 10, pxPerSample = 6 } = {}) =>
    Math.max(min, Math.min(max, Math.ceil(Math.abs(pxPerFrame) / pxPerSample)));

  // ---------------------------------------------------------------------------------------------
  // 7. Per-word blur swap with spring. Old phrase leaves (blur up, fade), new phrase lands per word
  //    on a spring (opacity + blur + small y), staggered. Pure HTML string.
  function wordSwap(t, tSwap, oldText, newText, { gap = 0.05, zeta = 0.75, freq = 2.4, blurMax = 10, rise = 26, outDur = 0.18, gold = [] } = {}) {
    const span = (w, s) => `<span style="display:inline-block;white-space:pre;${s}">${w}</span>`;
    if (t < tSwap) return oldText.split(' ').map((w) => span(w, '')).join(' ');
    const ow = oldText.split(' '), nw = newText.split(' ');
    const ko = prog(t, tSwap, tSwap + outDur);
    if (ko < 1) return ow.map((w, i) => { const k = clamp(ko * 1.3 - i * 0.04); return span(w, `opacity:${(1 - k).toFixed(3)};filter:blur(${(k * blurMax).toFixed(2)}px);transform:translateY(${(-k * rise * 0.5).toFixed(2)}px)`); }).join(' ');
    const tIn = tSwap + outDur;
    return nw.map((w, i) => {
      const s = spring(t - tIn - i * gap, zeta, freq);
      const o = clamp(s * 1.6), b = Math.max(0, 1 - s) * blurMax;
      const c = gold.includes(i) ? 'color:var(--accent);' : '';
      return span(w, `${c}opacity:${o.toFixed(3)};filter:${b > 0.05 ? `blur(${b.toFixed(2)}px)` : 'none'};transform:translateY(${((1 - s) * rise).toFixed(2)}px)`);
    }).join(' ');
  }

  // ---------------------------------------------------------------------------------------------
  // 8. Hi-DPI canvas: call once at setup. Under `--resolution portrait-4k` Chrome runs at DPR 2,
  //    but a 1080x1920 backing store is upscaled (soft dots). This doubles the backing store and
  //    scales the context so drawing code keeps using 1080x1920 coordinates.
  function hiDPICanvas(canvas, w = 1080, h = 1920) {
    const dpr = Math.max(1, Math.round(window.__HF_DEVICE_SCALE_FACTOR__ || window.devicePixelRatio || 1));
    canvas.width = w * dpr; canvas.height = h * dpr; canvas.style.width = w + 'px'; canvas.style.height = h + 'px';
    const ctx = canvas.getContext('2d'); ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, dpr };
  }
  // With hiDPICanvas, clearRect(0,0,1080,1920) still clears everything (context is scaled).
  // If you ever setTransform(1,0,0,1,0,0) inside drawing code, restore with ctx.setTransform(dpr,0,0,dpr,0,0).

  return { spring, springVel, springSettle, readLine, readLineCSS, counter, seenCount, redactK, redactBarCSS, redactLine, redactWipe,
    irisRadius, irisCSS, irisRimCSS, zoom2, zoom2DurB, zoomAboutCSS, velBlurPx, vel, dirBlurSVG, dirBlurSet, zoomBlurPx, shutterTimes, accumulate, samplesFor,
    wordSwap, hiDPICanvas };
})();
if (typeof module !== 'undefined') module.exports = HX;
