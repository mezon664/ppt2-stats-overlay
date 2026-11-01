"""Precise match end/start detection via two banners (user's explicit request:
freeze the instant the match concludes, reset the instant the next one begins):

  - "やった!" (victory celebration) appears on the WINNING side's own panel the
    moment a round is decided -> match end -> freeze.
  - "ゴー!" (GO!) appears centered on screen during the pre-round countdown and
    disappears right as the next round's first pieces drop -> its disappearance
    -> match start -> reset.

Both templates were extracted directly from live capture (not the recorded video
used for the other banners), so the background-bleed mismatch that affected the
T-SPIN templates doesn't apply here — confirmed by a clean confidence curve on the
real frames they came from (noise floor ~0.15-0.26, true signal 0.87-1.0).

"やった!" was only observed on the right side in available footage; the left-side
window is a mirror-symmetry estimate (same reasoning/caveat as REN's left window
in banner_detect.py) using the same template image, since (unlike the T-SPIN/B2B
word crops) this is a large, high-contrast logo less likely to need a per-side
image — not yet confirmed with a real left-side win.
"""
from collections import deque
from pathlib import Path

import cv2
import numpy as np
from image_io import read_image

from capture_profile import scale_box, scale_template, REFERENCE_PROFILE

SCRIPTS_DIR = Path(__file__).resolve().parent

# GO! is detected by COLOR, not a template: the banner is a thick vivid-orange
# outline around white letters, and the gap between the left NEXT queue and
# the right HOLD box (where it sits) otherwise only ever shows stage
# background. The old template (t_go_live.png) was a big crop with board and
# stage background behind the letters; it matched its own stage in exactly
# one frame and scored 0.13 on the ice-studio stage even with "ゴー!" fully on
# screen. Banner orange in this region, measured on real recordings of three
# different stages: 0.17-0.24 while GO! is up, <=0.003 everywhere else
# (gameplay, victory screens, countdown), 0.008-0.019 the frame after it goes.
GO_REGION = (525, 230, 730, 400)  # reference coords
# Thresholds are relative to the stage's own background orange in that region,
# not absolute: some stages have orange there too (measured 0.000, 0.053 and
# 0.097 during play on three stages), and with fixed 0.10/0.03 the 0.097 stage
# never read GO! as gone afterwards (missed start, fell back to the timeout)
# while small drift past 0.10 followed by a transition to black read as a GO!
# that appeared and vanished (false start). GO! itself always jumps well above
# the background (0.05 -> 0.20-0.26, 0.097 -> 0.26) and falls back to it after.
GO_RISE = 0.08         # above background to count as GO! on screen
GO_FALL = 0.03         # within this of background again = GO! gone
GO_MIN = 0.10          # and never below this absolute level for GO! itself
GO_BASELINE_FRAMES = 15  # recent non-GO frames the background is the median of
GO_ENTER, GO_EXIT = GO_MIN, GO_FALL  # kept for tests describing the absolute floor


def _orange_ratio(frame, box):
    x1, y1, x2, y2 = box
    hsv = cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return float(((h >= 5) & (h <= 20) & (s >= 150) & (v >= 180)).mean())

YATTA_WINDOW_RIGHT = (742, 49, 1089, 218)
RIGHT_X_OFFSET = 803 - 198
YATTA_WINDOW_LEFT = tuple(
    v - RIGHT_X_OFFSET if i in (0, 2) else v for i, v in enumerate(YATTA_WINDOW_RIGHT)
)
YATTA_FILE = SCRIPTS_DIR / ".." / "assets" / "templates" / "t_yatta_live.png"
# The English game says "Yeah!" in the same place (burst_english: 0.88-1.00
# while it's up, <= 0.45 on everything else in the Japanese and English bursts)
YEAH_FILE = SCRIPTS_DIR / ".." / "assets" / "templates" / "t_yeah_live.png"
YATTA_ENTER, YATTA_EXIT = 0.70, 0.50


def _match(frame, tmpl, window):
    x1, y1, x2, y2 = window
    region = frame[y1:y2, x1:x2]
    th, tw = tmpl.shape[:2]
    if region.shape[0] < th or region.shape[1] < tw:
        return 0.0
    res = cv2.matchTemplate(region, tmpl, cv2.TM_CCOEFF_NORMED)
    return float(cv2.minMaxLoc(res)[1])


class MatchBoundaryDetector:
    """Tracks the GO!/victory-banner hysteresis state across frames. `update()`
    returns (victory_edge, go_disappeared_edge) — True exactly on the frame each
    transition is confirmed, not on every frame it stays true/false."""

    def __init__(self, profile=None):
        self.profile = profile or REFERENCE_PROFILE
        # Keep the unscaled images alive as attributes (not just local temporaries)
        # — capture_profile.scale_template() caches by id(img), and a temporary
        # passed inline can be garbage-collected and have its id() reused by the
        # NEXT cv2.imread() call, silently handing back the WRONG cached resize
        # (confirmed: this made self.yatta_tmpl end up holding the GO! image).
        self._yatta_tmpl_raw = read_image(YATTA_FILE)
        self.yatta_tmpl = scale_template(self._yatta_tmpl_raw, self.profile)
        self._yeah_tmpl_raw = read_image(YEAH_FILE)
        self.yeah_tmpl = scale_template(self._yeah_tmpl_raw, self.profile)
        self.go_region = scale_box(GO_REGION, self.profile)
        self.yatta_window_left = scale_box(YATTA_WINDOW_LEFT, self.profile)
        self.yatta_window_right = scale_box(YATTA_WINDOW_RIGHT, self.profile)

        self._go_active = False
        self._go_background = deque(maxlen=GO_BASELINE_FRAMES)
        self._yatta_active = False
        self.last_go_conf = 0.0
        self.last_yatta_conf = 0.0

    def update(self, frame, t):
        go_conf = _orange_ratio(frame, self.go_region)
        yatta_conf = max(
            _match(frame, tmpl, window)
            for tmpl in (self.yatta_tmpl, self.yeah_tmpl)       # Japanese / English game
            for window in (self.yatta_window_left, self.yatta_window_right)
        )
        self.last_go_conf = go_conf
        self.last_yatta_conf = yatta_conf

        victory_edge = False
        if not self._yatta_active and yatta_conf >= YATTA_ENTER:
            self._yatta_active = True
            victory_edge = True
        elif self._yatta_active and yatta_conf < YATTA_EXIT:
            self._yatta_active = False

        go_disappeared_edge = False
        background = float(np.median(self._go_background)) if self._go_background else 0.0
        if not self._go_active:
            if go_conf >= GO_MIN and go_conf >= background + GO_RISE:
                self._go_active = True
            else:
                self._go_background.append(go_conf)
        elif go_conf <= background + GO_FALL:
            self._go_active = False
            go_disappeared_edge = True

        return victory_edge, go_disappeared_edge
