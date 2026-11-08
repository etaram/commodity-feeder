// node render.js [stillsOnly] : renders each scene to scenes/<id>.mp4 (1920x1080, 30 fps), or stills at chosen times
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const fs = require('fs');
const LEAD = 0.6, TAIL = 1.0, FPS = 30;
const dur = Object.fromEntries(fs.readFileSync('dur.txt', 'utf8').trim().split('\n').map(l => { const [k, v] = l.split(' '); return [k, +v + LEAD + TAIL]; }));
(async () => {
  const b = await chromium.launch();
  const pg = await b.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  await pg.goto('file://' + __dirname + '/video.html');
  await pg.evaluate(d => window.setup(d), dur);
  await pg.waitForTimeout(500);
  const mode = process.argv[2];
  if (mode === 'stills') {
    const list = JSON.parse(process.argv[3]);
    for (const [id, t] of list) { await pg.evaluate(([i, tt]) => window.frame(i, tt), [id, t]); await pg.screenshot({ path: `still_${id}_${t}.jpg`, type: 'jpeg', quality: 85 }); }
    await b.close(); return;
  }
  fs.mkdirSync('scenes', { recursive: true });
  const ids = mode ? mode.split(',') : Object.keys(dur);
  for (const id of ids) {
    const n = Math.round(dur[id] * FPS);
    const tmp = `scenes/${id}.tmp.mp4`;
    const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', String(FPS), tmp]);
    for (let i = 0; i < n; i++) {
      await pg.evaluate(([i2, tt]) => window.frame(i2, tt), [id, i / FPS]);
      const buf = await pg.screenshot({ type: 'jpeg', quality: 92 });
      if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    }
    ff.stdin.end();
    const code = await new Promise(r => ff.on('close', r));
    if (code === 0) fs.renameSync(tmp, `scenes/${id}.mp4`); else console.error('ffmpeg failed', id);
    console.log(id, n, 'frames');
  }
  await b.close();
})();
