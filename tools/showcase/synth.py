#!/usr/bin/env python3
"""A royalty-free demo track for the showcase recording: wide spectrum so cava and the
desk visualisers have something to dance to. Pure numpy, deterministic (seeded).

    python3 tools/showcase/synth.py OUT.wav     ~83 s, 44.1 kHz stereo, ~3 s to render

Written from scratch here (no samples, no third-party melody): the audio is this repo's.
tools/showcase/stage.sh renders it into the stage's run dir; audio is never committed."""
import sys, wave
import numpy as np

SR = 44100
BPM = 112
BEAT = 60 / BPM
BAR = 4 * BEAT
rng = np.random.default_rng(7)

PROG = [("A", [57, 60, 64]), ("F", [53, 57, 60]), ("C", [48, 52, 55]), ("G", [55, 59, 62])]
ROOT = {"A": 45, "F": 41, "C": 36, "G": 43}
# sections: (bars, layers)
SECTIONS = [
    (4, {"pad", "pluck"}),
    (4, {"pad", "pluck", "hat", "bass"}),
    (8, {"pad", "pluck", "hat", "bass", "kick", "clap"}),
    (8, {"pad", "pluck", "hat", "bass", "kick", "clap", "lead"}),
    (4, {"pad", "lead"}),
    (8, {"pad", "pluck", "hat", "bass", "kick", "clap", "lead"}),
    (2, {"pad"}),
]
NBARS = sum(b for b, _ in SECTIONS)
N = int((NBARS * BAR + 2.0) * SR)
out = np.zeros((N, 2))


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def env(n, a=0.005, d=0.2, s=0.0, r=0.0):
    t = np.arange(n) / SR
    e = np.minimum(1.0, t / max(a, 1e-4))
    e *= np.where(t < a, 1.0, s + (1 - s) * np.exp(-(t - a) / max(d, 1e-4)))
    if r > 0:
        tail = int(r * SR)
        if tail < n:
            e[-tail:] *= np.linspace(1, 0, tail)
    return e


def add(sig, start, pan=0.0, gain=1.0):
    i = int(start * SR)
    j = min(N, i + len(sig))
    if j <= i:
        return
    l = np.cos((pan + 1) * np.pi / 4) * gain
    r = np.sin((pan + 1) * np.pi / 4) * gain
    out[i:j, 0] += sig[: j - i] * l
    out[i:j, 1] += sig[: j - i] * r


def saw(f, n, harmonics=24):
    t = np.arange(n) / SR
    s = np.zeros(n)
    for k in range(1, harmonics + 1):
        if f * k > SR / 2.2:
            break
        s += np.sin(2 * np.pi * f * k * t) / k
    return s * 0.55


def pluck(f, dur, bright=0.996):
    p = max(2, int(SR / f))
    n = int(dur * SR)
    buf = rng.uniform(-1, 1, p)
    buf = buf - buf.mean()
    res = np.empty(n)
    pos = 0
    while pos < n:
        k = min(p, n - pos)
        res[pos:pos + k] = buf[:k]
        nxt = 0.5 * (buf + np.roll(buf, -1)) * bright
        buf = nxt
        pos += k
    return res * env(n, a=0.001, d=dur, s=1.0, r=0.05)


def kick(n=int(0.45 * SR)):
    t = np.arange(n) / SR
    f = 48 + 110 * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t * 7) * 1.1


def noise_hp(n, k=6):
    x = rng.uniform(-1, 1, n)
    lp = np.convolve(x, np.ones(k) / k, mode="same")
    return x - lp


def clap(n=int(0.22 * SR)):
    x = noise_hp(n, 3)
    t = np.arange(n) / SR
    e = np.exp(-t * 22) + 0.6 * np.exp(-np.maximum(t - 0.012, 0) * 30) * (t > 0.012)
    return x * e * 0.55


def hat(open_=False):
    n = int((0.18 if open_ else 0.05) * SR)
    t = np.arange(n) / SR
    return noise_hp(n, 2) * np.exp(-t * (18 if open_ else 70)) * 0.32


LEAD = [76, None, 72, 74, 76, None, 79, 77, 76, None, 72, None, 71, 72, 74, None]

bar = 0
for nbars, layers in SECTIONS:
    for b in range(nbars):
        t0 = bar * BAR
        name, chord = PROG[bar % 4]
        if "pad" in layers:
            for m in chord:
                for det in (-0.07, 0.07):
                    s = saw(hz(m) * 2 ** (det / 12), int(BAR * SR) + int(0.3 * SR), 10)
                    s *= env(len(s), a=0.35, d=3.0, s=0.7, r=0.3)
                    add(s, t0, pan=det * 8, gain=0.045)
        if "pluck" in layers:
            arp = chord + [chord[0] + 12, chord[1] + 12, chord[2] + 12]
            for k in range(16):
                m = arp[(k * 5 + bar) % len(arp)] + 12
                add(pluck(hz(m), 0.45), t0 + k * BEAT / 4, pan=0.5 * np.sin(k), gain=0.16)
        if "bass" in layers:
            for k in range(8):
                m = ROOT[name] + (12 if k % 4 == 3 else 0)
                n = int(BEAT / 2 * SR * 0.9)
                s = (np.sin(2 * np.pi * hz(m) * np.arange(n) / SR) + 0.35 * saw(hz(m), n, 6))
                add(s * env(n, a=0.004, d=0.18, s=0.4, r=0.03), t0 + k * BEAT / 2, gain=0.32)
        if "kick" in layers:
            for k in range(4):
                add(kick(), t0 + k * BEAT, gain=0.7)
        if "clap" in layers:
            for k in (1, 3):
                add(clap(), t0 + k * BEAT, pan=0.05, gain=0.8)
        if "hat" in layers:
            for k in range(8):
                add(hat(open_=(k % 2 == 1 and k % 4 == 3)), t0 + k * BEAT / 2 + (0.012 if k % 2 else 0),
                    pan=0.3, gain=1.0)
        if "lead" in layers:
            for k in range(16):
                m = LEAD[(k + (bar % 2) * 8) % 16]
                if m is None or k % 2:
                    continue
                n = int(BEAT * 0.95 * SR)
                f = hz(m)
                t = np.arange(n) / SR
                vib = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * t) * (t > 0.15)
                ph = 2 * np.pi * np.cumsum(f * vib) / SR
                s = np.sin(ph) + 0.3 * np.sin(2 * ph) + 0.12 * np.sin(3 * ph)
                add(s * env(n, a=0.02, d=0.6, s=0.5, r=0.08), t0 + k * BEAT / 2, pan=-0.2, gain=0.09)
        bar += 1

# sidechain-ish pump on everything but the kick is skipped; simple master: soft clip + normalise
out = np.tanh(out * 1.4)
out /= np.max(np.abs(out)) + 1e-9
out *= 0.89
pcm = (out * 32767).astype("<i2")
with wave.open(sys.argv[1], "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print(f"{NBARS} bars, {N / SR:.1f} s")
