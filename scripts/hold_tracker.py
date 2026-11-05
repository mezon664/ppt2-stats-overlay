"""Flags the one NEXT-queue advance that isn't a real placement: using HOLD
for the first time in a match. HOLD starts the match empty; the first time a
player holds, the current piece goes into that empty slot and the next piece
spawns from NEXT the same way a lock does — so queue_tracker.py sees a queue
shift and counts a piece placed, but nothing was actually placed on the
board. Every hold after the first SWAPS with whatever's already in HOLD and
never touches NEXT, so this can only ever fire once per match per side.

Confirmed on a real recording (debug_frames/burst_hold, kept locally, not in
git): the right side's queue_tracker recorded a false placement at t=19.16,
the exact frame its HOLD box's colored-pixel ratio went from 0.000 (empty
checkerboard) to filled — the left side showed the same pairing later in the
same clip at t=20.31. Not a plain clear or banner event either time; nothing
else explains a queue shift with no corresponding board change.
"""
import cv2
import numpy as np

from gameplay_gate import PIECE_SAT_MIN

from board_read import HUE_BUCKETS
from capture_profile import scale_box, REFERENCE_PROFILE

# Reference-resolution (1232x692) boxes over just the HOLD piece icon (below
# the "HOLD" label), measured on debug_frames/burst_hold.
HOLD_ICON_BOXES = {"left": (123, 112, 187, 155), "right": (730, 117, 794, 160)}
FILLED_RATIO = 0.05  # colored-pixel ratio above which HOLD holds a piece (same threshold as gameplay_gate.SLOT_EMPTY_RATIO)
STABLE_READS = 2  # consecutive filled reads before the first use counts (rejects a one-frame misread)


class HoldTracker:
    def __init__(self, side, profile=None):
        self.profile = profile or REFERENCE_PROFILE
        self.box = scale_box(HOLD_ICON_BOXES[side], self.profile)
        self.used = False
        self.first_use_t = None
        self._candidate_t = None
        self._filled_reads = 0
        # A fill only means "first use" after HOLD has been seen empty: when
        # tracking starts mid-match (startup, the GO!-timeout fallback) HOLD is
        # often already filled, and treating that as a first use discarded a
        # real placement (burst_hold, left side, t=0.53).
        self._seen_empty = False

    def piece(self, frame):
        """The piece in HOLD now (I O T S Z J L, by its color as in the NEXT
        queue), or None when it's empty or can't be told (opener_detect: a
        first-bag piece held while a second-bag one went down in its place)."""
        x1, y1, x2, y2 = self.box
        region = frame[y1:y2, x1:x2]
        if region.size == 0:
            return None
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV).reshape(-1, 3)
        colored = (hsv[:, 1] > PIECE_SAT_MIN) & (hsv[:, 2] > 100)   # (gameplay_gate: paler captures)
        if colored.mean() <= FILLED_RATIO:
            return None
        h = int(np.median(hsv[colored, 0]))
        for label, lo, hi in HUE_BUCKETS:
            if lo <= h < hi:
                return label
        return None

    def update(self, frame, t):
        """Returns the timestamp HOLD was first confirmed used this match —
        exactly once, on the frame that confirms it — or None every other
        frame (including every frame after the first use)."""
        if self.used:
            return None
        x1, y1, x2, y2 = self.box
        region = frame[y1:y2, x1:x2]
        if region.size == 0:
            return None
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        filled = ((hsv[..., 1] > PIECE_SAT_MIN) & (hsv[..., 2] > 100)).mean() > FILLED_RATIO
        if not filled:
            self._seen_empty = True
            self._candidate_t, self._filled_reads = None, 0
            return None
        if not self._seen_empty:
            return None
        if self._candidate_t is None:
            self._candidate_t = t
        self._filled_reads += 1
        if self._filled_reads < STABLE_READS:
            return None
        self.used = True
        self.first_use_t = self._candidate_t
        return self._candidate_t
