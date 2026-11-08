const { chromium } = require('playwright'); const { spawn } = require('child_process'); const fs = require('fs');
const FPS = 30;
(async () => {
  const vo = JSON.parse(fs.readFileSync(__dirname + '/vo.json')), map = JSON.parse(fs.readFileSync(__dirname + '/map.json'));
  const knob = JSON.parse(fs.readFileSync('/tmp/claude-0/-home-claude/ee7d08a5-56d0-5999-9485-3d08067cc70c/scratchpad/promo/shots/est/meta.json')).meta.map(m => m && m.knob ? m.knob : null);
  const b = await chromium.launch({ args: ['--allow-file-access-from-files'] });
  const pg = await b.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  await pg.goto('file://' + __dirname + '/film.html');
  await pg.evaluate(([m, v, k]) => { window.KNOB = k; window.setup(m, v); }, [map, vo, knob]);
  await pg.evaluate(() => document.fonts.ready); await pg.waitForTimeout(500);
  const info = await pg.evaluate(() => ({ total: window.TOTAL, times: window.TIMES, scenes: window.SCENES }));
  fs.writeFileSync(__dirname + '/timeline.json', JSON.stringify(info));
  const mode = process.argv[2];
  if (mode === 'info') { console.log(JSON.stringify(info)); await b.close(); return; }
  if (mode === 'stills') { for (const t of JSON.parse(process.argv[3])) { await pg.evaluate(t => window.frame(t), t); await pg.screenshot({ path: `${__dirname}/st_${t}.jpg`, type: 'jpeg', quality: 80 }); } await b.close(); return; }
  const out = process.argv[3] || 'film_video.mp4';
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '17', '-pix_fmt', 'yuv420p', out + '.tmp.mp4']);
  for (let i = 0; i < Math.round(info.total * FPS); i++) {
    await pg.evaluate(t => window.frame(t), i / FPS);
    const buf = await pg.screenshot({ type: 'jpeg', quality: 92 });
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
  }
  ff.stdin.end(); const code = await new Promise(r => ff.on('close', r)); if (code === 0) fs.renameSync(out + '.tmp.mp4', out); console.log('done', code); await b.close();
})();
