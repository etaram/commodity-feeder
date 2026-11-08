# Original ambient corporate bed: pads, arpeggio, soft pulse. Deterministic, no samples.
import numpy as np, sys
from scipy.io import wavfile
from scipy.signal import butter, sosfilt
SR = 44100; DUR = float(sys.argv[1]); BPM = 96; beat = 60 / BPM; bar = 4 * beat
N = int(SR * DUR); t = np.arange(N) / SR
L = np.zeros(N); R = np.zeros(N)
def hz(m): return 440 * 2 ** ((m - 69) / 12)
prog = [[57, 60, 64, 69], [53, 57, 60, 65], [48, 55, 60, 64], [55, 59, 62, 67]]  # Am F C G
rng = np.random.default_rng(7)
def env(n, a, r):
    e = np.ones(n); ai = int(a * SR); ri = int(r * SR)
    e[:ai] = np.linspace(0, 1, ai); e[-ri:] *= np.linspace(1, 0, ri); return e
nb = int(np.ceil(DUR / bar))
for b in range(nb):
    ch = prog[b % 4]; s = int(b * bar * SR); n = min(int(bar * 1.15 * SR), N - s)
    if n <= 0: break
    tt = np.arange(n) / SR; e = env(n, 0.9, 1.2)
    for k, m in enumerate(ch):
        for det, pan in ((-0.07, 0.3), (0.07, 0.7)):
            f = hz(m) * 2 ** (det / 12)
            w = np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt) + 0.12 * np.sin(6 * np.pi * f * tt)
            L[s:s + n] += 0.035 * w * e * (1 - pan); R[s:s + n] += 0.035 * w * e * pan
    # bass
    f = hz(ch[0] - 12); bb = np.sin(2 * np.pi * f * tt) * env(n, 0.05, 0.8) * 0.09
    L[s:s + n] += bb; R[s:s + n] += bb
    # arpeggio, 8ths, from bar 2 on
    if b >= 2:
        notes = [ch[0] + 12, ch[2] + 12, ch[1] + 12, ch[3] + 12, ch[2] + 12, ch[1] + 24, ch[3] + 12, ch[2] + 12]
        for i, m in enumerate(notes):
            s2 = s + int(i * beat / 2 * SR); n2 = min(int(0.6 * SR), N - s2)
            if n2 <= 0: continue
            t2 = np.arange(n2) / SR; f = hz(m)
            w = (np.sin(2 * np.pi * f * t2) + 0.2 * np.sin(4 * np.pi * f * t2)) * np.exp(-t2 * 6) * 0.05
            pan = 0.3 + 0.4 * ((i % 4) / 3)
            L[s2:s2 + n2] += w * (1 - pan); R[s2:s2 + n2] += w * pan
    # soft pulse on beats 1 and 3 from bar 4
    if b >= 4:
        for i in (0, 2):
            s3 = s + int(i * beat * SR); n3 = min(int(0.35 * SR), N - s3)
            if n3 <= 0: continue
            t3 = np.arange(n3) / SR; f = 55 * np.exp(-t3 * 18) + 45
            k = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t3 * 9) * 0.16
            L[s3:s3 + n3] += k; R[s3:s3 + n3] += k
sos = butter(4, 6500, 'low', fs=SR, output='sos'); L = sosfilt(sos, L); R = sosfilt(sos, R)
# simple reverb-ish: a few delayed copies
for d, g in ((0.031, .25), (0.057, .2), (0.089, .15), (0.143, .1)):
    k = int(d * SR); L[k:] += g * R[:-k]; R[k:] += g * L[:-k]
fade = np.ones(N); fi = int(2.5 * SR); fo = int(4 * SR); fade[:fi] = np.linspace(0, 1, fi); fade[-fo:] = np.linspace(1, 0, fo)
st = np.stack([L * fade, R * fade], 1); st /= np.abs(st).max() * 1.12
wavfile.write(sys.argv[2], SR, (st * 32767).astype(np.int16))
print("music", DUR)
