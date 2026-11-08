const { chromium } = require('playwright'); const { spawn } = require('child_process'); const fs = require('fs');
const FPS = 30;
(async () => {
  const tl = JSON.parse(fs.readFileSync(__dirname + '/tl.json')), map = JSON.parse(fs.readFileSync(__dirname + '/map.json'));
  const b = await chromium.launch({ args: ['--allow-file-access-from-files'] });
  const pg = await b.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
  pg.on('pageerror', e => console.log('pageerror', e.message));
  await pg.goto('file://' + __dirname + '/reel.html');
  await pg.evaluate(([m, t]) => window.setup(m, t), [map, tl]);
  await pg.evaluate(() => document.fonts.ready); await pg.waitForTimeout(500);
  fs.writeFileSync(__dirname + '/cues.json', JSON.stringify(await pg.evaluate(() => window.CUESOUT)));
  const mode = process.argv[2];
  if (mode === 'stills') { for (const t of JSON.parse(process.argv[3])) { await pg.evaluate(t => window.frame(t), t); await pg.waitForTimeout(60); await pg.evaluate(t => window.frame(t), t); await pg.screenshot({ path: `${__dirname}/st/${t}.jpg`, type: 'jpeg', quality: 80 }); } await b.close(); return; }
  const out = process.argv[3] || 'reel_video.mp4';
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '17', '-pix_fmt', 'yuv420p', out + '.tmp.mp4']);
  const from = +(process.argv[4] || 0), to = +(process.argv[5] || tl.total);
  for (let i = Math.round(from * FPS); i < Math.round(to * FPS); i++) {
    await pg.evaluate(t => window.frame(t), i / FPS);
    const buf = await pg.screenshot({ type: 'jpeg', quality: 92 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
  }
  ff.stdin.end(); const code = await new Promise(r => ff.on('close', r)); if (code === 0) fs.renameSync(out + '.tmp.mp4', out); console.log('done', code); await b.close();
})();
