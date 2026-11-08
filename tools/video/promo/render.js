const { chromium } = require('playwright'); const { spawn } = require('child_process'); const fs = require('fs');
const FPS = 30, DUR = 50;
(async () => {
  const b = await chromium.launch({ args: ['--allow-file-access-from-files'] });
  const pg = await b.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  await pg.goto('file://' + __dirname + '/promo.html');
  const knob = JSON.parse(fs.readFileSync(__dirname + '/shots/est/meta.json')).meta.map(m => m && m.knob ? m.knob : null);
  await pg.evaluate(k => { window.KNOB = k; }, knob); await pg.waitForTimeout(400);
  const mode = process.argv[2];
  if (mode === 'stills') { for (const t of JSON.parse(process.argv[3])) { await pg.evaluate(t => window.frame(t), t); await pg.screenshot({ path: `${__dirname}/st_${t}.jpg`, type: 'jpeg', quality: 80 }); } await b.close(); return; }
  const [a, z] = (mode || `0-${DUR}`).split('-').map(Number); const out = process.argv[3] || 'video.mp4';
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '17', '-pix_fmt', 'yuv420p', out + '.tmp.mp4']);
  for (let i = Math.round(a * FPS); i < Math.round(z * FPS); i++) {
    await pg.evaluate(t => window.frame(t), i / FPS);
    const buf = await pg.screenshot({ type: 'jpeg', quality: 92 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
  }
  ff.stdin.end(); const code = await new Promise(r => ff.on('close', r));
  if (code === 0) fs.renameSync(out + '.tmp.mp4', out); console.log('done', code); await b.close();
})();
