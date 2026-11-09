import json, pathlib
P = pathlib.Path(__file__).resolve().parent.parent
tl = json.load(open(P / 'src/tl15.json')); mp = json.load(open(P / 'src/map.json'))
icons = {n: json.load(open(P / f'assets/icons/{n}.json')) for n in ['whatsapp', 'gmail', 'telegram']}
D = tl['total']
imgs = ''.join(f'<img src="assets/ui/{i:04d}.jpg" style="opacity:0">' for i in range(79))
fonts = "@font-face{font-family:DV;src:url(assets/fonts/DejaVuSans.ttf)}@font-face{font-family:Plex;font-weight:100 900;src:url(assets/fonts/DejaVuSans.ttf);unicode-range:U+0400-04FF,U+0590-05FF,U+0600-06FF}" + ''.join(f"@font-face{{font-family:{fam};font-weight:{w};src:url(assets/fonts/{f}.woff2)}}" for fam, w, f in [
    ('Barlow', 600, 'barlow-condensed-latin-600-normal'), ('Barlow', 700, 'barlow-condensed-latin-700-normal'),
    ('Inter', 600, 'inter-latin-600-normal'), ('Inter', 700, 'inter-latin-700-normal'), ('Inter', 800, 'inter-latin-800-normal'), ('Plex', 400, 'ibm-plex-sans-latin-400-normal'), ('Plex', 500, 'ibm-plex-sans-latin-500-normal'), ('Plex', 600, 'ibm-plex-sans-latin-600-normal'), ('Plex', 700, 'ibm-plex-sans-latin-700-normal')])
html = f'''<!doctype html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=1080, height=1920">
<script src="assets/gsap.min.js"></script>
<style>{fonts}
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1080px;height:1920px;overflow:hidden;background:#0B1324}}
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;font-family:Plex,sans-serif;color:#fff;--accent:#F0CF7A}}
.abs{{position:absolute}}
#ground{{position:absolute;inset:0}}
#map{{position:absolute;inset:0}}
#phone{{position:absolute;left:0;top:0;width:704px;height:1490px;border-radius:96px;background:#0A0C10;padding:14px;transform-origin:50% 50%;box-shadow:0 40px 90px rgba(0,0,0,.35),inset 0 0 0 2px #2B3140}}
#screen{{position:relative;width:676px;height:1462px;border-radius:82px;overflow:hidden;background:#0B1324}}
#uiwrap img{{position:absolute;left:0;top:0;width:676px}}
#island{{position:absolute;left:50%;top:22px;width:190px;height:54px;border-radius:27px;background:#000;transform:translateX(-50%);z-index:5}}
.ai{{border-radius:22%;display:flex;align-items:center;justify-content:center;flex:none}}
.kv{{flex:1;background:#18244A;border:2px solid #24356A;border-radius:22px;padding:18px 20px}}
.kv b{{display:block;font:700 54px/1 Barlow;color:#fff}} .kv span{{display:block;font:500 26px Plex;color:#9FB1D3;margin-top:6px}}
.num{{font-variant-numeric:tabular-nums}}
#subs{{position:absolute;left:60px;right:60px;top:1755px;display:flex;justify-content:center}}
.sub{{background:rgba(5,8,15,.62);border-radius:16px;padding:12px 24px;font:600 40px/1.25 Inter;letter-spacing:-0.01em;color:#fff;text-align:center;max-width:960px}}
#black{{position:absolute;inset:0;background:#000;opacity:0}}
</style></head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-duration="{D}" data-width="1080" data-height="1920" data-fps="30">
  <div id="stage" class="clip" data-start="0" data-duration="{D}" data-track-index="0" style="position:absolute;inset:0" data-layout-allow-overflow data-layout-allow-overlap>
  <div id="ground"></div>
  <div id="media" class="abs" style="inset:0;overflow:hidden"><img id="m_iss_a" class="bgm" src="assets/media/iss_a.jpg" data-w="3200" data-h="2130" style="position:absolute;left:0;top:0;height:1920px;opacity:0"><img id="m_black_marble" class="bgm" src="assets/media/black_marble.jpg" data-w="3200" data-h="2130" style="position:absolute;left:0;top:0;height:1920px;opacity:0"><img id="m_iss_c" class="bgm" src="assets/media/iss_c.jpg" data-w="3200" data-h="2190" style="position:absolute;left:0;top:0;height:1920px;opacity:0"><img id="m_port_cranes" class="bgm" src="assets/media/port_cranes.jpg" data-w="3200" data-h="2134" style="position:absolute;left:0;top:0;height:1920px;opacity:0"><img id="m_port_reykjavik" class="bgm" src="assets/media/port_reykjavik.jpg" data-w="3200" data-h="2292" style="position:absolute;left:0;top:0;height:1920px;opacity:0"><img id="m_port_miami" class="bgm" src="assets/media/port_miami.jpg" data-w="3040" data-h="2008" style="position:absolute;left:0;top:0;height:1920px;opacity:0"><img id="m_ship_cmacgm" class="bgm" src="assets/media/ship_cmacgm.jpg" data-w="3200" data-h="1462" style="position:absolute;left:0;top:0;height:1920px;opacity:0"><img id="m_iss_d" class="bgm" src="assets/media/iss_d.jpg" data-w="3200" data-h="2190" style="position:absolute;left:0;top:0;height:1920px;opacity:0"><div id="tint" class="abs" style="inset:0;opacity:0"></div></div>
  <canvas id="map" width="1080" height="1920"></canvas>
  <div id="phone"><div id="screen"><div id="uiwrap" class="abs" style="inset:0">{imgs}</div><div id="scrhtml" class="abs" style="inset:0"></div><div id="island"></div></div></div>
  <div id="fx" class="abs" style="inset:0"></div>
  <div id="subs"></div>
  <div id="black"></div>
 </div>
 <audio id="mix" class="clip" src="assets/audio/mix15.m4a" data-start="0" data-duration="{D}" data-track-index="1"></audio>
</div>
<script>window.TL={json.dumps(tl)};window.MAP={json.dumps(mp)};window.ICON={json.dumps(icons)};</script>
<script>{open(P / 'src/head14.js').read()}
{open(P / 'src/scenes15.js').read()}</script>
</body></html>'''
open(P / 'index.html', 'w').write(html); print('ok', len(html))
