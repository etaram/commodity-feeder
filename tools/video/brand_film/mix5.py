"""v5 mix: narration is the clock; music ("Future Business", Marco Margna, CC BY 3.0) aligned so its drop lands on 'So we built Sinder'; recorded sfx on visible actions."""
import json, subprocess, pathlib
P = pathlib.Path(__file__).resolve().parent.parent; A = P / 'assets'
tl = json.load(open(P / 'src/tl5.json')); SC = {s[0]: s[1:] for s in tl['scenes']}; L = tl['lines']; D = tl['total']
def wt(k, pre):
    for w in L[k]['words']:
        if w[0].startswith(pre): return w[1]
    return L[k]['t']
cues = []
a, b = SC['fomo'][0] + 0.05, wt('v4', 'already')
for i in range(10):
    u = i / 9; cues.append((a + (b - a) * (1 - (1 - u) ** 1.5), ['notification.mp3', 'ping.mp3'][i % 2], -11 + i * 0.5))
cues += [(wt('v4', 'already') - 0.05, 'error.mp3', -9), (SC['brand'][0] + 0.02, 'whoosh-short.mp3', -8), (SC['brand'][0] + 0.38, 'click.mp3', -7),
         (SC['brand'][0] + 0.45, 'whoosh-cinematic.mp3', -8), (tl['t5'], 'impact-bass-1.mp3', -2)]
W = ['whoosh.mp3', 'whoosh-short.mp3', 'whoosh-cinematic.mp3']
for i, s in enumerate(['army', 'analyze', 'build', 'meet', 'yes', 'cta']): cues.append((SC[s][0] - 0.1, W[i % 3], -10))
for i, pre in enumerate(['Tender', 'Award', 'Trade', 'Registries', 'Sanctions', 'Prices']): cues.append((wt('v7', pre) - 0.06, ['pop.mp3', 'click-soft.mp3'][i % 2], -9))
cues += [(wt('v8', 'translate'), 'whoosh-short.mp3', -12), (wt('v8', 'score'), 'pop.mp3', -9), (wt('v8', 'lift') - 0.05, 'pop.mp3', -7)]
for pre in ['suppliers', 'price', 'Freight', 'RFQ', 'odds']: cues.append((wt('v10', pre) + 0.25, 'click-soft.mp3', -8))
cues += [(wt('v11', 'Signal'), 'whoosh.mp3', -11)]
for k, pre in [('v12', 'Ask'), ('v13', 'Supplier'), ('v13', 'contact'), ('v13', 'price')]: cues.append((wt(k, pre) + 0.1, 'click-soft.mp3', -9))
cues += [(wt('v14', 'yes') - 0.05, 'click.mp3', -5), (wt('v14', 'yes'), 'chime.mp3', -13), (wt('v15', 'Sinder') - 0.05, 'impact-bass-2.mp3', -9),
         (wt('v15', 'Lift') - 0.05, 'pop.mp3', -7), (wt('v16', "let's") - 0.03, 'impact-bass-1.mp3', -4)]
inputs = ['-i', str(A / 'audio/voice5.wav'), '-i', str(A / 'audio/music5.mp3')]; filt = []; labels = []
for j, (t, f, g) in enumerate(cues):
    inputs += ['-i', str(A / 'sfx' / f)]; n = j + 2; ms = int(max(0, t + 1 / 30) * 1000)
    filt.append(f'[{n}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={g}dB,adelay={ms}|{ms}[s{j}]'); labels.append(f'[s{j}]')
off = tl['music_off']
filt.append(f'[1:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=start={off},asetpts=PTS-STARTPTS,afade=t=in:d=1.5,volume=-1dB,afade=t=out:st={D - 3.2}:d=3.2,apad=whole_dur={D}[mus]')
filt.append('[0:a]aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=70,equalizer=f=3500:t=q:w=1.2:g=2,acompressor=threshold=-20dB:ratio=3.5:attack=4:release=80,volume=3dB,asplit=2[vo][key]')
filt.append('[mus][key]sidechaincompress=threshold=0.04:ratio=4:attack=12:release=260[duck]')
filt.append(f'[duck][vo]{"".join(labels)}amix=inputs={2 + len(labels)}:normalize=0:duration=longest,atrim=0:{D},loudnorm=I=-14:TP=-1.5:LRA=8[out]')
subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error', *inputs, '-filter_complex', ';'.join(filt), '-map', '[out]', '-ar', '48000', '-c:a', 'aac', '-b:a', '256k', str(A / 'audio/mix5.m4a')], check=True)
print('mixed', len(cues), 'cues')
