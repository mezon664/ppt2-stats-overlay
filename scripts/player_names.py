"""The players' names, read off the name plates under the boards (for the
comments: "{me}ナイス", "{rival}つよい" — user's request).

Windows' own text recognition (the same as scripts/rating.py; Japanese
first), on its own thread so the server never waits for it. Each plate is
read at three sizes, once a second while a match is on, until a name is
settled: the same text read SAME_READS times. Before that, nothing (no
guessed name on screen). The user chose this knowing it misreads now and
then (on the recordings: 夕映え read as タ映え every time, めぞん now and
then as めそん). Kept for the set: read again only when the match's
players may have changed (a new match after the menus).

Read from the letters' lack of colour (prepare): a light-blue glow passes
behind the plate and tints a letter, so by brightness alone ぞ went missing
(live, every time: めぞん read as めん — user); the plate's own top and bottom
lines are left out of the crop too. On the live frames in debug_frames this
read めぞん 18 times out of 19 (was めん every time).
"""
import asyncio
import logging
import queue
import threading
import time
from collections import Counter

import cv2
import numpy as np

log = logging.getLogger(__name__)

REFERENCE_W = 1232
# the name plates (reference 1232 x 692), the text inside them (between the plate's lines)
PLATES = {"left": (165, 634, 470, 653), "right": (762, 634, 1066, 653)}
SCALES = (2, 3, 4)
SAME_READS = 3        # the same text this many times: that's the name
READ_EVERY_S = 1.0
MAX_LEN = 16


def clean(text):
    """A reading tidied: spaces out, at most MAX_LEN characters, the
    recognizer's usual slips put right (fix); "" if it's no name."""
    text = "".join(str(text or "").split())
    text = "".join(c for c in text if c.isprintable() and c not in "{}")
    if not text or len(text) > MAX_LEN:
        return ""
    return fix(text)


def _kanji(c):
    return "\u4e00" <= c <= "\u9fff"


def fix(text):
    """Slips Windows' recognizer makes every time on these plates (the
    recordings): 夕 read as タ before a kanji (夕映え -> タ映え), and the
    digit after CPU read as a letter (CPU1 -> CPUI)."""
    import re
    out = []
    for i, c in enumerate(text):
        if c == "タ" and i + 1 < len(text) and _kanji(text[i + 1]) and (i == 0 or not ("\u30a0" <= text[i - 1] <= "\u30ff")):
            c = "夕"
        out.append(c)
    text = "".join(out)
    return re.sub(r"^(CPU)[Il|]$", r"\g<1>1", text)


def settle(readings):
    """The name from the readings so far, or None."""
    counts = Counter(r for r in readings if r)
    if not counts:
        return None
    text, n = counts.most_common(1)[0]
    return text if n >= SAME_READS else None


def prepare(crop, scale):
    """The plate for the recognizer: dark letters on white, from how little
    colour each pixel has (the letters are white, the plate blue — and a
    glow behind a letter brightens it but stays blue), stretched to full
    contrast, `scale` times the size, a white margin round it."""
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)[..., 1].astype(np.float32)
    lo, hi = np.percentile(g, 2), np.percentile(g, 98)
    g = np.clip((g - lo) * 255 / max(1.0, hi - lo), 0, 255).astype(np.uint8)
    g = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return cv2.copyMakeBorder(g, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)


def plate(frame, side):
    k = frame.shape[1] / REFERENCE_W
    x1, y1, x2, y2 = (int(round(v * k)) for v in PLATES[side])
    return frame[y1:y2, x1:x2]


class NameReader:
    """state["names"]: {"left": …, "right": …} once each is settled."""

    def __init__(self):
        self.names = {}
        self._readings = {"left": [], "right": []}
        self._match = None
        self._next = 0.0
        self._jobs = queue.Queue(maxsize=1)
        self._engine = None
        self._thread = None
        self._lock = threading.Lock()

    def update(self, state, frame, now=None):
        """Called with each state (the server's loop): hands a frame over to be read now and then."""
        now = time.monotonic() if now is None else now
        st = state or {}
        match = st.get("match_start_t")
        if match != self._match:
            self._match = match
            # (the names stay while the next match goes on: a set's players don't change)
        if st.get("match_screen") is not True or frame is None:
            if st.get("match_screen") is False:   # back in the menus: next time, read afresh
                with self._lock:
                    self.names, self._readings = {}, {"left": [], "right": []}
            return dict(self.names)
        with self._lock:
            done = all(side in self.names for side in PLATES)
        if not done and now >= self._next:
            self._next = now + READ_EVERY_S
            self._start()
            try:
                self._jobs.put_nowait({side: plate(frame, side).copy() for side in PLATES})
            except queue.Full:
                pass
        return dict(self.names)

    def _start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="player-names", daemon=True)
            self._thread.start()

    def _run(self):
        while True:
            crops = self._jobs.get()
            for side, crop in crops.items():
                with self._lock:
                    if side in self.names:
                        continue
                for text in self.read(crop):
                    with self._lock:
                        self._readings[side].append(text)
                        name = settle(self._readings[side])
                        if name and side not in self.names:
                            self.names[side] = name
                            log.info("[%s] player name read: %s", side, name)

    def _ocr(self):
        if self._engine is None:
            from winrt.windows.globalization import Language
            from winrt.windows.media.ocr import OcrEngine
            engine = None
            try:
                engine = OcrEngine.try_create_from_language(Language("ja"))
            except Exception:
                engine = None
            self._engine = engine or OcrEngine.try_create_from_user_profile_languages() or False
        return self._engine or None

    def read(self, crop):
        """The plate read at each size (tidied; empty ones left out)."""
        import rating
        engine = self._ocr()
        if engine is None or crop is None or not crop.size:
            return []
        out = []
        for scale in SCALES:
            try:
                img = prepare(crop, scale)
                out.append(clean(asyncio.run(rating.RatingReader._recognize(engine, img))))
            except Exception:
                log.debug("name reading failed", exc_info=True)
        return [t for t in out if t]
