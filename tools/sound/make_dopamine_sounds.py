"""Makes the ドーパミンモード sounds (assets/dopamine_sounds/*.wav): all
synthesised here from sine / saw waves and noise — nothing taken from a
real machine. 44.1 kHz, 16-bit, mono.

  kyuin    the rising キュイン every burst starts with
  slam     a low boom as the name slams in
  whoosh   the cut-in band sweeping across
  fanfare  a bright brass-ish arpeggio for the big ones
  fever    a longer fanfare with a trill for a PERFECT CLEAR
  jara     gold medals pouring (many small metal clinks)
  glint    the 普通 level's sound (its chime sounded cheap: user): a soft FM
           bell arpeggio (root, fifth, octave), slightly detuned for width,
           a little low body, in a small room's reverb; per BtB step too
  tick     a slot reel clunking to a stop
  jackpot  the reels' win: bells running up
  whistle  a firework rocket going up
  pop      a firework bursting

Each Back-to-Back in a row plays higher (user: higher with every BtB, for
the brain juice): kyuin, fanfare and a bell (chime) come in STEPS pitches,
up a major scale — kyuin_p0 … kyuin_p14 (p0: no BtB). The bell plays a
rising tune as the chain goes on.

    python tools/sound/make_dopamine_sounds.py
"""
import wave
from pathlib import Path

import numpy as np

RATE = 44100
OUT = Path(__file__).resolve().parents[2] / "assets" / "dopamine_sounds"
RNG = np.random.default_rng(20261114)


def t_of(seconds):
    return np.arange(int(RATE * seconds)) / RATE


def env(n, attack=0.005, release=0.1, total=None):
    """A linear attack, an exponential fall to the end."""
    t = np.arange(n) / RATE
    total = total or n / RATE
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    r = np.exp(-np.maximum(0, t - attack) / max(release, 1e-4))
    return a * r


def saw(freq, t):
    phase = np.cumsum(freq / RATE) if np.ndim(freq) else freq * t
    return 2 * (phase % 1.0) - 1


def sine(freq, t):
    phase = np.cumsum(2 * np.pi * freq / RATE) if np.ndim(freq) else 2 * np.pi * freq * t
    return np.sin(phase)


def lowpass(x, k):
    """A one-pole low-pass (k: 0..1, smaller = darker)."""
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc += k * (v - acc)
        y[i] = acc
    return y


def echo(x, delay=0.09, gain=0.35, times=4):
    out = np.concatenate([x, np.zeros(int(RATE * delay * times))])
    d = int(RATE * delay)
    for i in range(1, times + 1):
        out[i * d:i * d + len(x)] += x * gain ** i
    return out


# the pitch for each step of a BtB chain: up a major scale, semitones from the base
SCALE = (0, 2, 4, 5, 7, 9, 11, 12, 14, 16, 17, 19, 21, 23, 24)
STEPS = len(SCALE)


def up(step):
    return 2 ** (SCALE[step] / 12)


def kyuin(k=1.0):
    t = t_of(0.55)
    f = k * 520 * (2 ** (np.clip(t / 0.32, 0, 1) * 2.4)) * (1 + 0.02 * np.sin(2 * np.pi * 28 * t))
    x = 0.55 * sine(f, t) + 0.25 * sine(f * 2, t) + 0.12 * np.sign(sine(f, t))
    x *= env(len(t), 0.01, 0.22)
    return echo(x, 0.07, 0.3, 3)


def slam():
    t = t_of(0.6)
    f = 40 + 110 * np.exp(-t / 0.05)
    body = sine(f, t) * env(len(t), 0.002, 0.18)
    hit = lowpass(RNG.standard_normal(len(t)), 0.25) * env(len(t), 0.001, 0.03)
    return 0.9 * body + 0.5 * hit


def whoosh():
    t = t_of(0.5)
    noise = RNG.standard_normal(len(t))
    k = 0.02 + 0.5 * np.sin(np.pi * np.clip(t / 0.4, 0, 1)) ** 2
    y = np.empty_like(noise)
    acc = 0.0
    for i, v in enumerate(noise):
        acc += k[i] * (v - acc)
        y[i] = acc
    return 0.8 * y * np.sin(np.pi * np.clip(t / 0.5, 0, 1))


def brass(freq, seconds):
    t = t_of(seconds)
    vib = 1 + 0.006 * np.sin(2 * np.pi * 5.5 * t) * np.clip(t / 0.15, 0, 1)
    x = saw(freq * vib, t) + 0.5 * saw(freq * 1.003 * vib, t)
    x = lowpass(x, 0.18)
    return x * env(len(t), 0.02, seconds * 0.9)


def chord(notes, seconds, gain=0.32):
    out = np.zeros(int(RATE * seconds))
    for f in notes:
        out += brass(f, seconds)
    return gain * out / len(notes)


def chime(k=1.0):
    """A bright bell at 1046.5 Hz x k, with a sparkle on top."""
    t = t_of(0.9)
    f = 1046.5 * k
    x = sum(np.sin(2 * np.pi * f * r * t) * g * np.exp(-t / d)
            for r, g, d in ((1, 1.0, 0.45), (2.0, 0.5, 0.25), (3.0, 0.25, 0.15), (4.2, 0.15, 0.08)))
    x *= np.clip(t / 0.003, 0, 1)
    return echo(x, 0.08, 0.3, 3)


def fanfare(k=1.0):
    c, e, g, c2, e2, g2 = (k * f for f in (523.25, 659.25, 783.99, 1046.5, 1318.5, 1568.0))
    parts = [chord([c, e], 0.12), chord([e, g], 0.12), chord([g, c2], 0.12), chord([c2, e2, g2, c], 0.9, 0.45)]
    return echo(np.concatenate(parts), 0.11, 0.25, 3)


def fever():
    notes = [523.25, 659.25, 783.99, 1046.5, 783.99, 1046.5, 1318.5]
    parts = [chord([f, f * 1.5], 0.1) for f in notes]
    trill = np.concatenate([chord([1568.0, 1046.5], 0.06, 0.3), chord([1760.0, 1174.7], 0.06, 0.3)] * 5)
    end = chord([1046.5, 1318.5, 1568.0, 2093.0, 523.25], 1.3, 0.5)
    return echo(np.concatenate(parts + [trill, end]), 0.12, 0.25, 3)


def jara():
    total = 1.8
    out = np.zeros(int(RATE * (total + 0.3)))
    for _ in range(140):
        start = RNG.uniform(0, total) ** 1.4 / total ** 0.4   # (more at the start)
        n = int(RATE * 0.12)
        t = t_of(0.12)
        f0 = RNG.uniform(2600, 6200)
        x = sum(np.sin(2 * np.pi * f0 * r * t) * g for r, g in ((1, 1), (2.76, 0.5), (5.4, 0.25)))
        x *= env(n, 0.0008, RNG.uniform(0.015, 0.04)) * RNG.uniform(0.25, 0.7)
        i = int(start * RATE)
        out[i:i + n] += x[:len(out) - i]
    return out * np.clip((total + 0.3 - t_of(total + 0.3)) / 0.5, 0, 1)


def reverb(x, seconds=1.2, mix=0.35):
    """A small room: a few combs of different lengths, darkened, after the dry sound."""
    tail = np.zeros(len(x) + int(RATE * seconds))
    for delay, gain in ((0.0297, 0.78), (0.0371, 0.76), (0.0411, 0.74), (0.0437, 0.72),
                        (0.0533, 0.70), (0.0671, 0.68)):
        d = int(RATE * delay)
        y = np.zeros(len(tail))
        y[:len(x)] = x
        for i in range(d, len(y)):
            y[i] += gain * y[i - d] * 0.62
        tail += y
    tail = lowpass(tail / 6, 0.35)
    dry = np.concatenate([x, np.zeros(len(tail) - len(x))])
    return dry * (1 - mix) + tail * mix * 2.2


def fm_bell(f, seconds, index=2.4, ratio=3.5, tau=0.55):
    t = t_of(seconds)
    mod_index = index * np.exp(-t / 0.18)
    tone = np.sin(2 * np.pi * f * t + mod_index * np.sin(2 * np.pi * f * ratio * t))
    tone += 0.5 * np.sin(2 * np.pi * f * 1.004 * t + mod_index * 0.8 * np.sin(2 * np.pi * f * 1.004 * ratio * t))
    return tone * np.clip(t / 0.004, 0, 1) * np.exp(-t / tau)


def glint(k=1.0):
    f0 = 784.0 * k
    out = np.zeros(int(RATE * 1.3))
    for i, (ratio, gain) in enumerate(((1.0, 0.9), (1.5, 0.75), (2.0, 0.7))):
        note = fm_bell(f0 * ratio, 1.0, tau=0.5 - 0.08 * i) * gain
        start = int(RATE * 0.055 * i)
        out[start:start + len(note)] += note[:len(out) - start]
    t = t_of(1.3)
    out += 0.35 * np.sin(2 * np.pi * f0 / 4 * t) * np.clip(t / 0.003, 0, 1) * np.exp(-t / 0.12)   # (a little body)
    return reverb(out, 0.9, 0.3)


def tick():
    t = t_of(0.12)
    click = lowpass(RNG.standard_normal(len(t)), 0.5) * env(len(t), 0.0005, 0.012)
    thump = sine(180 * np.exp(-t / 0.03) + 90, t) * env(len(t), 0.001, 0.04)
    return 0.6 * click + 0.8 * thump


def jackpot():
    notes = [1046.5, 1318.5, 1568.0, 2093.0, 2637.0, 3136.0]
    out = np.zeros(int(RATE * 1.6))
    for i, f in enumerate(notes * 2):
        start = int(RATE * 0.055 * i)
        t = t_of(0.5)
        x = (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * f * 2.0 * t)) * np.exp(-t / 0.18)
        out[start:start + len(x)] += x[:len(out) - start] * (0.6 if i < len(notes) else 0.4)
    return echo(out, 0.09, 0.3, 3)


def whistle():
    t = t_of(0.5)
    f = 900 + 1800 * (t / 0.5) ** 1.3
    x = sine(f, t) * 0.5 + lowpass(RNG.standard_normal(len(t)), 0.3) * 0.25
    return x * np.clip(t / 0.05, 0, 1) * np.clip((0.5 - t) / 0.08, 0, 1)


def pop():
    t = t_of(1.0)
    crack = lowpass(RNG.standard_normal(len(t)), 0.6) * env(len(t), 0.001, 0.05)
    boom = sine(70 + 60 * np.exp(-t / 0.05), t) * env(len(t), 0.002, 0.25)
    crackle = np.zeros(len(t))
    for _ in range(40):
        i = int(RNG.uniform(0.08, 0.8) * RATE)
        n = int(RATE * 0.01)
        crackle[i:i + n] += RNG.standard_normal(n)[:len(t) - i] * RNG.uniform(0.1, 0.35)
    return 0.7 * crack + 0.9 * boom + 0.6 * crackle


def save(name, x):
    x = np.asarray(x, dtype=float)
    peak = np.max(np.abs(x)) or 1.0
    x = x / peak * 0.85
    fade = min(len(x), int(RATE * 0.02))
    x[-fade:] *= np.linspace(1, 0, fade)
    OUT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT / f"{name}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((x * 32767).astype("<i2").tobytes())
    print(name, round(len(x) / RATE, 2), "s")


if __name__ == "__main__":
    for name, make in (("slam", slam), ("whoosh", whoosh), ("fever", fever), ("jara", jara), ("tick", tick),
                       ("jackpot", jackpot), ("whistle", whistle), ("pop", pop)):
        save(name, make())
    for old in ("kyuin", "fanfare"):   # (one pitch each before)
        (OUT / f"{old}.wav").unlink(missing_ok=True)
    # (the base pitch only: the app makes the higher ones from it on the PC —
    # hud/dopamine.py pitched_file — a much lighter download)
    for step in (0,):
        for name, make in (("kyuin", kyuin), ("fanfare", fanfare), ("chime", chime), ("glint", glint)):
            save(f"{name}_p{step}", make(up(step)))
