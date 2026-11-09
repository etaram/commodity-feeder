"""v14 timeline: place each narration line (Christopher, tempo 1.06) with gaps, absolute word times, scene starts from lines."""
import json, subprocess, pathlib
P = pathlib.Path('/tmp/claude-0/-home-claude/ee7d08a5-56d0-5999-9485-3d08067cc70c/scratchpad/hf/sinder'); V = pathlib.Path('/tmp/claude-0/-home-claude/ee7d08a5-56d0-5999-9485-3d08067cc70c/scratchpad/v15/pages/en-US-ChristopherNeural')
TEMPO = 1.09
W = json.load(open(V/'words.json')); SCR = json.load(open('/home/claude/commodity-feeder/tools/video/film15.json')); order = [k for k, _ in SCR]
for k, text in SCR:  # keep the script's punctuation on each word (captions break on it)
    toks = text.split()
    if len(toks) == len(W[k]): W[k] = [[tk, x[1], x[2]] for tk, x in zip(toks, W[k])]
    else: print('token mismatch', k, len(toks), len(W[k]), [x[0] for x in W[k]])
GAP = {'p1': 0.55, 'p2': 0.4, 'e1': 0.55, 'v1': 0.55, 'v2': 0.45, 'v3': 0.3, 'v4': 0.35, 'v5': 0.95, 'v6': 0.45, 'f1': 0.35, 'f2': 0.35, 'f3': 0.35, 'f4': 0.35, 'f5': 0.35, 'f6': 0.35, 'v11': 0.4, 'v12': 0.35, 'v13': 0.3, 'v14': 0.6, 'v15': 0.4}
t = 0.0; lines = {}; parts = []
for k in order:
    w = W[k]; a = max(0, w[0][1] - 0.04); b = w[-1][1] + w[-1][2] + 0.08
    t += GAP[k]; st = t; d = (b - a) / TEMPO
    lines[k] = {'t': round(st, 3), 'd': round(d, 3), 'words': [[x[0], round(st + (x[1] - a) / TEMPO, 3), round(x[2] / TEMPO, 3)] for x in w]}
    parts.append((k, a, b, st)); t = st + d
total = round(t + 2.6, 3); T5 = lines['v5']['t']
L = lambda k: lines[k]['t']
sc = [('hook', 0), ('market', L('p1') - 0.3), ('noise', L('v2') - 0.35), ('chaos', L('v3') - 0.4), ('grind', L('p2') - 0.35), ('flood', L('v4') - 0.45), ('reveal', T5), ('army', L('v6') - 0.45), ('rank', L('f1') - 0.12),
      ('sup', L('f2') - 0.08), ('contacts', L('f3') - 0.45), ('reverse', L('f4') - 0.55), ('price', L('f5') - 0.12), ('odds', L('f6') - 0.4), ('build', L('v11') - 0.6),
      ('meet', L('v12') - 0.35), ('yes', L('v13') - 0.15), ('ending', L('e1') - 0.3), ('cta', L('v14') - 0.5)]
scenes = [[n, round(s, 3), round(sc[i + 1][1] if i + 1 < len(sc) else total, 3)] for i, (n, s) in enumerate(sc)]
json.dump({'total': total, 'beat': 0.5, 't5': T5, 'music_off': round(T5 - 25.80, 3), 'scenes': scenes, 'lines': lines}, open(P/'src/tl15.json', 'w'))
# narration track
inp = []; flt = []; lab = []
for j, (k, a, b, st) in enumerate(parts):
    inp += ['-i', str(V/f'{k}.mp3')]; ms = int(st * 1000)
    flt.append(f'[{j}:a]aformat=sample_rates=48000:channel_layouts=mono,atrim={a}:{b},asetpts=PTS-STARTPTS,atempo={TEMPO},afade=t=in:d=0.02,adelay={ms}[a{j}]'); lab.append(f'[a{j}]')
flt.append(f'{"".join(lab)}amix=inputs={len(lab)}:normalize=0,apad=whole_dur={total},atrim=0:{total}[o]')
subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error', *inp, '-filter_complex', ';'.join(flt), '-map', '[o]', '-c:a', 'pcm_s16le', str(P/'assets/audio/voice15.wav')], check=True)
print('total', total, 'T5', T5, [(s[0], s[1]) for s in scenes])
