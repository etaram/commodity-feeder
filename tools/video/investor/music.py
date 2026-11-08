# Original cinematic score for the investor film. Sections follow the film's timeline (timeline.json). No samples.
import numpy as np, json, sys
from scipy.io import wavfile
from scipy.signal import butter, sosfilt
SR = 44100
tl = json.load(open(sys.argv[2])); SCN = {s[0]: (s[1], s[2]) for s in tl["scenes"]}; T = tl["times"]; DUR = tl["total"] + 1.5
N = int(SR * DUR); L = np.zeros(N); R = np.zeros(N); rng = np.random.default_rng(11)
def hz(m): return 440 * 2 ** ((m - 69) / 12)
def add(sig, t, g=1.0, pan=.5):
    s = int(t * SR); n = min(len(sig), N - s)
    if n > 0 and s >= 0: L[s:s+n] += sig[:n] * g * (1 - pan); R[s:s+n] += sig[:n] * g * pan
lp = lambda x, f: sosfilt(butter(2, f, 'low', fs=SR, output='sos'), x)
def pad(ch, dur, bright=1800, g=.05):
    n = int(dur * SR); t = np.arange(n) / SR; s = np.zeros(n)
    for m in ch:
        for d in (-7, 0, 7):
            f = hz(m) * 2 ** (d / 1200); s += sum(np.sin(2 * np.pi * f * k * t + k) / k ** 1.3 for k in range(1, 6))
    e = np.minimum(1, t / 1.2) * np.minimum(1, (dur - t) / 1.2)
    return lp(s, bright) * e * g
def piano(m, dur=2.5, g=.12):
    n = int(dur * SR); t = np.arange(n) / SR; f = hz(m)
    s = sum(np.sin(2 * np.pi * f * k * t) * np.exp(-t * (2.2 + k * 1.3)) / k for k in range(1, 7))
    return s * np.minimum(1, t / .004) * g
def kick():
    t = np.arange(int(.4 * SR)) / SR; return np.sin(2 * np.pi * np.cumsum(46 + 110 * np.exp(-t * 28)) / SR) * np.exp(-t * 6)
def hat(d=.05, g=.3):
    t = np.arange(int(d * SR)) / SR; return sosfilt(butter(2, 7500, 'high', fs=SR, output='sos'), rng.standard_normal(len(t))) * np.exp(-t * 60) * g
def snare():
    t = np.arange(int(.3 * SR)) / SR; return sosfilt(butter(2, [800, 4000], 'band', fs=SR, output='sos'), rng.standard_normal(len(t))) * np.exp(-t * 14) + np.sin(2 * np.pi * 190 * t) * np.exp(-t * 25) * .5
def bass(m, dur):
    n = int(dur * SR); t = np.arange(n) / SR; f = hz(m); return lp(np.sin(2 * np.pi * f * t) + .35 * np.sin(4 * np.pi * f * t), 400) * np.exp(-t * 2.5) * .3
def riser(dur, g=.4):
    n = int(dur * SR); t = np.arange(n) / SR; x = rng.standard_normal(n); out = np.zeros(n); seg = int(.02 * SR)
    for i in range(0, n, seg): out[i:i+seg] = lp(x[i:i+seg], 200 + 9000 * (i / n) ** 2)
    return out * (t / dur) ** 2 * g
def impact(g=1.0):
    t = np.arange(int(2.5 * SR)) / SR; k = np.sin(2 * np.pi * np.cumsum(36 + 90 * np.exp(-t * 10)) / SR) * np.exp(-t * 2.2)
    return (k + lp(rng.standard_normal(len(t)), 1800) * np.exp(-t * 4) * .35) * g
def whoosh(d=.6):
    t = np.arange(int(d * SR)) / SR; return sosfilt(butter(2, [500, 5000], 'band', fs=SR, output='sos'), rng.standard_normal(len(t))) * np.sin(np.pi * t / d) ** 2 * .25
def tick():
    t = np.arange(int(.03 * SR)) / SR; return np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 250) * .3
# progression Am F C G (vi IV I V), and a brighter C G Am F for the vision part
A = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]; RT = [45, 41, 36, 43]
B = [[48, 52, 55], [55, 59, 62], [57, 60, 64], [53, 57, 60]]; RB = [36, 43, 45, 41]
bpm = 100; bt = 60 / bpm; bar = 4 * bt
# 1. map: low drone and sparse piano
m0, m1 = SCN["map"]; add(pad([45, 52, 57], m1 + .6, 900, .06), 0)
for i, (tt, n) in enumerate([(0.6, 69), (2.0, 72), (3.4, 76), (4.8, 74), (6.2, 72), (7.6, 69)]): add(piano(n, 3, .09), tt, 1, .35 + .1 * i)
# 2. chaos: clock ticks speeding up, dissonant cluster, riser into the logo
c0, c1 = SCN["chaos"]; t = c0; gap = .5
while t < c1 - .2: add(tick(), t, 1, .5 + .3 * np.sin(t)); t += gap; gap = max(.09, gap * .9)
add(pad([56, 57, 63], c1 - c0 + .3, 1200, .045), c0); add(riser(c1 - c0, .5), c0)
# 3. logo: impact and a warm open chord
l0, l1 = SCN["logo"]; add(impact(1.0), l0); add(pad([45, 52, 57, 64, 69], l1 - l0 + 1, 2400, .055), l0)
add(piano(81, 3, .07), l0 + .4, 1, .6); add(piano(76, 3, .06), l0 + 1.0, 1, .4)
# 4. product run: driving beat at 100 BPM from 'tend' to the end of 'model'
p0 = SCN["tend"][0]; p1 = SCN["pocket"][1]; t = p0; b = 0
while t < p1 - 1e-6:
    ch, rt = (A[b % 4], RT[b % 4]) if t < SCN["model"][0] else (B[b % 4], RB[b % 4])
    for q in range(4):
        tb = t + q * bt
        if tb >= p1: break
        add(kick(), tb, .8); add(hat(), tb + bt / 2, .9, .65); add(hat(.03, .15), tb + bt / 4, 1, .35); add(hat(.03, .15), tb + 3 * bt / 4, 1, .35)
        if q in (1, 3): add(snare(), tb, .28, .45)
        add(bass(rt, bt * .9), tb, 1)
    for i in range(8): add(piano(ch[i % 3] + 12 * (1 + (i // 3) % 2), .5, .045), t + i * bt / 2, 1, .3 + .4 * (i % 2))
    add(pad([m + 12 for m in ch], bar + .4, 2200, .03), t)
    t += bar; b += 1
for k in ("tend", "sup", "price", "est", "agent", "model", "engine", "pocket"): add(whoosh(), SCN[k][0] - .3)
# 5. engine and Telegram scenes ride the same beat (section above runs to the end of 'pocket')
# 6. CTA: swell, impact on "Let's talk", final chord
q0, q1 = SCN["cta"]; add(riser(T["i12"] + 1.6 - q0, .35), q0); add(impact(.9), T["i12"] + 1.6)
add(pad([45, 52, 57, 60, 64, 69], q1 - q0 + 1.5, 3000, .06), q0)
for n, dt in ((69, 1.7), (72, 2.3), (76, 2.9), (81, 3.5)): add(piano(n, 4, .08), T["i12"] + dt, 1, .5)
for c in [SCN["tend"][0] + 1.75, SCN["sup"][0] + 1.3, SCN["sup"][0] + 2.8]: add(tick(), c, .8)
st = np.stack([L, R], 1); st = sosfilt(butter(4, 13000, 'low', fs=SR, output='sos'), st, axis=0)
for d, g in ((.029, .2), (.047, .16), (.083, .12), (.131, .09), (.21, .06)):
    k = int(d * SR); st[k:, 0] += g * st[:-k, 1]; st[k:, 1] += g * st[:-k, 0]
fade = np.ones(N); fo = int(2 * SR); fade[-fo:] = np.linspace(1, 0, fo); st *= fade[:, None]
st /= np.abs(st).max() * 1.05; wavfile.write(sys.argv[1], SR, (st * 32767).astype(np.int16)); print("score", round(DUR, 1))
