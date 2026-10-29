"""Opener (開幕テンプレ) detection from the board after each early placement.

Shapes come from assets/openers.json: each opener's first-bag shape tags on
テトリステンプレ整理Wiki, as テト譜 (fumen) strings — the wiki tags every
opener with its finished first-bag shapes, mirrored versions and hold
variants included, so they are the exact boards to look for.

After each of the first MAX_PLACEMENTS placements (NEXT-queue advances), the
player's board is read cell by cell (bright = something there, the same rule
as board_read.board_is_clear, so stage art and the dim ghost piece don't
count) and compared with every shape: the bottom rows must equal the shape
exactly and every row above it must be empty, except the top few rows where
the next piece has already spawned. An exact match only — a board that is
one cell off, or has garbage under it, is not called anything.
"""
import json
from pathlib import Path

import cv2

from board_read import cell_center, LEFT_BOX, RIGHT_BOX, ROWS, COLS, CLEAR_V_MIN
from capture_profile import scale_box, REFERENCE_PROFILE
from fumen import decode

OPENERS_PATH = Path(__file__).resolve().parent.parent / "assets" / "openers.json"

MAX_PLACEMENTS = 10    # a first bag is 7 pieces; a little slack for the first hold
# The board is checked on every frame of the opening, not only when a
# placement is confirmed: a live 合掌TSD was missed because the frames between
# its 7th and 8th piece never coincided with a confirmed NEXT-queue shift
# (fast play / a queue misread at the start). Checking stops after this long
# or once MAX_PLACEMENTS pieces are down, whichever comes first.
OPENING_S = 12.0
# Only these rows right above the shape must be empty. Checking the whole
# board missed a live 迷走砲: the white sparkles of a hard drop sat a few rows
# higher, and the next piece can already be falling too.
CLEAR_ROWS_ABOVE = 2
# A cell is a block when this share of its sample patch is bright: blocks fill
# the cell, while sparkle particles are a few bright pixels.
BLOCK_FILL = 0.5


def _shape_rows(fumen):
    """A shape tag as occupancy rows, bottom row first, trimmed to its height."""
    rows = decode(fumen)[0].board_with_piece()
    height = max((i + 1 for i, r in enumerate(rows) if any(r)), default=0)
    return tuple(tuple(bool(c) for c in rows[i]) for i in range(height))


def load_openers(path=OPENERS_PATH):
    """[(name, shape_rows)], several shapes per opener."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for op in data["openers"]:
        name = op.get("display") or op["name"]     # shorter on-screen name if given
        for f in op["shapes"]:
            out.append((name, _shape_rows(f)))
    return out


def match_openers(occupancy, openers):
    """Names of the openers whose shape the board shows exactly.
    occupancy: ROWS rows of COLS bools, bottom row first."""
    names = []
    for name, shape in openers:
        h = len(shape)
        if all(tuple(occupancy[r]) == shape[r] for r in range(h)) and \
                not any(any(occupancy[r]) for r in range(h, min(ROWS, h + CLEAR_ROWS_ABOVE))):
            if name not in names:
                names.append(name)
    return names


def read_occupancy(frame, box):
    """ROWS x COLS bools, bottom row first: True where the cell holds a block
    (most of its sample patch bright — see BLOCK_FILL)."""
    x1, y1, x2, y2 = box
    v = cv2.cvtColor(frame[y1:y2 + 4, x1:x2 + 4], cv2.COLOR_BGR2HSV)[..., 2]   # just the board
    rows = []
    for row in range(ROWS - 1, -1, -1):          # board_read rows are top-first
        cells = []
        for col in range(COLS):
            cx, cy = cell_center(box, col, row)
            cx, cy = cx - x1, cy - y1
            patch = v[cy - 3:cy + 3, cx - 3:cx + 3]
            cells.append(bool((patch >= CLEAR_V_MIN).mean() >= BLOCK_FILL))
        rows.append(cells)
    return rows


_OPENERS = None


def openers():
    global _OPENERS
    if _OPENERS is None:
        _OPENERS = load_openers()
    return _OPENERS


class OpenerDetector:
    """One player's opener for the current match (reset with the pipeline)."""

    def __init__(self, side, profile=None):
        self.side = side
        self.profile = profile or REFERENCE_PROFILE
        self.box = scale_box(LEFT_BOX if side == "left" else RIGHT_BOX, self.profile)
        self.placements = 0
        self.name = None

    def on_frame(self, frame, t_in_match, placements=0):
        """Call on every frame with the time since the match started and the
        placements confirmed on this frame. During the opening the board is
        compared every frame; returns the opener name when it becomes known
        or changes, else None."""
        self.placements += placements
        if t_in_match > OPENING_S or self.placements > MAX_PLACEMENTS:
            return None
        return self._check(frame)

    def on_placements(self, frame, count):
        """Check only when `count` placements were confirmed on this frame
        (kept for tests / callers without match time)."""
        if count <= 0 or self.placements >= MAX_PLACEMENTS:
            return None
        self.placements += count
        return self._check(frame)

    def _check(self, frame):
        names = match_openers(read_occupancy(frame, self.box), openers())
        if not names:
            return None
        name = " / ".join(names)      # shapes shared by two openers: show both
        if name != self.name:
            self.name = name
            return name
        return None
