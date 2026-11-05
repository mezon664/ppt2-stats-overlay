"""Black and white levels of the captured picture, put right before reading.

Some PCs capture the game washed out: blacks gray, whites dim (Windows with
HDR on is the usual one). Every check made for a normal picture then misses
— the orange of GO!, the white of a clear flash, the colors of the NEXT
pieces: replaying the recordings washed out (black 42, white 233) left 1 of
9, 1 of 14 and 3 of 15 events (a user's T-SPINs went uncounted).

The NEXT label is the yardstick: white letters on black, and found by its
shape whatever the levels (its match score stays the same washed out). On
every recording its darkest part is 0 and its brightest 255 (127 while the
pause dims the screen). So its darks and brights are noted on the match
screen, and when they say the picture is washed out, every frame is
stretched back to 0-255 before it's read.
"""
from collections import deque

import cv2
import numpy as np

KEEP = 60              # label readings remembered
MIN_READINGS = 10      # before anything is put right
DARK_OK = 8            # a black up to this is black
BRIGHT_OK = 240        # a white from this is white
MIN_RANGE = 100        # less than this between them: not trusted (a dark screen)
STEP = 2.0             # the stretch only changes once the levels moved this much


class Levels:
    def __init__(self):
        self._darks = deque(maxlen=KEEP)
        self._brights = deque(maxlen=KEEP)
        self._lut = None
        self.range = None   # (black, white) being put right, or None

    def observe(self, raw, gate):
        """The NEXT labels the gate found on this (uncorrected) frame."""
        found = getattr(gate, "last_found", None) or {}
        th, tw = gate.template.shape[:2]
        for x, y in found.values():
            label = raw[y:y + th, x:x + tw]
            if label.size == 0:
                continue
            gray = cv2.cvtColor(label, cv2.COLOR_BGR2GRAY)
            self._darks.append(float(np.percentile(gray, 5)))
            self._brights.append(float(np.percentile(gray, 95)))
        if len(self._darks) >= MIN_READINGS:
            self._update()

    def _update(self):
        dark = float(np.median(self._darks))
        bright = float(np.percentile(self._brights, 90))   # dimmed frames (pause) don't count
        if (dark <= DARK_OK and bright >= BRIGHT_OK) or bright - dark < MIN_RANGE:
            self._lut, self.range = None, None
            return
        if self.range is not None and abs(self.range[0] - dark) < STEP and abs(self.range[1] - bright) < STEP:
            return
        self.range = (dark, bright)
        x = np.arange(256, dtype=np.float32)
        self._lut = np.clip((x - dark) * 255.0 / (bright - dark), 0, 255).astype(np.uint8)

    def apply(self, frame):
        return frame if self._lut is None else cv2.LUT(frame, self._lut)
