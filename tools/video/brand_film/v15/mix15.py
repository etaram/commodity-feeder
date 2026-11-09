"""Proposed mix (scratch only). Same structure as src/mix9.py with the review's changes."""
import json, subprocess, pathlib, sys, re
P = pathlib.Path('/tmp/claude-0/-home-claude/ee7d08a5-56d0-5999-9485-3d08067cc70c/scratchpad/hf/sinder'); A = P/'assets'
OUT = P/'build_audio'
OUT.mkdir(exist_ok=True)
tl = json.load(open(P/'src/tl15.json')); SC = {s[0]: s[1:] for s in tl['scenes']}; L = tl['lines']; D = tl['total']; T5 = tl['t5']
def wt(k, pre):
    for w in L[k]['words']:
        if w[0].startswith(pre): return w[1]
    return L[k]['t']
# peak offset of each file (s from file start to its hit); cue time t = visual time - PK, the +1/30 below then puts the hit 1 frame after the picture
PK = {'notification.mp3': .23, 'ping.mp3': .33, 'pop.mp3': .12, 'whoosh.mp3': .165, 'click.mp3': .05, 'impact-bass-1.mp3': .076, 'impact-bass-2.mp3': 0.0, 'glitch-3.mp3': 1.85, 'whoosh-cinematic.mp3': 2.55}
cues = []  # (visual_time, file, gain_dB, rate)
def cue(v, f, g, r=1.0): cues.append((v - PK[f], f, g, r))
cue(wt('v1', 'lost'), 'click.mp3', -12)
cue(SC['noise'][0], 'whoosh.mp3', -12, 0.94)
for pre in ['thousand', 'live']: cue(wt('v2', pre), 'pop.mp3', -10)
for i, pre in enumerate(['portals', 'languages', 'PDFs']): cue(wt('v3', pre) - 0.3, 'whoosh.mp3', -13, [1.0, 0.94, 1.06][i])
cue(wt('v4', 'Nobody') + 0.1, 'whoosh.mp3', -12, 0.94)
cue(T5, 'whoosh-cinematic.mp3', -10); cue(T5, 'impact-bass-1.mp3', -14)
for i, s in enumerate(['army', 'rank', 'sup', 'contacts', 'price', 'odds', 'build', 'meet', 'cta']): cue(SC[s][0], 'whoosh.mp3', -12, [1.0, 0.94, 1.06][i % 3])
cue(SC['reverse'][0] + 0.1, 'whoosh.mp3', -11, 0.94)
for k in ['f1', 'f2', 'f3', 'f5']: cue(L[k]['t'] + 0.3, 'pop.mp3', -8)
cue(wt('f4', 'blueprint'), 'pop.mp3', -9); cue(L['f6']['t'] + 0.3, 'pop.mp3', -8)
for w in ['Business', 'OSINT', 'co-pilot']: cue(wt('v5', w) - 0.05, 'pop.mp3', -9)
cue(wt('f6', 'expected'), 'impact-bass-2.mp3', -18); cue(wt('f6', 'bid'), 'pop.mp3', -8); cue(wt('v11', 'one') + 0.1, 'whoosh.mp3', -12, 1.06)
q1 = L['v12']['t'] + 0.2; cue(q1, 'pop.mp3', -11); cue(q1 + 0.8, 'pop.mp3', -11); cue(L['v13']['t'] - 0.3, 'pop.mp3', -11)
cue(wt('v13', 'yes') - 0.08, 'click.mp3', -8); cue(wt('v14', 'Sinder') - 0.1, 'impact-bass-2.mp3', -20); cue(wt('v15', "let's") + 0.5, 'pop.mp3', -10)
MUSIC_START = T5 - 25.80   # Terminus: the drums land (25.80 s into the file) on the drop
MPOS = (f"adelay={int(MUSIC_START*1000)}|{int(MUSIC_START*1000)},afade=t=in:st={MUSIC_START:.3f}:d=1.5" if MUSIC_START >= 0 else f"atrim=start={-MUSIC_START:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=1.5")
cue(wt('p2', 'gone') + 0.05, 'impact-bass-2.mp3', -14); cue(wt('e1', 'see') - 0.05, 'whoosh-cinematic.mp3', -14)
for s_ in ['market', 'grind', 'ending']: cue(SC[s_][0], 'whoosh.mp3', -13, 0.94)
G = f"if(lt(t,{T5-0.2:.2f}),5,0)"
inputs = ['-i', str(A/'audio/voice15.wav'), '-i', str(A/'audio/terminus.mp3')]; filt = []; labels = []
for j, (t, f, g, r) in enumerate(cues):
    inputs += ['-i', str(A/'sfx'/f)]; n = j + 2; ms = int(max(0, t + 1/30) * 1000)
    rate = f',asetrate={int(48000*r)},aresample=48000' if r != 1.0 else ''
    filt.append(f'[{n}:a]aformat=sample_rates=48000:channel_layouts=stereo{rate},volume={g}dB,adelay={ms}|{ms}[s{j}]'); labels.append(f'[s{j}]')
filt.append(f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,{MPOS},volume=-5dB,volume='pow(10,({G})/20)':eval=frame,afade=t=out:st={D-2.4}:d=2.4,apad=whole_dur={D},atrim=0:{D},asplit=2[mus][musraw]")
filt.append('[0:a]aformat=sample_rates=48000:channel_layouts=stereo,highpass=f=90,equalizer=f=250:t=q:w=1:g=-2,equalizer=f=3500:t=q:w=1.2:g=2,acompressor=threshold=-24dB:ratio=3.5:attack=4:release=80,volume=6dB,asplit=3[vo][key][voout]')
filt.append('[mus][key]sidechaincompress=threshold=0.03:ratio=4:attack=15:release=350:knee=4,asplit=2[duck][duckout]')
filt.append(f'{"".join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest,apad=whole_dur={D},atrim=0:{D},asplit=2[sfx][sfxout]')
filt.append(f'[duck][vo][sfx]amix=inputs=3:normalize=0:duration=longest,atrim=0:{D}[sum]')
outs = []
for lab, name in [('musraw', 'music_raw'), ('voout', 'voice'), ('duckout', 'music_ducked'), ('sfxout', 'sfx'), ('sum', 'premix')]:
    outs += ['-map', f'[{lab}]', '-c:a', 'pcm_f32le', str(OUT/f'{name}.wav')]
subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error', *inputs, '-filter_complex', ';'.join(filt), *outs], check=True)
# static gain to -14 LUFS, then a true-peak-safe limiter (no gain riding)
r = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-i', str(OUT/'premix.wav'), '-af', 'ebur128', '-f', 'null', '-'], capture_output=True, text=True).stderr
I = float(re.findall(r'I:\s+(-?[\d.]+) LUFS', r)[-1]); gain = -14.0 - I
subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error', '-i', str(OUT/'premix.wav'), '-af', f'volume={gain:.2f}dB,aresample=192000,alimiter=limit=0.79:attack=2:release=60:level=disabled,aresample=48000', '-c:a', 'pcm_f32le', str(OUT/'final.wav')], check=True)
m = {'input_i': I, 'input_tp': gain}
subprocess.run(['ffmpeg', '-nostdin', '-y', '-loglevel', 'error', '-i', str(OUT/'final.wav'), '-c:a', 'aac', '-b:a', '256k', str(A/'audio/mix15.m4a')], check=True)
json.dump(cues, open(OUT/'cues.json', 'w')); print('pass1', m['input_i'], m['input_tp'], 'cues', len(cues))
