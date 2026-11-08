# Original 120 BPM promo track: intro build, drop at 6 s, sections every 3 bars, final hit at 48 s. No samples.
import numpy as np, sys, json
from scipy.io import wavfile
from scipy.signal import butter, sosfilt
SR = 44100; DUR = 51.0; BPM = 120; B = 60 / BPM
N = int(SR * DUR); L = np.zeros(N); R = np.zeros(N)
rng = np.random.default_rng(3)
ev = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else {}
def add(sig, t, gain=1.0, pan=0.5):
    s = int(t * SR); n = min(len(sig), N - s)
    if n <= 0 or s < 0: return
    L[s:s+n] += sig[:n] * gain * (1 - pan) * 2 * 0.5 + 0; R[s:s+n] += sig[:n] * gain * pan * 2 * 0.5
def hz(m): return 440 * 2 ** ((m - 69) / 12)
def env(n, a, d):
    e = np.ones(n); ai = max(1, int(a * SR)); e[:ai] = np.linspace(0, 1, ai); e *= np.exp(-np.arange(n) / SR / d); return e
def kick():
    t = np.arange(int(.35 * SR)) / SR; f = 50 + 120 * np.exp(-t * 30); return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7)
def clap():
    t = np.arange(int(.25 * SR)) / SR; n = rng.standard_normal(len(t)); sos = butter(2, [900, 3000], 'band', fs=SR, output='sos')
    return sosfilt(sos, n) * np.exp(-t * 18) * 1.2
def hat(open_=False):
    t = np.arange(int((.18 if open_ else .05) * SR)) / SR; n = rng.standard_normal(len(t)); sos = butter(2, 7000, 'high', fs=SR, output='sos')
    return sosfilt(sos, n) * np.exp(-t * (14 if open_ else 70)) * .35
def saw(f, n):
    t = np.arange(n) / SR; return sum(np.sin(2 * np.pi * f * k * t) / k for k in range(1, 9))
def stab(ch, dur):
    n = int(dur * SR); s = sum(saw(hz(m) * 2 ** (d / 1200), n) for m in ch for d in (-8, 8)) * env(n, .005, .18)
    return sosfilt(butter(2, 3200, 'low', fs=SR, output='sos'), s) * .05
def bassnote(m, dur):
    n = int(dur * SR); t = np.arange(n) / SR; f = hz(m)
    s = np.sin(2 * np.pi * f * t) + .5 * np.sign(np.sin(2 * np.pi * f * t)) * .4
    return sosfilt(butter(2, 500, 'low', fs=SR, output='sos'), s) * env(n, .005, .25) * .32
def pad(ch, dur):
    n = int(dur * SR); t = np.arange(n) / SR
    s = sum(np.sin(2 * np.pi * hz(m) * t + np.sin(2 * np.pi * .3 * t)) for m in ch); e = np.minimum(1, t / .6) * np.minimum(1, (dur - t) / .6)
    return s * e * .03
def noise_riser(dur):
    n = int(dur * SR); t = np.arange(n) / SR; x = rng.standard_normal(n)
    out = np.zeros(n); seg = int(.02 * SR)
    for i in range(0, n, seg):
        fc = 300 + 9000 * (i / n) ** 2; sos = butter(2, min(fc, 18000), 'low', fs=SR, output='sos'); out[i:i+seg] = sosfilt(sos, x[i:i+seg])
    return out * (t / dur) ** 2 * .5
def whoosh(dur=.5):
    n = int(dur * SR); t = np.arange(n) / SR; x = sosfilt(butter(2, [400, 5000], 'band', fs=SR, output='sos'), rng.standard_normal(n))
    return x * np.sin(np.pi * t / dur) ** 2 * .35
def impact():
    t = np.arange(int(1.6 * SR)) / SR; k = np.sin(2 * np.pi * np.cumsum(40 + 80 * np.exp(-t * 12)) / SR) * np.exp(-t * 3)
    n = sosfilt(butter(2, 2500, 'low', fs=SR, output='sos'), rng.standard_normal(len(t))) * np.exp(-t * 5) * .4
    return (k + n) * .9
def click():
    t = np.arange(int(.03 * SR)) / SR; return np.sin(2 * np.pi * 2200 * t) * np.exp(-t * 300) * .25
prog = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]  # Am F C G
roots = [45, 41, 36, 43]
DROP, END = 6.0, 48.0
# intro: pad + ticking hats + riser
add(pad([57, 60, 64, 69], 4.2), 0, 1); add(pad([53, 57, 60, 65], 2.2), 4.0, 1)
for i in range(int(6 / (B / 2))):
    t = i * B / 2; add(hat(), t, .5 + .5 * t / 6, .6)
add(noise_riser(2.0), 4.0, .9)
for i in range(8): add(clap(), 5.0 + i * B / 4, .15 + .1 * i, .5)   # snare roll
add(impact(), DROP, .8)
# groove
t = DROP; bar = 0
while t < END - 1e-6:
    ch = prog[bar % 4]; root = roots[bar % 4]
    for q in range(4):
        tb = t + q * B
        if tb >= END: break
        add(kick(), tb, .9); add(hat(), tb + B / 2, .7, .65); add(hat(), tb + B / 4, .25, .35); add(hat(), tb + 3 * B / 4, .25, .35)
        if q in (1, 3): add(clap(), tb, .55, .45)
        add(bassnote(root, B / 2 * .9), tb + B / 2, 1)
        if q in (0, 2): add(stab(ch, B * .45), tb + B * .5, 1, .5)
    for i in range(8):  # arp
        m = ch[i % 3] + 12 * (1 + (i // 3) % 2); n = int(.18 * SR); tt = np.arange(n) / SR
        add(np.sin(2 * np.pi * hz(m) * tt) * np.exp(-tt * 14) * .06, t + i * B / 2 + B / 4, 1, .3 + .4 * (i % 2))
    add(pad([m + 12 for m in ch], 4 * B + .3), t, .8)
    t += 4 * B; bar += 1
# sidechain duck: pump everything except kicks around each beat after the drop
for nm, arr in (('L', L), ('R', R)):
    pass
for tw in ev.get('whoosh', []): add(whoosh(.55), tw - .3, 1, .5)
for tc in ev.get('click', []): add(click(), tc, 1, .5)
for ti in ev.get('impact', []): add(impact(), ti, .6)
# ending: final hit and a reverb-like tail
add(impact(), END, 1.0); add(pad([57, 60, 64, 69, 72], 3.0), END, 1.2)
sos = butter(4, 12000, 'low', fs=SR, output='sos'); L = sosfilt(sos, L); R = sosfilt(sos, R)
for d, g in ((.023, .22), (.041, .18), (.067, .14), (.109, .1), (.17, .07)):
    k = int(d * SR); L2 = L.copy(); L[k:] += g * R[:-k]; R[k:] += g * L2[:-k]
fade = np.ones(N); fo = int(1.5 * SR); fade[-fo:] = np.linspace(1, 0, fo)
st = np.stack([L * fade, R * fade], 1); st /= np.abs(st).max() * 1.05
wavfile.write(sys.argv[1], SR, (st * 32767).astype(np.int16)); print('music ok')
