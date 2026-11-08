# Original score and sound design for the Sinder reel: 120 BPM, cues come from the compositor (cues.json). No samples.
import numpy as np, json, sys
from scipy.io import wavfile
from scipy.signal import butter, sosfilt
SR = 44100
tl = json.load(open(sys.argv[2])); SCN = {s[0]: (s[1], s[2]) for s in tl["scenes"]}; DUR = tl["total"] + 1.0; CUES = json.load(open(sys.argv[3]))
N = int(SR * DUR); L = np.zeros(N); R = np.zeros(N); rng = np.random.default_rng(11)
def hz(m): return 440 * 2 ** ((m - 69) / 12)
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
M = (np.zeros(N), np.zeros(N)); X = (np.zeros(N), np.zeros(N))   # music bus (can be muffled) and sfx bus
def put(bus, sig, t, g=1.0, pan=.5):
    s = int(t * SR); n = min(len(sig), N - s)
    if n > 0 and s >= 0: bus[0][s:s+n] += sig[:n] * g * (1 - pan); bus[1][s:s+n] += sig[:n] * g * pan
def clap():
    t = np.arange(int(.25 * SR)) / SR; n = sosfilt(butter(2, [1000, 5000], 'band', fs=SR, output='sos'), rng.standard_normal(len(t)))
    return n * sum(np.exp(-np.maximum(0, t - d) * 40) * (t >= d) for d in (0, .01, .022)) / 3 * .9
def sub(m, dur):
    n = int(dur * SR); t = np.arange(n) / SR; f = hz(m); pump = np.minimum(1, (t % .5) / .14) ** 1.6
    return (np.sin(2 * np.pi * f * t) + .22 * np.tanh(3 * np.sin(4 * np.pi * f * t))) * pump * .34
def stab(ch, g=.06):
    n = int(.4 * SR); t = np.arange(n) / SR; s = sum(np.sin(2 * np.pi * hz(m + 12) * t * (1 + .002 * d)) for m in ch for d in (-1, 1))
    return lp(s, 2600) * np.exp(-t * 7) * g
def pluck(m, g=.045):
    n = int(.22 * SR); t = np.arange(n) / SR; return lp(np.sign(np.sin(2 * np.pi * hz(m) * t)) * .6 + np.sin(2 * np.pi * hz(m) * t), 3000) * np.exp(-t * 18) * g
def blip(f0, f1, d=.12, g=.25):
    t = np.arange(int(d * SR)) / SR; return np.sin(2 * np.pi * np.cumsum(np.linspace(f0, f1, len(t))) / SR) * np.exp(-t * 30) * g
def ping(g=.25):
    t = np.arange(int(.45 * SR)) / SR; a = np.sin(2 * np.pi * 1318 * t) * np.exp(-t * 12); b = np.sin(2 * np.pi * 1760 * t) * np.exp(-np.maximum(0, t - .09) * 12) * (t > .09)
    return (a + b) * g
def thump(g=.8):
    t = np.arange(int(.5 * SR)) / SR; return (np.sin(2 * np.pi * np.cumsum(60 + 140 * np.exp(-t * 30)) / SR) * np.exp(-t * 9) + lp(rng.standard_normal(len(t)), 2500) * np.exp(-t * 25) * .5) * g
def chime(g=.2):
    s = np.zeros(int(1.2 * SR))
    for i, m in enumerate((84, 88, 91)):
        t = np.arange(len(s) - int(i * .06 * SR)) / SR; s[int(i * .06 * SR):] += np.sin(2 * np.pi * hz(m) * t) * np.exp(-t * 4)
    return s * g
bt = .5; bar = 2.0
CH = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]; RT = [33, 29, 36, 31]
h0, h1 = SCN["hook"]; p0, p1 = SCN["problem"]; b0 = SCN["brand"][0]; e0 = SCN["engine"][0]; m0, m1 = SCN["meet"]; q0, q1 = SCN["cta"]
lets = [c["t"] for c in CUES if c["type"] == "impact"][-1]
# hook: dark drone, low heartbeat from the counter onward
put(M, pad([45, 52, 57], h1 + .5, 900, .05), 0); t = 1.5
while t < h1: put(M, lp(kick(), 300), t, .55); t += 1.0
# problem: tension, clock ticks speeding up, riser into the brand drop
put(M, pad([56, 57, 63], p1 - p0 + .2, 1500, .045), p0); put(M, riser(p1 - p0 - .1, .55), p0)
t = p0; gap = .5
while t < p1 - .2: put(X, tick(), t, .9, .5 + .3 * np.sin(t * 3)); t += gap; gap = max(.07, gap * .9)
# drop: full groove from the brand to the end of the meeting (muffled during it), arps from the engine
put(M, pad([45, 52, 57, 64, 69], 4, 2800, .05), b0)
t = b0; b = 0; end = q0 + 1.0
while t < end - 1e-6:
    ch, rt = CH[b % 4], RT[b % 4]
    put(M, stab(ch), t, 1, .5); put(M, pad([m + 12 for m in ch], bar + .3, 2400, .02), t); put(M, sub(rt, bar), t)
    for q in range(4):
        tb = t + q * bt
        if tb >= end: break
        put(M, kick(), tb, .9)
        if q in (1, 3): put(M, clap(), tb, .5, .45)
        put(M, hat(), tb + .25, .9, .65)
        for s in (.125, .375): put(M, hat(.03, .15), tb + s, 1, .35)
        if t >= e0:
            for i in range(4): put(M, pluck(ch[(q + i) % 3] + 24), tb + i * .125, 1, .3 + .4 * (i % 2))
    if b % 4 == 3:
        for i in range(4): put(M, hat(.02, .25), t + 1.5 + i * .125, 1, .5)
    t += bar; b += 1
# CTA: drums out, swell into "Let's talk", final chord
put(M, riser(lets - (q0 + 1.0), .45), q0 + 1.0)
put(M, pad([45, 52, 57, 60, 64, 69], q1 - lets + 1, 3200, .065), lets)
for n, dt in ((69, 0), (72, .25), (76, .5), (81, .75)): put(M, piano(n, 3, .09), lets + dt, 1, .5)
# sound design from the compositor's cues
for c in CUES:
    t, k, g = c["t"], c["type"], c["g"]
    if k == "impact": put(X, impact(1.0), t, g)
    elif k == "drop": put(X, impact(1.0), t, g)
    elif k == "riser_short": pass
    elif k == "whoosh": put(X, whoosh(.5), t, g * 1.3)
    elif k == "wipe": put(X, whoosh(.45), t, g * 1.4, .7)
    elif k == "ping": put(X, ping(), t, g, .3 + .4 * ((t * 7) % 1))
    elif k == "live": put(X, chime(.22), t, g)
    elif k == "pop": put(X, blip(500, 1400, .1, .25), t, g, .55)
    elif k == "stamp": put(X, thump(.7), t, g)
    elif k == "tick": put(X, tick(), t, g * 1.2)
    elif k == "tap": put(X, blip(2200, 1800, .04, .3), t, g)
    elif k == "msg": put(X, blip(880, 1320, .09, .22), t, g, .45)
# muffle the music bus during the meeting
Mst = np.stack(M, 1); a, bb = int(m0 * SR), int(min(N, (m1 - .1) * SR))
seg = sosfilt(butter(2, 700, 'low', fs=SR, output='sos'), Mst[a:bb], axis=0) * 1.15
fl = int(.25 * SR); w = np.ones(bb - a); w[:fl] = np.linspace(0, 1, fl); w[-fl:] = np.linspace(1, 0, fl)
Mst[a:bb] = Mst[a:bb] * (1 - w[:, None]) + seg * w[:, None]
st = Mst + np.stack(X, 1)
st = sosfilt(butter(4, 14500, 'low', fs=SR, output='sos'), st, axis=0)
for d, g in ((.029, .14), (.047, .11), (.083, .08)):
    k = int(d * SR); st[k:, 0] += g * st[:-k, 1]; st[k:, 1] += g * st[:-k, 0]
st = np.tanh(st * 1.3); fade = np.ones(N); fo = int(1.5 * SR); fade[-fo:] = np.linspace(1, 0, fo); st *= fade[:, None]
st /= np.abs(st).max() * 1.05; wavfile.write(sys.argv[1], SR, (st * 32767).astype(np.int16)); print("score", round(DUR, 1))
