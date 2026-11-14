"""Mid-game T-spin setups (途中テンプレ) on your board, for the comments.

The setups are in assets/midgame_setups.json: each one's shape around its
T-slots just before the first T goes in ("#" a block, "." empty, "?"
either; top to bottom, the last row the one under the slots), how many lines
that first T-spin clears, and its English name.
- STSD, DT砲, TDアタック, キングクリムゾン, TスピンFIN: drawn by hand from
  Hard Drop Tetris Wiki's diagrams (2026-11-14).
- The rest: テトリステンプレ集＠テト譜, 中盤テンプレまとめ (some drawn by hand from
  their テト譜 or, for CC砲 / NiL-cross / ダークネスカズスペシャル, their pictures;
  永久機関 is the same shape as TSTタワー: one, "TSTタワー（永久機関）"),
  (https://w.atwiki.jp/tetrismaps/pages/506.html), each page's テト譜: the
  board right before its first T-spin, the columns of its T-spins +-1, from
  the lowest covered gap there up to the highest block (2026-11-14).
Both ways round (mirrored) and anywhere on the board; outside the board
counts as a block (walls, floor).

A setup is only called out when it's used: its shape was on the board (for
SEEN_READS reads running — not a piece passing by) and, within HOLD_S after
it was last seen, a T-spin clearing that many lines happens. When several
are on the board, the one with the most cells to it (the bigger setup) is
the one. After one is called out, none for COVER_S (the rest of a big setup
holds smaller ones). A shape alone says nothing (no guesses on screen).
"""
import json
import logging
from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

log = logging.getLogger(__name__)
SETUPS_PATH = Path(__file__).resolve().parent.parent / "assets" / "midgame_setups.json"
SEEN_READS = 2
BOARDS_KEPT = 6
HOLD_S = 3.0
COVER_S = 8.0
# the T-spins that clear that many lines (scripts/comments.py's kinds)
SPINS = {1: {"tss", "tsm"}, 2: {"tsd", "tsmd"}, 3: {"tst"}}

SETUPS = {}
SHAPES = []      # (name, filled mask, empty mask), biggest first
SIZE = {}        # name -> cells it says something about


def _masks(rows):
    filled = np.array([[c == "#" for c in r] for r in rows])
    empty = np.array([[c == "." for c in r] for r in rows])
    return filled, empty


def relax(rows):
    """A setup told by its empty space (user: the roof's exact shape, the
    columns beside it, the rows below shouldn't matter): kept are the covered
    empty cells (a block above them, or blocks on both sides: the slots the
    T's go into), the empty cells right beside those (the way in, the T's arms),
    and the blocks touching them (walls, floor, the roof cell over a slot —
    with the diagonal ones, the T-spin corners). Every other cell: either."""
    h, w = len(rows), len(rows[0])
    body = rows[:-1]   # (the last row is the one under the setup)
    # inside: an empty cell with a block above it (under a roof), or with blocks
    # on both sides in its row (in a slot or a well, open at the top or not)
    covered = {(y, x) for y in range(len(body)) for x in range(w)
               if body[y][x] == "." and (any(body[yy][x] == "#" for yy in range(y))
                                         or ("#" in body[y][:x] and "#" in body[y][x + 1:]))}
    space = set(covered)
    for y, x in covered:
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            yy, xx = y + dy, x + dx
            if 0 <= yy < len(body) and 0 <= xx < w and body[yy][xx] == ".":
                space.add((yy, xx))
    out = []
    for y in range(h):
        line = ""
        for x in range(w):
            c = rows[y][x]
            # (blocks right next to it only: the diagonal ones fixed the roof's
            # piece — a user's マジカルキー went unnamed)
            near = any((y + dy, x + dx) in space for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)))
            if (y, x) in space:
                line += "."
            elif c == "#" and near:
                line += "#"
            else:
                line += "?"
        out.append(line)
    # (rows and columns left with nothing to check go)
    while out and set(out[0]) == {"?"}:
        out.pop(0)
    while out and set(out[-1]) == {"?"}:
        out.pop()
    keep = [x for x in range(w) if any(r[x] != "?" for r in out)]
    return ["".join(r[x] for x in keep) for r in out] if keep else rows


def load(setups=None):
    global SETUPS, SHAPES, SIZE
    if setups is None:
        setups = json.loads(SETUPS_PATH.read_text(encoding="utf-8"))
    SETUPS = setups
    loose = {n: relax(s["rows"]) for n, s in setups.items()}
    SIZE = {n: sum(c != "?" for r in rows for c in r) for n, rows in loose.items()}
    shapes = []
    for name, s in setups.items():
        rows = loose[name]
        for shape in (rows, [r[::-1] for r in rows]):
            shapes.append((name,) + _masks(shape))
    SHAPES = sorted(shapes, key=lambda t: -SIZE[t[0]])


def find(grid):
    """The setups on a board: grid is ROWS x 10, True = a block, row 0 the top."""
    grid = np.asarray(grid, dtype=bool)
    rows, cols = grid.shape
    found = set()
    boards = {}
    for name, filled, empty in SHAPES:
        if name in found:
            continue
        h, w = filled.shape
        board = boards.get(h)
        if board is None:
            # room around: empty above, a wall each side, the floor (one row) under
            board = np.ones((rows + h + 1, cols + 2), dtype=bool)
            board[:h, 1:-1] = False
            board[h:h + rows, 1:-1] = grid
            boards[h] = board
        if w > cols + 2:
            continue
        win = sliding_window_view(board, (h, w))
        ok = (win | ~filled).all(axis=(2, 3)) & ~(win & empty).any(axis=(2, 3))
        if ok.any():
            found.add(name)
    return found


def best(names):
    """The biggest of these setups (or None)."""
    return max(names, key=lambda n: SIZE[n], default=None)


class Watch:
    """Your board read after read, and the T-spins as they come: which setup was used."""

    def __init__(self):
        self.reset()

    def reset(self):
        self._run = {}     # name -> reads running it's been seen
        self._seen = {}    # name -> last time seen (for SEEN_READS reads or more)
        self._quiet_until = 0.0
        self._last_key, self._last_found = None, set()
        self._boards = []   # the last few different boards: (time, grid) — logged at a T-spin with no setup

    def see(self, grid, now):
        if grid is None:
            return
        # (the board changes a couple of times a second, it's read ten: an
        # unchanged one isn't matched against every setup again — ~4 ms each)
        key = np.asarray(grid, dtype=bool).tobytes()
        if key != self._last_key:
            self._last_key, self._last_found = key, find(grid)
            self._boards = (self._boards + [(now, np.asarray(grid, dtype=bool).copy())])[-BOARDS_KEPT:]
            for name in self._last_found - set(n for n, r in self._run.items() if r):
                log.info("mid-game setup on your board: %s", name)
        here = self._last_found
        for name in SETUPS:
            self._run[name] = self._run.get(name, 0) + 1 if name in here else 0
            if self._run[name] >= SEEN_READS:
                self._seen[name] = now

    def spun(self, spin, now):
        """A T-spin of yours (comments' kind: "tsd", "tst", ...): the setup it came from, or None."""
        if now < self._quiet_until:
            return None
        used = [n for n, seen in self._seen.items()
                if now - seen <= HOLD_S and spin in SPINS.get(SETUPS[n]["lines"], ())]
        name = best(used)
        if name:
            self._seen.clear()
            self._quiet_until = now + COVER_S
            # (the board with it too, and what else matched: to see a wrong name's why)
            log.info("mid-game setup used: %s (%s; also matched: %s); the boards just before it:\n%s", name, spin,
                     ", ".join(n for n in used if n != name) or "none",
                     "\n\n".join(f"t-{now - t:.2f}s\n" + board_text(g) for t, g in self._boards[-3:]))
        elif spin in ("tsd", "tst"):
            # (none of them: the boards before it, to see why — a user's setups went unnamed)
            log.info("a %s with no mid-game setup seen; the boards just before it:\n%s", spin,
                     "\n\n".join(f"t-{now - t:.2f}s\n" + board_text(g) for t, g in self._boards[-3:]))
        return name


def board_text(grid):
    """A board as text (# a block), its empty top rows left out."""
    rows = ["".join("#" if c else "." for c in row) for row in np.asarray(grid, dtype=bool)]
    while rows and set(rows[0]) == {"."}:
        rows.pop(0)
    return "\n".join(rows)


def english(name):
    return SETUPS[name]["en"]


def names(name, lang="ja"):
    """What a setup is called in comments: its name, and the shorter ones it also goes by ("also")."""
    first = english(name) if lang == "en" else name
    return [first] + list(SETUPS[name].get("also", []))


if SETUPS_PATH.exists():
    load()
