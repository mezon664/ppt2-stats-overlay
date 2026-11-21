"""Is this マラソン with エンドレス ON? (開幕テンプレ練習 runs only there.)

The match screen doesn't show the setting, so it is read on マラソン's start
screen (every way into a game passes it, ゲームせってい comes back to it) and
kept until it shows again. ON and OFF each need their own clear match: the
value slides and fades in, and those frames say nothing. The match itself is
told by the "MARATHON" label of the MODE panel (still readable under the
pause menu). A setting that wasn't seen counts as not ON. Screen capture only.

Measured on debug_frames/burst_marathon_endless and the versus recordings
(tests/test_endless_gate.py)."""
from pathlib import Path

import cv2

from image_io import read_image

TEMPLATES = Path(__file__).resolve().parent / ".." / "assets" / "templates"
REFERENCE_W = 1232
# (reference px) where each template is looked for
MODE_WINDOW = (850, 95, 1080, 150)
ROW_WINDOW = (680, 145, 810, 188)
VALUE_WINDOW = (945, 145, 1020, 188)
LABEL_MIN = 0.85
VALUE_MIN = 0.9
# this many readings of a match that isn't マラソン forget the setting
OTHER_MODE_READS = 20


def _load(name):
    return cv2.cvtColor(read_image(TEMPLATES / name), cv2.COLOR_BGR2GRAY)


def _score(gray, box, template):
    x1, y1, x2, y2 = box
    return float(cv2.matchTemplate(gray[y1:y2, x1:x2], template, cv2.TM_CCOEFF_NORMED).max())


class EndlessGate:
    def __init__(self):
        self.mode = _load("t_marathon_label.png")
        self.row = _load("t_endless_row.png")
        self.on = _load("t_endless_on.png")
        self.off = _load("t_endless_off.png")
        self.endless = None     # True / False as last shown, None = not seen
        self.marathon = False
        self._other = 0

    def update(self, frame, match_screen=False):
        """One frame; returns whether practice may run now."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if gray.shape[1] != REFERENCE_W:
            gray = cv2.resize(gray, (REFERENCE_W, round(gray.shape[0] * REFERENCE_W / gray.shape[1])),
                              interpolation=cv2.INTER_AREA)
        if _score(gray, ROW_WINDOW, self.row) >= LABEL_MIN:
            on, off = _score(gray, VALUE_WINDOW, self.on), _score(gray, VALUE_WINDOW, self.off)
            if max(on, off) >= VALUE_MIN:
                self.endless = on > off
        self.marathon = _score(gray, MODE_WINDOW, self.mode) >= LABEL_MIN
        if self.marathon or not match_screen:
            self._other = 0
        else:
            self._other += 1
            if self._other >= OTHER_MODE_READS:
                self.endless = None
        return self.marathon and self.endless is True
