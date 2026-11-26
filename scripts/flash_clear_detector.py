"""Line-clear detection via the white flash/light-burst effect the game plays on
ANY line clear (confirmed: fires for T-SPIN Double and TETRIS alike in validated
footage — the effect isn't specific to special moves, unlike the banners).

This is a generic "a clear just happened" signal, not a type/line-count signal —
it can't tell a plain single apart from a Tetris. But combined with:
  - banner detection (T-SPIN/TETRIS) when a banner DOES appear, giving exact type,
  - a flash with NO banner, treated as an unbannered (plain) clear of unknown size,
it directly fixes the two problems banner-only detection couldn't (user-confirmed,
see phase4 notes): plain clears are invisible to banners entirely, and the
estimated REN counter couldn't tell a non-clearing placement had broken the combo.
A flash edge, independent of banners, is also the right place to increment REN;
its ABSENCE despite continued play is what should break it (see line_clear_tracker.py).

Validated against real footage (not just synthetic data — board_tracker.py and the
aggregate-cell-count approach in line_clear_detector.py both failed this step):
baseline near-white pixel ratio within the playfield is ~0.05, isolated noise
peaks reach ~0.09, and the 3 real clear-flash clusters in a 70s burst peaked at
0.21-0.42 — a clean ~4x+ separation. Not yet validated for PLAIN (unbannered)
clears specifically, since the available footage happened to only contain
special-move clears early on — that's the next thing to confirm live.

WHITE_PIXEL_THRESHOLD recalibrated (current live theme): the original 220 was
measured against a theme whose EMPTY cells render dark. The current stage's
EMPTY cells render as a light gray checkerboard, sampled directly at 225-245
brightness — well above 220 — so the old threshold counted ordinary empty
board as "near-white" (confirmed: an idle board with no clear in progress
measured ratio=0.16, well past the old ENTER_RATIO, from empty cells alone).
Genuine flash pixels reach true white (250+); raising the threshold to 250
cleanly separates them (idle board -> 0.0000, confirmed real clears -> still
0.02-0.21) — see the live threshold-comparison notes from that investigation.

LINE COUNT, not just "a clear happened": at WHITE_PIXEL_THRESHOLD=250, the
flash resolves into a clean per-ROW signal — at the exact rising-edge frame,
the rows that actually cleared read ~100% white while every other row reads
~0% (confirmed against a user-run ground-truth sequence of 1/2/3/4-line
clears done in order: row-counting gave exactly 1,2,3,4 lit rows at each
edge, and separately against 8 banner-confirmed events — T-SPIN Single=1,
T-SPIN Double=2, TETRIS=4 — every single one matched its banner's true line
count exactly). This is what board-state before/after diffing
(live_pipeline.py's old approach) was trying and failing to measure
accurately (noisy deltas like -4 or +27 for real single-digit-line clears) —
the flash itself already tells you the count directly, read at the RISING
EDGE frame specifically (a later "peak" frame over-counts: the glow bleeds
into neighboring rows as it blooms, confirmed up to 6 "lit" rows for an
actual 4-line clear a few frames after the edge).
"""
import cv2
from image_io import write_image
import numpy as np

from capture_profile import scale_box, REFERENCE_PROFILE
from board_read import LEFT_BOX, RIGHT_BOX, ROWS

WHITE_PIXEL_THRESHOLD = 250   # 0-255 grayscale cutoff for "near-white"
ENTER_RATIO = 0.05
EXIT_RATIO = 0.025
ROW_LIT_RATIO = 0.5   # fraction of a row's pixels that must be near-white to count as "cleared"
MAX_LINES_PER_EVENT = 4


# White runs shorter than this part of a row (top to bottom) don't count toward
# the flash: a garbage block's top edge is a thin bright line that a capture
# board's / stream's picture puts past 250. A board half full of garbage then
# read ~0.03-0.05 white with no flash at all, above EXIT_RATIO, so the flash
# never ended and every clear after it was swallowed (user report: both sides'
# numbers stopped once the garbage piled up; seen on their stream). A clear's
# flash is whole rows tall and stays.
THIN_LINE_OF_ROW = 0.35


def _white_ratio(frame, box):
    x1, y1, x2, y2 = box
    region = frame[y1:y2, x1:x2]
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    white = (gray > WHITE_PIXEL_THRESHOLD).astype(np.uint8)
    k = max(3, int((y2 - y1) / ROWS * THIN_LINE_OF_ROW))
    white = cv2.morphologyEx(white, cv2.MORPH_OPEN, np.ones((k, 1), np.uint8))
    return float(white.mean())


# The board's true row pitch over the box's own (box height / 20): the box
# starts a little above the top row (the grid is 23.0 px a row at the
# reference size, the box 23.55 a band).
ROW_PITCH_OF_BAND = 23.0 / 23.55


def count_lit_rows(frame, box):
    return len(lit_rows(frame, box))


def lit_rows(frame, box):
    """The board rows (0 the bottom one) that count_lit_rows counts: which
    rows a clear takes away (live_pipeline: how many of them were garbage).

    count_lit_rows: how many board rows are (almost) entirely near-white in this
    exact frame — the measured line count for a clear caught at its flash's
    rising edge. Not clamped to MAX_LINES_PER_EVENT here (the caller decides
    what an out-of-range count means — likely the wrong frame was used, e.g.
    a bloomed-out peak rather than the edge).

    The rows are 20 bands of the board's row pitch, but where they start is
    found on the frame itself: the start (within half a row of the grid's
    usual place) at which each band is most clearly all-white or all-dark.
    With fixed bands, a picture sitting a quarter row off them (a capture
    board's, user report: a TETRIS read as 5 lit rows and dropped, T-SPIN
    Doubles as 3 — 73 in one evening, singles as 0) lit one band too many or
    too few (tools/validation/flash_rows_shift.py)."""
    x1, y1, x2, y2 = box
    pitch = (y2 - y1) / ROWS * ROW_PITCH_OF_BAND
    top = y1 + (y2 - y1) - ROWS * pitch       # the grid's usual top (the box starts above it)
    pad = int(pitch) + 1
    lo = max(0, int(top) - pad)
    gray = cv2.cvtColor(frame[lo:y2 + pad, x1:x2], cv2.COLOR_BGR2GRAY)
    lit = (gray > WHITE_PIXEL_THRESHOLD).mean(axis=1)          # each pixel line's white share
    cum = np.concatenate(([0.0], np.cumsum(lit)))
    best = None
    for step in range(-int(pitch / 2), int(pitch / 2) + 1):
        edges = [int(round(top - lo + step + r * pitch)) for r in range(ROWS + 1)]
        edges = [min(max(e, 0), len(lit)) for e in edges]
        means = [(cum[b] - cum[a]) / max(1, b - a) for a, b in zip(edges, edges[1:])]
        # (white left outside the 20 bands counts against this start too)
        outside = (cum[edges[0]] + cum[-1] - cum[edges[-1]]) / pitch
        muddle = sum(min(m, 1 - m) for m in means) + outside
        if best is None or muddle < best[0] - 1e-9 or (abs(muddle - best[0]) <= 1e-9 and abs(step) < abs(best[2])):
            best = (muddle, [ROWS - 1 - r for r, m in enumerate(means) if m > ROW_LIT_RATIO], step)
    return sorted(best[1])


def count_lit_bands(frame, box):
    """The older measure (20 fixed bands), kept for comparisons in tools/."""
    x1, y1, x2, y2 = box
    row_h = (y2 - y1) / ROWS
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    count = 0
    for r in range(ROWS):
        row = gray[int(y1 + r * row_h):int(y1 + (r + 1) * row_h), x1:x2]
        if (row > WHITE_PIXEL_THRESHOLD).mean() > ROW_LIT_RATIO:
            count += 1
    return count


class FlashClearDetector:
    """One instance per side. update() returns True exactly on the frame a flash
    is first confirmed (rising edge), not on every frame it stays bright."""

    def __init__(self, side, profile=None, debug_dump_dir=None):
        self.side = side
        self.profile = profile or REFERENCE_PROFILE
        box = LEFT_BOX if side == "left" else RIGHT_BOX
        self.box = scale_box(box, self.profile)
        self._active = False
        self.last_ratio = 0.0
        self.last_edge_row_count = None  # set on the frame an edge fires; see count_lit_rows
        self.last_edge_rows = []         # those rows, 0 the bottom one (lit_rows)
        # Live play (post-calibration) showed far more edges than the original
        # validation clip ever had — the box covers the WHOLE playfield, so any
        # bright moment unrelated to a line clear (light-colored pieces, a
        # garbage-warning flash, etc.) can cross ENTER_RATIO too. Dumping the
        # raw frame at every edge lets that be checked against real screenshots
        # instead of guessed at.
        self.debug_dump_dir = debug_dump_dir

    def update(self, frame, t):
        ratio = _white_ratio(frame, self.box)
        self.last_ratio = ratio
        edge = False
        if not self._active and ratio >= ENTER_RATIO:
            self._active = True
            edge = True
            # Measured at THIS exact frame, not a later one — see count_lit_rows'
            # docstring for why a later "peak" frame over-counts.
            self.last_edge_rows = lit_rows(frame, self.box)
            self.last_edge_row_count = len(self.last_edge_rows)
        elif self._active and ratio < EXIT_RATIO:
            self._active = False
        if edge and self.debug_dump_dir:
            import os
            import cv2 as _cv2
            os.makedirs(self.debug_dump_dir, exist_ok=True)
            fname = f"flash_{self.side}_t{t:.2f}_ratio{ratio:.3f}_rows{self.last_edge_row_count}.png"
            write_image(os.path.join(self.debug_dump_dir, fname), frame)
        return edge

    @property
    def active(self):
        """True while a flash is still playing out (ratio hasn't dropped below
        EXIT_RATIO yet) — the right moment to read "after" board state is once
        this goes back to False, not some guessed fixed delay."""
        return self._active
