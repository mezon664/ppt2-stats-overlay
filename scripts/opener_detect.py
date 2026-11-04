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
one cell off is not called anything.

Holding a first-bag piece and putting a second-bag piece down first (user:
山岳積み with its L held and the next bag's Z down — never recognized): the
board is then the shape without the held piece and with one more piece, or,
once the held piece goes in, the whole shape plus one more piece. So each
piece is noted as it lands (the 4 cells that appear), and when nothing
matches exactly each landed piece is taken out in turn: what's left must be
a whole shape, or a shape once a piece of the kind in HOLD (its color) is put
back somewhere. (Indexing every shape without each of its pieces instead
took 1.5 million entries and 527 MB.)

Garbage (お邪魔) received during the opening pushes the shape up: whole
garbage rows at the bottom are set aside first (user's request), and the
shape must then sit exactly on top of them. Only rows that are plainly
garbage count — see garbage_rows.
"""
import json
import re
from pathlib import Path

import cv2
import numpy as np

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
# Garbage rows: every cell but one holds a block, and those blocks are grey.
# Measured (burst2): garbage blocks saturation 0, piece blocks 120-255 (one
# lit-up cell 44). A row with any colored block is not garbage, so a player's
# own nearly full row is never taken for one.
GARBAGE_SAT_MAX = 30


def _shape_rows(fumen):
    """A shape tag as occupancy rows, bottom row first, trimmed to its height."""
    rows = decode(fumen)[0].board_with_piece()
    height = max((i + 1 for i, r in enumerate(rows) if any(r)), default=0)
    return tuple(tuple(bool(c) for c in rows[i]) for i in range(height))


def _cleared(rows):
    """The shape as the game shows it: a full row is cleared at once, so it
    drops out and everything above moves down (1269 of the wiki's 4411 tags
    hold full rows — openers that clear lines in their first bag)."""
    rows = tuple(r for r in rows if not all(r))
    height = max((i + 1 for i, r in enumerate(rows) if any(r)), default=0)
    return rows[:height]


# After its cleared lines drop out a shape can be tiny (321 tags leave 8
# cells, 14 leave 4) — a board that size turns up early in any opening: in
# the recordings, 5 sparse boards of 6-10 cells were named that way (the CPU
# after an early clear). A leftover under this many cells isn't used; such an
# opener is recognized just before its T-spin instead (_before_the_t_spin).
MIN_LEFTOVER_CELLS = 14
# A leftover shape only counts once the opener's own number of pieces could
# be down; the placement count can lag a piece or two behind.
PLACEMENT_SLACK = 2
# The T piece in its 4 turns: (cells as (column, row) offsets with rows
# counted upward, its center cell).
T_CELLS = ((((0, 0), (1, 0), (2, 0), (1, 1)), (1, 0)), (((1, 0), (0, 1), (1, 1), (2, 1)), (1, 1)),
           (((0, 0), (0, 1), (0, 2), (1, 1)), (0, 1)), (((1, 0), (1, 1), (1, 2), (0, 1)), (1, 1)))


def _before_the_t_spin(raw):
    """A tag with full rows shows the first bag as if nothing cleared; in the
    game those rows clear as the T goes in, so the opener is on screen just
    BEFORE that: the tag without the T. Every way a T fits there as a
    T-spin (inside the shape, touching each full row, leaving none full, and
    3 of the 4 corners around its center blocked — the game's T-spin rule,
    and open above in at least one of its columns, so it can come down)
    gives one such board."""
    full = [i for i, r in enumerate(raw) if all(r)]
    if not full:
        return []
    cells = {(c, r) for r, row in enumerate(raw) for c, v in enumerate(row) if v}
    out = []
    for turn, (mc, mr) in T_CELLS:
        for r0 in range(len(raw)):
            for c0 in range(COLS):
                t = {(c0 + dc, r0 + dr) for dc, dr in turn}
                if not t <= cells or any(not any((c, r) in t for c in range(COLS)) for r in full):
                    continue
                cx, cy = c0 + mc, r0 + mr
                blocked = sum(1 for dx in (-1, 1) for dy in (-1, 1)
                              if not (0 <= cx + dx < COLS) or cy + dy < 0
                              or ((cx + dx, cy + dy) in cells and (cx + dx, cy + dy) not in t))
                if blocked < 3:
                    continue
                rest = cells - t   # the T has to come down from the top: some column of it is open above
                if not any(all((c, rr) not in rest for rr in range(r + 1, len(raw) + 2)) for c, r in t):
                    continue
                rows = tuple(tuple((c, r) in cells and (c, r) not in t for c in range(COLS)) for r in range(len(raw)))
                if any(all(r) for r in rows):
                    continue
                height = max((i + 1 for i, r in enumerate(rows) if any(r)), default=0)
                if rows[:height] not in out:
                    out.append(rows[:height])
    return out
# Boards as bit masks for the hold case: row r, column c is bit r * COLS + c.
# Only the rows a first bag can reach (the next piece spawns higher up).
MASK_ROWS = 12
HOLD_MIN_CELLS = 24   # the hold case: only shapes of 6 pieces or more


def _mask(rows):
    m = 0
    for r, row in enumerate(rows[:MASK_ROWS]):
        for c, v in enumerate(row):
            if v:
                m |= 1 << (r * COLS + c)
    return m


def _turns():
    """Each tetromino's turns as cell offsets (column, row), from its lowest-left corner."""
    base = {"I": [(0, 0), (1, 0), (2, 0), (3, 0)], "O": [(0, 0), (1, 0), (0, 1), (1, 1)],
            "T": [(0, 0), (1, 0), (2, 0), (1, 1)], "S": [(0, 0), (1, 0), (1, 1), (2, 1)],
            "Z": [(1, 0), (2, 0), (0, 1), (1, 1)], "J": [(0, 0), (1, 0), (2, 0), (0, 1)],
            "L": [(0, 0), (1, 0), (2, 0), (2, 1)]}
    out = {}
    for letter, cells in base.items():
        seen, cur = set(), cells
        for _ in range(4):
            cur = [(y, -x) for x, y in cur]
            mx, my = min(x for x, _ in cur), min(y for _, y in cur)
            seen.add(tuple(sorted((x - mx, y - my) for x, y in cur)))
        out[letter] = sorted(seen)
    return out


TURNS = _turns()
ALL_TURNS = sorted({t for ts in TURNS.values() for t in ts})   # the 19 tetromino outlines
# every placement of each piece kind on the bottom MASK_ROWS rows, as masks
PLACEMENTS = {letter: [sum(1 << ((r + dy) * COLS + c + dx) for dx, dy in turn)
                       for turn in turns
                       for r in range(MASK_ROWS - max(dy for _, dy in turn))
                       for c in range(COLS - max(dx for dx, _ in turn))]
              for letter, turns in TURNS.items()}


def _is_tetromino(mask):
    cells = [(i % COLS, i // COLS) for i in range(MASK_ROWS * COLS) if mask >> i & 1]
    if len(cells) != 4:
        return False
    mx, my = min(x for x, _ in cells), min(y for _, y in cells)
    return tuple(sorted((x - mx, y - my) for x, y in cells)) in ALL_TURNS


# A board shared by several openers shows this many names, then "ほか".
MAX_NAMES = 2


def screen_name(name):
    """The name as shown: without its （…）/(…) variant part — パフェ積み(中あけ)
    and りねパフェ(左凸) show as パフェ積み / りねパフェ (user's request)."""
    return re.sub(r"\s*[（(][^）)]*[）)]", "", name).strip() or name


class Shape(tuple):
    """(name, rows as the game shows them, pieces the opener has placed)."""
    __slots__ = ()

    def __new__(cls, name, rows, pieces=0):
        return super().__new__(cls, (name, rows, pieces))


def load_openers(path=OPENERS_PATH):
    """[Shape(name, rows, pieces)], several shapes per opener; rows with the
    shape's full lines cleared (see _cleared)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for op in data["openers"]:
        name = screen_name(op.get("display") or op["name"])     # shorter on-screen name if given
        for f in op["shapes"]:
            raw = _shape_rows(f)
            rows = _cleared(raw)
            if rows == raw:
                out.append(Shape(name, rows))
                continue
            # lines clear in this first bag: the board just before the T-spin,
            # and (if it's big enough to tell apart) the one left after it
            for before in _before_the_t_spin(raw):
                out.append(Shape(name, before))
            if sum(map(sum, rows)) >= MIN_LEFTOVER_CELLS:
                out.append(Shape(name, rows, sum(map(sum, raw)) // 4))
    return out


class OpenerIndex:
    """The shapes looked up by their rows (4000+ shapes are compared every
    frame of the opening for both players: a scan of all of them was too slow)."""

    def __init__(self, openers, english=None):
        self.english = english or {}   # see load_english
        self.openers = list(openers)
        self.by_rows = {}
        for shape in self.openers:
            name, rows = shape[0], shape[1]
            self.by_rows.setdefault(rows, []).append(shape)
        self.heights = sorted({len(r) for r in self.by_rows})
        # the hold case: whole shapes (not the leftovers after a clear) as masks
        self.by_mask = {}
        for shape in self.openers:
            if len(shape) > 2 and shape[2]:
                continue
            names = self.by_mask.setdefault(_mask(shape[1]), [])
            if shape[0] not in names:
                names.append(shape[0])
        # only shapes of most of a bag: with a small one (3-4 pieces) any early
        # board less a piece came out as an opener (burst_boundary, the CPU)
        self.counts = {c for c in (bin(m).count("1") for m in self.by_mask) if c >= HOLD_MIN_CELLS}

    def match(self, occupancy, placements=None):
        names = []
        for h in self.heights:
            if any(any(occupancy[r]) for r in range(h, min(ROWS, h + CLEAR_ROWS_ABOVE))):
                continue
            for shape in self.by_rows.get(tuple(tuple(occupancy[r]) for r in range(h)), ()):
                name, pieces = shape[0], shape[2] if len(shape) > 2 else 0
                if placements is not None and pieces and placements < pieces - PLACEMENT_SLACK:
                    continue   # a small leftover shape this early is something else
                if name not in names:
                    names.append(name)
        return names

    def match_with_hold(self, mask, landed, hold):
        """No exact shape: one landed piece is a second-bag one (see the
        module docstring). landed: the pieces that landed, as masks; hold:
        the piece kind in HOLD, or None."""
        n = bin(mask).count("1")
        names = []
        for piece in landed:
            if piece & mask != piece:
                continue
            rest = mask & ~piece
            found = []
            if n - 4 in self.counts:                     # the held piece went in after it: the whole shape
                found += self.by_mask.get(rest, [])
            if hold in PLACEMENTS and n in self.counts:  # still held: the shape once it's put back
                for p in PLACEMENTS[hold]:
                    if not p & rest:
                        found += self.by_mask.get(rest | p, [])
            found = [f for f in found if f]
            for name in found:
                if name not in names:
                    names.append(name)
        return names


def shown_name(names, language="ja"):
    """What the overlays show for these names: up to MAX_NAMES of them."""
    if len(names) <= MAX_NAMES:
        return " / ".join(names)
    return " / ".join(names[:MAX_NAMES]) + (" ほか" if language == "ja" else " etc.")


def load_english(path=OPENERS_PATH):
    """{shown Japanese name: English name} for the openers that have one
    ("name_en": Hard Drop's name, else the wiki's — see
    tools/opener_import/build_openers.py). The rest show in Japanese in
    English too (user's request)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = {}
    for op in data["openers"]:
        if op.get("name_en"):
            # without its (…) part, like the Japanese names (user: in English too)
            out.setdefault(screen_name(op.get("display") or op["name"]), screen_name(op["name_en"].strip()))
    return out


def match_openers(occupancy, openers, placements=None):
    """Names of the openers whose shape the board shows exactly.
    occupancy: ROWS rows of COLS bools, bottom row first. openers: an
    OpenerIndex (or a list of shapes). placements: pieces placed so far
    (None: don't check, see PLACEMENT_SLACK)."""
    if not isinstance(openers, OpenerIndex):
        openers = OpenerIndex(openers)
    return openers.match(occupancy, placements)


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


def garbage_rows(frame, box):
    """How many rows at the bottom of the board are garbage: exactly one empty
    cell, every block grey (see GARBAGE_SAT_MAX). Counted from the bottom up,
    stopping at the first row that isn't one."""
    x1, y1, x2, y2 = box
    hsv = cv2.cvtColor(frame[y1:y2 + 4, x1:x2 + 4], cv2.COLOR_BGR2HSV)
    count = 0
    for row in range(ROWS - 1, -1, -1):          # bottom row first
        filled, grey = 0, True
        for col in range(COLS):
            cx, cy = cell_center(box, col, row)
            patch = hsv[cy - y1 - 3:cy - y1 + 3, cx - x1 - 3:cx - x1 + 3].reshape(-1, 3)
            if (patch[:, 2] >= CLEAR_V_MIN).mean() >= BLOCK_FILL:
                filled += 1
                grey = grey and float(np.median(patch[:, 1])) <= GARBAGE_SAT_MAX
        if filled != COLS - 1 or not grey:
            break
        count += 1
    return count


_OPENERS = None


def openers():
    """Every opener shape, indexed (loaded once)."""
    global _OPENERS
    if _OPENERS is None:
        _OPENERS = OpenerIndex(load_openers(), load_english())
    return _OPENERS


class OpenerDetector:
    """One player's opener for the current match (reset with the pipeline)."""

    def __init__(self, side, profile=None):
        self.side = side
        self.profile = profile or REFERENCE_PROFILE
        self.box = scale_box(LEFT_BOX if side == "left" else RIGHT_BOX, self.profile)
        self.placements = 0
        self.name = None
        self.name_en = None   # the same in English (Japanese where there's no English name)
        self._board = 0       # the board as last seen settled (a mask, see _mask)
        self._seen = None     # the board on the previous frame
        self.landed = []      # each piece that landed, as a mask (the hold case)
        self._reported = False   # _report_miss: once
        self._last_hold = None

    def on_frame(self, frame, t_in_match, placements=0, hold=None):
        """Call on every frame with the time since the match started, the
        placements confirmed on this frame and the piece kind in HOLD (or
        None). During the opening the board is compared every frame; returns
        the opener name when it becomes known or changes, else None."""
        self.placements += placements
        if t_in_match > OPENING_S or self.placements > MAX_PLACEMENTS:
            self._report_miss()
            return None
        self._last_hold = hold
        return self._check(frame, hold)

    def _report_miss(self):
        """Once per match, when the opening ends with no opener: what was on
        the board, the pieces as they landed and HOLD, in server.log (so a
        "not recognized" can be looked into)."""
        if self.name is not None or self._reported or not self._board:
            return
        self._reported = True
        import logging

        def draw(m):
            top = max((i // COLS for i in range(MASK_ROWS * COLS) if m >> i & 1), default=0)
            return "/".join("".join("#" if m >> (r * COLS + c) & 1 else "." for c in range(COLS))
                            for r in range(top, -1, -1))
        logging.getLogger("opener").info(
            "[%s] no opener: board %s | landed %s | hold %s | placements %d", self.side, draw(self._board),
            " ".join(draw(p) for p in self.landed), self._last_hold, self.placements)

    def _note_landing(self, mask):
        """A board the same two frames running that holds everything the
        last one did plus one tetromino: that piece landed."""
        settled = mask == self._seen
        self._seen = mask
        if not settled or mask == self._board:
            return
        new = mask & ~self._board
        if self._board & ~mask == 0 and _is_tetromino(new):
            self.landed.append(new)
        self._board = mask

    def on_placements(self, frame, count):
        """Check only when `count` placements were confirmed on this frame
        (kept for tests / callers without match time)."""
        if count <= 0 or self.placements >= MAX_PLACEMENTS:
            return None
        self.placements += count
        return self._check(frame)

    def _check(self, frame, hold=None):
        occupancy = read_occupancy(frame, self.box)
        lifted = garbage_rows(frame, self.box)
        if lifted:   # the shape sits on top of the garbage it was pushed up by
            occupancy = occupancy[lifted:] + [[False] * COLS for _ in range(lifted)]
        mask = _mask(occupancy)
        self._note_landing(mask)
        names = match_openers(occupancy, openers(), self.placements)
        if not names and self.name is None and self.landed:
            names = openers().match_with_hold(mask, self.landed, hold)
        if not names:
            return None
        name = shown_name(names)      # shapes shared by several openers: up to MAX_NAMES of them
        index = openers()
        # dict.fromkeys: two Japanese names can share one English name once its (…) is gone
        self.name_en = shown_name(list(dict.fromkeys(index.english.get(n, n) for n in names)), "en")
        if name != self.name:
            self.name = name
            return name
        return None
