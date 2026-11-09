"""v5 mix: narration is the clock; music ("Future Business", Marco Margna, CC BY 3.0) aligned so its drop lands on 'So we built Sinder'; recorded sfx on visible actions."""
import json, subprocess, pathlib
P = pathlib.Path(__file__).resolve().parent.parent; A = P / 'assets'
tl = json.load(open(P / 'src/tl9.json')); SC = {s[0]: s[1:] for s in tl['scenes']}; L = tl['lines']; D = tl['total']
def wt(k, pre):
    for w in L[k]['words']:
        if w[0].startswith(pre): return w[1]
    return L[k]['t']
cues = []
a, b = SC['flood'][0] + 0.05, wt('v4', 'slip')
for i in range(10):
    u = i / 9; cues.append((a + (b - a) * (1 - (1 - u) ** 1.5), ['notification.mp3', 'ping.mp3'][i % 2], -12 + i * 0.5))
cues += [(wt('v1', 'lost') - 0.05, 'impact-bass-2.mp3', -6), (SC['hook'][0] + 0.02, 'glitch-3.mp3', -14)]
for pre in ['thousand', 'live']: cues.append((wt('v2', pre), 'pop.mp3', -9))
for i, pre in enumerate(['portals', 'languages', 'Endless']): cues.append((wt('v3', pre) - 0.35, ['whoosh-short.mp3', 'whoosh.mp3', 'glitch-1.mp3'][i], -11))
cues += [(tl['t5'] - 0.55, 'whoosh-short.mp3', -9), (tl['t5'] - 0.3, 'click.mp3', -7), (tl['t5'] - 0.25, 'whoosh-cinematic.mp3', -9), (tl['t5'], 'impact-bass-1.mp3', -2)]
W = ['whoosh.mp3', 'whoosh-short.mp3', 'whoosh-cinematic.mp3']
for i, s in enumerate(['army', 'rank', 'sup', 'contacts', 'reverse', 'price', 'odds', 'build', 'meet', 'yes', 'cta']): cues.append((SC[s][0] - 0.1, W[i % 3], -11))
for k in ['f1', 'f2', 'f3', 'f5']: cues.append((L[k]['t'] + 0.15, 'pop.mp3', -8))
cues += [(L['f4']['t'] + 0.3, 'whoosh-short.mp3', -10), (wt('f4', 'Get'), 'impact-bass-2.mp3', -11), (wt('f5', 'Origin'), 'pop.mp3', -9), (L['f6']['t'] + 0.1, 'pop.mp3', -8)]
cues += [(wt('v5', 'Business'), 'pop.mp3', -9), (wt('v5', 'OSINT'), 'pop.mp3', -8), (wt('v5', 'co-pilot'), 'pop.mp3', -8)]
cues += [(wt('f6', 'bid'), 'impact-bass-2.mp3', -10), (wt('v11', 'one'), 'whoosh.mp3', -12), (wt('v12', 'Ask') - 0.05, 'click-soft.mp3', -8), (wt('v12', 'Ask') + 0.7, 'click-soft.mp3', -9), (wt('v12', 'Ask') + 1.3, 'click-soft.mp3', -9),
         (wt('v13', 'yes') - 0.05, 'click.mp3', -5), (wt('v13', 'yes'), 'chime.mp3', -14), (wt('v14', 'Sinder') - 0.05, 'impact-bass-2.mp3', -9), (wt('v15', "let's") - 0.03, 'impact-bass-1.mp3', -4)]
inputs = ['-i', str(A / 'audio/voice9.wav'), '-i', str(A / 'audio/music5.mp3')]; filt = []; labels = []
for j, (t, f, g) in enumerate(cues):
    inputs += ['-i', str(A / 'sfx' / f)]; n = j + 2; ms = int(max(0, t + 1 / 30) * 1000)
    filt.append(f'[{n}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={g}dB,adelay={ms}|{ms}[s{j}]'); labels.append(f'[s{j}]')
off = tl['music_off']
filt.append(f'[1:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=start={off},asetpts=PTS-STARTPTS,afade=t=in:d=1.0,volume=-14dB,afade=t=out:st={D - 3.2}:d=3.2,apad=whole_dur={D}[mus]')
filt.append('[0:a]aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=70,equalizer=f=3500:t=q:w=1.2:g=2,acompressor=threshold=-24dB:ratio=3.5:attack=4:release=80,volume=6dB,asplit=2[vo][key]')
filt.append('[mus][key]sidechaincompress=threshold=0.03:ratio=6:attack=10:release=220[duck]')
filt.append(f'[duck][vo]{"".join(labels)}amix=inputs={2 + len(labels)}:normalize=0:duration=longest,atrim=0:{D},loudnorm=I=-14:TP=-1.5:LRA=8[out]')
subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error', *inputs, '-filter_complex', ';'.join(filt), '-map', '[out]', '-ar', '48000', '-c:a', 'aac', '-b:a', '256k', str(A / 'audio/mix9.m4a')], check=True)
print('mixed', len(cues), 'cues')
