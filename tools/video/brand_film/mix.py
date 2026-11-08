"""Mix: narration (clock), CC BY music bed opening on the brand reveal, Pixabay sfx on visible actions. Cue times follow film.js."""
import json, subprocess, pathlib
P = pathlib.Path(__file__).resolve().parent.parent; A = P / 'assets'
tl = json.load(open(P / 'src/tl.json')); SC = {s[0]: s[1:] for s in tl['scenes']}; W = tl['words']; D = tl['total']
def wt(k, pre):
    for w in W[k]:
        if w[0].startswith(pre): return w[1]
    return tl['vo'][k][0]
cues = []  # (time, file, gain_db)
a, b = SC['problem'][0] + 0.35, wt('r2', 'PDFs') + 0.2
for i in range(10):
    u = i / 9; t = a + (b - a) * (1 - (1 - u) ** 1.5); cues.append((t, ['notification.mp3', 'ping.mp3'][i % 2], -9 + i * 0.4))
cues += [(SC['problem'][1] - 1.15, 'whoosh-short.mp3', -6), (SC['problem'][1] - 0.32, 'click.mp3', -6)]
cues += [(SC['problem'][0] + 0.5, 'riser.mp3', -10)]  # will be placed so it ends on the brand
cues += [(SC['brand'][0], 'impact-bass-1.mp3', -3)]
whooshes = ['whoosh.mp3', 'whoosh-short.mp3', 'whoosh-cinematic.mp3']
for i, s in enumerate(['tend', 'price', 'bid', 'engine', 'meet', 'cta']): cues.append((SC[s][0] - 0.12, whooshes[i % 3], -9))
cues += [(SC['tend'][0] + 1.45, 'pop.mp3', -8)]
for pre in ['Finds', 'really', 'makes']: cues.append((wt('r5', pre) + 0.36, 'pop.mp3', -10))
cues += [(wt('r6', 'Prices') + 0.05, 'pop.mp3', -8), (wt('r7', 'dollar'), 'impact-bass-2.mp3', -8)]
for pre in ['agents', 'sources', 'countries', 'clock']: cues.append((wt('r8', pre) - 0.03, 'pop.mp3', -9))
for pre in ['Ask', 'Supplier', 'contact', 'price']: cues.append((wt('r9', pre) + 0.16, 'click-soft.mp3', -8))
cues += [(SC['meet'][1] - 1.0, 'click.mp3', -5), (wt('r10', 'Let'), 'impact-bass-1.mp3', -4)]
riser = 4.0  # riser.mp3 length check below
dur = lambda f: float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(f)]))
inputs = ['-i', str(A / 'audio/voice.wav'), '-i', str(A / 'audio/music.mp3')]; filt = []; labels = []
for j, (t, f, g) in enumerate(cues):
    if f == 'riser.mp3': t = SC['brand'][0] - dur(A / 'sfx' / f) + 0.05
    inputs += ['-i', str(A / 'sfx' / f)]; n = j + 2
    filt.append(f'[{n}:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={g}dB,adelay={int(max(0, t + 1 / 30) * 1000)}|{int(max(0, t + 1 / 30) * 1000)}[s{j}]'); labels.append(f'[s{j}]')
m0 = SC['brand'][0]; off = 7.9
filt.append(f'[1:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=start={off},asetpts=PTS-STARTPTS,afade=t=in:d=0.08,volume=-4dB,afade=t=out:st={D - m0 - 3.0}:d=3.0,adelay={int(m0 * 1000)}|{int(m0 * 1000)},apad=whole_dur={D}[mus]')
filt.append('[0:a]aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=70,acompressor=threshold=-20dB:ratio=3:attack=5:release=90,volume=2dB,asplit=2[vo][key]')
filt.append('[mus][key]sidechaincompress=threshold=0.03:ratio=7:attack=15:release=320[duck]')
filt.append(f'[duck][vo]{"".join(labels)}amix=inputs={2 + len(labels)}:normalize=0:duration=longest,atrim=0:{D},loudnorm=I=-14:TP=-1.5:LRA=9[out]')
cmd = ['ffmpeg', '-nostdin', '-y', '-loglevel', 'error', *inputs, '-filter_complex', ';'.join(filt), '-map', '[out]', '-ar', '48000', '-c:a', 'aac', '-b:a', '256k', str(A / 'audio/mix.m4a')]
subprocess.run(cmd, check=True); print('mixed', len(cues), 'cues')
