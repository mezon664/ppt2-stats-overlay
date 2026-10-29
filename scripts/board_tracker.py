"""Piece-lock / line-clear / garbage-row event tracker.

Design (see docs/phase2_notes.md for rationale):
- `settled`: the confirmed, locked board. Only ever updated by confirmed events below.
- Each incoming raw frame reading is compared against `settled`. Cells that are
  non-empty in raw but empty in settled are "extra" cells: either the still-falling
  active piece, a piece that just locked but hasn't been merged yet, or noise.
- A connected 4-cell "extra" blob of one color that matches that color's known
  tetromino shape is a *lock candidate*. It must then appear unchanged for
  STABLE_FRAMES consecutive raw samples before being confirmed as a real lock
  (filters out the piece while it's still actively moving/rotating, and filters
  one-frame recognition glitches).
- Garbage-row additions (full grey rows) and line clears (a full non-garbage row
  disappearing with everything above shifting down) are detected and applied to
  `settled` directly — they never get matched against tetromino shapes, so they
  can't be miscounted as piece locks.
- Any "extra" blob that never resolves into a confirmed, shape-matching lock within
  a timeout is dropped and logged as `unmatched` for manual review, not counted.
"""
from collections import deque
from piece_shapes import matches_piece_shape
from board_read import EMPTY, GARBAGE, COLS, ROWS

STABLE_FRAMES = 3
LOCK_TIMEOUT_FRAMES = 20  # ~1.3s at 15fps; a candidate not confirmed by then is dropped


def connected_components(cells_by_color):
    """cells_by_color: dict[(r,c)] = label. Returns list of (label, frozenset(cells))."""
    visited = set()
    comps = []
    for pos, label in cells_by_color.items():
        if pos in visited:
            continue
        stack = [pos]
        comp = set()
        while stack:
            p = stack.pop()
            if p in visited or cells_by_color.get(p) != label:
                continue
            visited.add(p)
            comp.add(p)
            r, c = p
            for nr, nc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if (nr, nc) in cells_by_color and (nr, nc) not in visited:
                    stack.append((nr, nc))
        comps.append((label, frozenset(comp)))
    return comps


class BoardTracker:
    def __init__(self, name="board"):
        self.name = name
        self.settled = [[EMPTY for _ in range(COLS)] for _ in range(ROWS)]
        self.raw_history = deque(maxlen=STABLE_FRAMES)
        self.candidates = {}  # frozenset(cells) -> {"label":..., "first_seen": t, "age": n}
        self.events = []  # (time, type, data)
        self.unmatched_log = []
        self.piece_count = 0

    def _stable_raw(self):
        if len(self.raw_history) < STABLE_FRAMES:
            return None
        frames = list(self.raw_history)
        stable = [[None] * COLS for _ in range(ROWS)]
        for r in range(ROWS):
            for c in range(COLS):
                vals = [f[r][c] for f in frames]
                stable[r][c] = vals[-1] if all(v == vals[-1] for v in vals) else "?"
        return stable

    def _settled_full_rows(self):
        return [r for r in range(ROWS) if all(self.settled[r][c] != EMPTY for c in range(COLS))]

    def _apply_garbage_rows(self, stable, t):
        # a "garbage row": fully GARBAGE except at most one hole, newly present in `stable`
        # but not already reflected in settled at that row index.
        for r in range(ROWS):
            row = stable[r]
            if "?" in row:
                continue
            garbage_like = sum(1 for v in row if v == GARBAGE)
            non_empty = sum(1 for v in row if v != EMPTY)
            if garbage_like >= COLS - 1 and non_empty >= COLS - 1:
                if self.settled[r] != row and all(self.settled[r][c] in (EMPTY,) for c in range(COLS)):
                    self.settled[r] = list(row)
                    self.events.append((round(t, 2), "garbage_row_added", {"row": r}))

    def _apply_line_clears(self, stable, t):
        full_before = self._settled_full_rows()
        if not full_before:
            return
        # if a previously-full settled row is now empty/near-empty in stable, and the
        # rows above have shifted down to fill the gap, treat as line clear(s).
        cleared = [r for r in full_before if sum(1 for v in stable[r] if v != EMPTY) <= 2]
        if not cleared:
            return
        for r in sorted(cleared):
            del self.settled[r]
            self.settled.insert(0, [EMPTY] * COLS)
            self.events.append((round(t, 2), "line_clear", {"row": r}))
        # drop any in-flight candidates: their row coordinates are now stale
        self.candidates.clear()

    def update(self, raw_board, t):
        self.raw_history.append(raw_board)
        stable = self._stable_raw()
        if stable is None:
            return

        self._apply_line_clears(stable, t)
        self._apply_garbage_rows(stable, t)

        extra = {}
        for r in range(ROWS):
            for c in range(COLS):
                v = stable[r][c]
                if v in (EMPTY, GARBAGE, "?"):
                    continue
                if self.settled[r][c] == v:
                    continue
                extra[(r, c)] = v

        if len(extra) > 12:
            # More than one piece's worth of "new" cells appeared between confirmations.
            # This is not a single legitimate placement (that bug exists and was observed:
            # an undetected line-clear shift gets misread as several simultaneous piece
            # locks). Treat it as desync: snap settled to the current stable reading
            # instead of guessing, and log it for manual review rather than silently
            # mis-counting placements.
            self.events.append((round(t, 2), "resync", {"extra_cells": len(extra)}))
            for r in range(ROWS):
                for c in range(COLS):
                    if stable[r][c] != "?":
                        self.settled[r][c] = stable[r][c]
            self.candidates.clear()
            return

        comps = connected_components(extra)
        seen_this_frame = set()
        for label, cells in comps:
            if len(cells) != 4:
                continue
            seen_this_frame.add(cells)
            if cells not in self.candidates:
                self.candidates[cells] = {"label": label, "first_seen": t, "age": 0, "confirmed_run": 0}
            cand = self.candidates[cells]
            cand["age"] += 1
            if matches_piece_shape(label, cells):
                cand["confirmed_run"] += 1
            else:
                cand["confirmed_run"] = 0

            if cand["confirmed_run"] >= STABLE_FRAMES:
                for (r, c) in cells:
                    self.settled[r][c] = label
                self.piece_count += 1
                self.events.append((round(cand["first_seen"], 2), "piece_lock", {
                    "piece": label, "cells": sorted(cells), "confirmed_at": round(t, 2),
                }))
                del self.candidates[cells]

        # age out stale / abandoned candidates
        for cells in list(self.candidates.keys()):
            if cells not in seen_this_frame:
                cand = self.candidates[cells]
                if cand["age"] >= LOCK_TIMEOUT_FRAMES or True:
                    self.unmatched_log.append((round(t, 2), cand["label"], sorted(cells)))
                del self.candidates[cells]
