"""Makes the announcer's lines (assets/announcer/<voice>/*.wav) with Kokoro
(https://huggingface.co/hexgrad/Kokoro-82M, Apache-2.0): a free text-to-
speech model, run here once — the app only plays the files. The user
picked two voices: af_heart (American, female) and am_adam (American,
male).

Each line is cut tight (no silence before it: no lag) and made loud the
same way as hud/dopamine.py shape_voice. The lines are the ones
hud/dopamine.py phrases() lists (kept the same here: this runs in Kokoro's
own Python, without the app's).

Needs Kokoro and PyTorch (not the app's requirements), e.g. in a separate venv:
    pip install torch --index-url https://download.pytorch.org/whl/cpu
    pip install kokoro soundfile
    python tools/sound/make_announcer.py
"""
import re
import wave
from pathlib import Path

import numpy as np
from kokoro import KPipeline

OUT = Path(__file__).resolve().parents[2] / "assets" / "announcer"
VOICES = ("af_heart", "am_adam")
SPEED = 1.1
RATE = 24000
NAMES = ("T-Spin Single", "T-Spin Double", "T-Spin Triple", "T-Spin Mini", "T-Spin Mini Double", "Tetris",
         "Perfect Clear")
DRIVE = 1.8   # (hud/dopamine.py ANNOUNCE_DRIVE)


def lines():
    out = []
    for name in NAMES:
        out.append(name + "!")
        if name != "Perfect Clear":
            out.append("Back to Back, " + name + "!")
    return out


def slug(text):
    """The file name for a line (hud/dopamine.py line_file)."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def shape(x):
    x = np.asarray(x, dtype=float)
    loud = np.abs(x) > np.abs(x).max() * 0.03
    first, last = int(np.argmax(loud)), len(x) - int(np.argmax(loud[::-1]))
    x = x[max(0, first - int(RATE * 0.005)):min(len(x), last + int(RATE * 0.04))]
    x = x / np.abs(x).max()
    return np.tanh(DRIVE * x) / np.tanh(DRIVE) * 0.97


if __name__ == "__main__":
    pipe = KPipeline(lang_code="a")
    for voice in VOICES:
        folder = OUT / voice
        folder.mkdir(parents=True, exist_ok=True)
        for text in lines():
            audio = np.concatenate([np.asarray(a) for _, _, a in pipe(text, voice=voice, speed=SPEED)])
            y = shape(audio)
            with wave.open(str(folder / f"{slug(text)}.wav"), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes((y * 32767).astype("<i2").tobytes())
            print(voice, text, round(len(y) / RATE, 2), "s")
