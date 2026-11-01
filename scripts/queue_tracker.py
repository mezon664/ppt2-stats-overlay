"""Counts piece placements by watching each player's NEXT queue shift up.

Every placed piece advances the queue by one (the next piece spawns, the rest
move up, a new one slides in at the bottom). Combined with the clear flash,
that gives the REN rule directly: a placement with no clear flash since the
previous placement is a piece that locked without clearing, which ends the
combo. Measured on real recordings: a clearing placement shows its flash and
then the queue advances 0.55-0.81s later (the line-clear delay); a
non-clearing one advances right away with no flash in between.

Board-state tracking was tried for this before and gave unusable noise, and
watching the on-screen REN badge failed live against moving stage art; the
queue is match UI (same on every stage), anchored on the same NEXT label the
gameplay gate already matches.

Readings are the five slot pieces as letters (I O T S Z J L, from the same
hue buckets as board_read). While the queue slides, single frames misread
(e.g. ISOLO -> ISIIO -> ISOLO), so a reading only counts once it's been seen
twice in a row AND is the previous reading shifted up — and an advance is
timestamped at the first frame its new reading appeared, not when it was
confirmed (a fast piece can clear one frame after spawning; stamping late
would hand that flash to the wrong piece).

A match's very first queue shift is not a placement either, same idea as the
HOLD case (see hold_tracker.py): confirmed on every match boundary in
debug_frames/burst_boundary (4/4, both sides, 8/8) — a clean 1-shift lands
0.16-0.27s after the tracker's first reading, every single time, far too
fast to be a real placement. That's the first piece SPAWNING (leaving the
NEXT display to become the piece in play), not locking. Only the first
confirmed shift of a tracker's life is treated this way; every shift after
it is a real placement exactly as the comment above describes.
"""
import logging

import cv2
import numpy as np
from image_io import read_image

from board_read import HUE_BUCKETS
from capture_profile import scale_box, scale_template, REFERENCE_PROFILE
from gameplay_gate import NEXT_TEMPLATE_PATH, NEXT_WINDOWS, ON_SCREEN_THRESHOLD, QUEUE_SLOTS, SLOT_EMPTY_RATIO

log = logging.getLogger("queue_tracker")

STABLE_READS = 2       # consecutive identical readings before a reading counts
REBASELINE_READS = 4   # a stable reading that isn't a shift of the last one this long is a new baseline
MAX_SHIFT = 3          # placements that can land between two confirmed readings


def _hue_letter(h):
    for label, lo, hi in HUE_BUCKETS:
        if lo <= h < hi:
            return label
    return "?"


def count_advances(old, new):
    """How many places `new` is `old` shifted up by (0 if unchanged), or None
    if it isn't a shift at all (misread, or a different queue entirely)."""
    if new == old:
        return 0
    for k in range(1, MAX_SHIFT + 1):
        if new[:len(new) - k] == old[k:]:
            return k
    return None


class NextQueueTracker:
    def __init__(self, side, profile=None, discard_first_shift=False):
        self.side = side
        self.profile = profile or REFERENCE_PROFILE
        self.template = scale_template(read_image(NEXT_TEMPLATE_PATH), self.profile)
        self.window = scale_box(NEXT_WINDOWS[side], self.profile)
        self.slots = [tuple(int(round(v * self.profile.scale_x)) for v in s) for s in QUEUE_SLOTS]
        self.stable = None
        self._candidate = None
        self._candidate_t = None
        self._candidate_reads = 0
        self.pieces_placed = 0
        self.last_reading = None
        # The match's first confirmed shift is the first piece spawning, not
        # a lock — see the module docstring. Only set when the caller knows
        # this tracker was created right at a confirmed match start (not at
        # startup mid-match, a window resize, or the GO!-timeout fallback,
        # where the tracker's first observed shift is a real placement).
        # Cleared after that one shift either way.
        self._first_shift_pending = discard_first_shift

    def _read(self, frame):
        x1, y1, x2, y2 = self.window
        region = frame[y1:y2, x1:x2]
        th, tw = self.template.shape[:2]
        if region.shape[0] < th or region.shape[1] < tw:
            return None
        res = cv2.matchTemplate(region, self.template, cv2.TM_CCOEFF_NORMED)
        _, score, _, (mx, my) = cv2.minMaxLoc(res)
        if score < ON_SCREEN_THRESHOLD:
            return None
        lx, ly = x1 + mx, y1 + my
        h, w = frame.shape[:2]
        seq = ""
        for a, b, c, d in self.slots:
            reg = frame[max(0, ly + b):min(h, ly + d), max(0, lx + a):min(w, lx + c)]
            if reg.size == 0:
                return None
            hsv = cv2.cvtColor(reg, cv2.COLOR_BGR2HSV).reshape(-1, 3)
            colored = (hsv[:, 1] > 120) & (hsv[:, 2] > 120)
            if colored.mean() < SLOT_EMPTY_RATIO:
                seq += "."
            else:
                seq += _hue_letter(int(np.median(hsv[colored, 0])))
        return seq

    def update(self, frame, t):
        """Returns the timestamps of placements confirmed on this frame
        (usually empty, occasionally one, rarely more)."""
        seq = self._read(frame)
        self.last_reading = seq
        if seq is None or "." in seq or "?" in seq:
            self._candidate, self._candidate_reads = None, 0
            return []
        if seq == self._candidate:
            self._candidate_reads += 1
        else:
            self._candidate, self._candidate_t, self._candidate_reads = seq, t, 1
        if self._candidate_reads < STABLE_READS:
            return []
        if self.stable is None:
            self.stable = seq
            return []
        k = count_advances(self.stable, seq)
        if k is None:
            if self._candidate_reads >= REBASELINE_READS:
                log.info("[%s] queue %s -> %s isn't a shift; re-baselining", self.side, self.stable, seq)
                self.stable = seq
            return []
        if k:
            self.stable = seq
            if self._first_shift_pending:
                self._first_shift_pending = False
                k -= 1  # that shift was the first piece spawning, not a placement
            if k:
                self.pieces_placed += k
        return [self._candidate_t] * k
