# Original score for the Sinder vertical reel, 120 BPM, cuts on the beat. No samples.
import numpy as np, json, sys
from scipy.io import wavfile
from scipy.signal import butter, sosfilt
SR = 44100
tl = json.load(open(sys.argv[2])); SCN = {s[0]: (s[1], s[2]) for s in tl["scenes"]}; DUR = tl["total"] + 1.0
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
def clap():
    t = np.arange(int(.25 * SR)) / SR; n = sosfilt(butter(2, [1000, 5000], 'band', fs=SR, output='sos'), rng.standard_normal(len(t)))
    e = sum(np.exp(-np.maximum(0, t - d) * 40) * (t >= d) for d in (0, .01, .02)) / 3; return n * e * .9
def sub(m, dur):
    n = int(dur * SR); t = np.arange(n) / SR; f = hz(m); pump = np.minimum(1, (t % .5) / .12) ** 1.5
    return (np.sin(2 * np.pi * f * t) + .25 * np.tanh(3 * np.sin(2 * np.pi * f * 2 * t))) * pump * .32
def stab(ch, g=.07):
    n = int(.35 * SR); t = np.arange(n) / SR; s = sum(np.sign(np.sin(2 * np.pi * hz(m + 12) * t)) * .5 + np.sin(2 * np.pi * hz(m + 24) * t) for m in ch)
    return lp(s, 3000) * np.exp(-t * 9) * g
def pluck(m, g=.05):
    n = int(.25 * SR); t = np.arange(n) / SR; return lp(np.sign(np.sin(2 * np.pi * hz(m) * t)), 2600) * np.exp(-t * 16) * g
bt = .5; bar = 2.0
CH = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]; RT = [33, 29, 36, 31]
h0, h1 = SCN["hook"]; c0, c1 = SCN["chaos"]; l0 = SCN["logo"][0]; e0 = SCN["engine"][0]; q0, q1 = SCN["cta"]
# hook: impact on the first frame, drone, beat comes in at 2 s
add(impact(.9), 0); add(pad([45, 52, 57], h1 + .3, 1200, .05), 0)
t = 2.0
while t < h1 - 1e-6:
    add(kick(), t, .8); add(hat(), t + .25, .7, .6); t += bt
add(sub(33, h1 - 2.0), 2.0, .7)
# chaos: no kick, ticks speeding up, dissonance, riser, a short gap before the drop
t = c0; gap = .4
while t < c1 - .3: add(tick(), t, 1.2, .5 + .3 * np.sin(t * 3)); t += gap; gap = max(.06, gap * .88)
add(pad([56, 57, 63], c1 - c0, 1400, .05), c0); add(riser(c1 - c0 - .25, .6), c0)
# drop at the logo, full beat to the CTA
add(impact(1.2), l0); add(pad([45, 52, 57, 64, 69], 3.5, 2600, .05), l0)
t = l0; b = 0; end = q0 + 1.0
while t < end - 1e-6:
    ch, rt = CH[b % 4], RT[b % 4]
    add(stab(ch), t, 1, .5); add(pad([m + 12 for m in ch], bar + .3, 2400, .022), t)
    add(sub(rt, bar), t, 1)
    for q in range(4):
        tb = t + q * bt
        if tb >= end: break
        add(kick(), tb, .9)
        if q in (1, 3): add(clap(), tb, .5, .45)
        add(hat(), tb + .25, .9, .65)
        for s in (.125, .375): add(hat(.03, .16), tb + s, 1, .35)
        if t >= e0:
            for i in range(4): add(pluck(ch[(q + i) % 3] + 24, .045), tb + i * .125, 1, .3 + .4 * (i % 2))
    if b % 4 == 3:
        for i in range(4): add(hat(.02, .25), t + 1.5 + i * .125, 1, .5)
    t += bar; b += 1
for k in SCN:
    if k not in ("hook",): add(whoosh(.5), SCN[k][0] - .3, 1.2)
# CTA: drums cut, swell into "Let's talk", final chord
lt = tl["lets"]
add(riser(lt - (q0 + 1.0), .45), q0 + 1.0); add(impact(1.1), lt)
add(pad([45, 52, 57, 60, 64, 69], q1 - lt + 1, 3200, .065), lt)
for n, dt in ((69, .0), (72, .25), (76, .5), (81, .75)): add(piano(n, 3, .09), lt + dt, 1, .5)
st = np.stack([L, R], 1); st = sosfilt(butter(4, 14000, 'low', fs=SR, output='sos'), st, axis=0)
for d, g in ((.029, .15), (.047, .12), (.083, .09)):
    k = int(d * SR); st[k:, 0] += g * st[:-k, 1]; st[k:, 1] += g * st[:-k, 0]
st = np.tanh(st * 1.4) ; fade = np.ones(N); fo = int(1.5 * SR); fade[-fo:] = np.linspace(1, 0, fo); st *= fade[:, None]
st /= np.abs(st).max() * 1.05; wavfile.write(sys.argv[1], SR, (st * 32767).astype(np.int16)); print("score", round(DUR, 1))
