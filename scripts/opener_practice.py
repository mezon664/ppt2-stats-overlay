"""開幕テンプレ練習: can the chosen opener be built with this game's first
bag, and where does each piece go.

The opener's shapes are the wiki's tags (assets/openers.json, see
opener_detect): the first bag as it stands when done, with no colors. With
the bag's order known (the piece in play and the five in NEXT give six; a bag
holds each of the seven once, so the last is the one missing), a search tries
each piece in turn — placed, or put in HOLD and the next one placed — on every
spot the piece can really get to: moved and turned the game's way (SRS, with
its wall kicks) from where it appears, and dropped. A spot counts when the
piece lies wholly inside the shape. No row may fill before the last piece (it
would clear and break the shape); a tag's full rows are the T-spin at the end,
and the T gets into its slot the game's way too.

A plan is the pieces in order, each with its cells and whether HOLD is
pressed first. Rows go up (row 0 = the bottom), like opener_detect's.
"""
import json
import itertools
from functools import lru_cache
from pathlib import Path

from fumen import decode

OPENERS_PATH = Path(__file__).resolve().parent.parent / "assets" / "openers.json"
COLS = 10
TOP = 24            # rows the search uses (the board's 20 and room above where pieces appear)
PIECES = "IOTSZJL"

# SRS: each piece's four turns in its box, as the guideline draws them (rows
# down), turned into (column, row up) offsets from the box's top-left.
_STATES = {
    "T": (".X.|XXX|...", ".X.|.XX|.X.", "...|XXX|.X.", ".X.|XX.|.X."),
    "J": ("X..|XXX|...", ".XX|.X.|.X.", "...|XXX|..X", ".X.|.X.|XX."),
    "L": ("..X|XXX|...", ".X.|.X.|.XX", "...|XXX|X..", "XX.|.X.|.X."),
    "S": (".XX|XX.|...", ".X.|.XX|..X", "...|.XX|XX.", "X..|XX.|.X."),
    "Z": ("XX.|.XX|...", "..X|.XX|.X.", "...|XX.|.XX", ".X.|XX.|X.."),
    "I": ("....|XXXX|....|....", "..X.|..X.|..X.|..X.", "....|....|XXXX|....", ".X..|.X..|.X..|.X.."),
    "O": (".XX.|.XX.|....", ".XX.|.XX.|....", ".XX.|.XX.|....", ".XX.|.XX.|...."),
}
SHAPES = {k: tuple(tuple((c, -r) for r, row in enumerate(s.split("|")) for c, ch in enumerate(row) if ch == "X")
                   for s in states) for k, states in _STATES.items()}
# wall kicks (x, y up), by (from turn, to turn); turns 0 / R=1 / 2 / L=3
_JLSTZ = {(0, 1): ((0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)), (1, 0): ((0, 0), (1, 0), (1, -1), (0, 2), (1, 2)),
          (1, 2): ((0, 0), (1, 0), (1, -1), (0, 2), (1, 2)), (2, 1): ((0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)),
          (2, 3): ((0, 0), (1, 0), (1, 1), (0, -2), (1, -2)), (3, 2): ((0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)),
          (3, 0): ((0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)), (0, 3): ((0, 0), (1, 0), (1, 1), (0, -2), (1, -2))}
_I = {(0, 1): ((0, 0), (-2, 0), (1, 0), (-2, -1), (1, 2)), (1, 0): ((0, 0), (2, 0), (-1, 0), (2, 1), (-1, -2)),
      (1, 2): ((0, 0), (-1, 0), (2, 0), (-1, 2), (2, -1)), (2, 1): ((0, 0), (1, 0), (-2, 0), (1, -2), (-2, 1)),
      (2, 3): ((0, 0), (2, 0), (-1, 0), (2, 1), (-1, -2)), (3, 2): ((0, 0), (-2, 0), (1, 0), (-2, -1), (1, 2)),
      (3, 0): ((0, 0), (1, 0), (-2, 0), (1, -2), (-2, 1)), (0, 3): ((0, 0), (-1, 0), (2, 0), (-1, 2), (2, -1))}
SPAWN = (3, 21)     # the box's top-left where a piece appears (columns 3-6, the rows just above the 20)


def kicks(piece, a, b):
    if piece == "O":
        return ((0, 0),)
    return (_I if piece == "I" else _JLSTZ)[(a, b)]


def cells_at(piece, turn, x, y):
    return frozenset((x + dx, y + dy) for dx, dy in SHAPES[piece][turn])


def _free(cells, board):
    return all(0 <= x < COLS and 0 <= y < TOP and (x, y) not in board for x, y in cells)


def fits(piece, room):
    """Every way the piece lies wholly inside `room` (a set of cells)."""
    out = set()
    for shape in set(SHAPES[piece]):
        ax, ay = shape[0]
        for x, y in room:   # the shape's first cell on each cell of the room
            cells = frozenset((x + dx - ax, y + dy - ay) for dx, dy in shape)
            if cells <= room:
                out.add(cells)
    return out


@lru_cache(maxsize=200000)
def landing_spots(piece, board):
    """{cells: (turn, x, y)} for every place the piece can come to rest on
    `board` (a frozenset of filled cells), moved left / right / down and turned
    either way with SRS kicks from where it appears."""
    start = (0, SPAWN[0], SPAWN[1])
    if not _free(cells_at(piece, *start), board):
        return {}
    seen, todo, spots = {start}, [start], {}
    while todo:
        turn, x, y = todo.pop()
        here = cells_at(piece, turn, x, y)
        if not _free(cells_at(piece, turn, x, y - 1), board):
            spots.setdefault(here, (turn, x, y))
        nxt = [(turn, x - 1, y), (turn, x + 1, y), (turn, x, y - 1)]
        for to in ((turn + 1) % 4, (turn + 3) % 4):
            for kx, ky in kicks(piece, turn, to):
                if _free(cells_at(piece, to, x + kx, y + ky), board):
                    nxt.append((to, x + kx, y + ky))
                    break
        for s in nxt:
            if s not in seen and _free(cells_at(piece, *s), board):
                seen.add(s)
                todo.append(s)
    return spots


def bag_order(seen):
    """The first bag's seven from the first pieces seen (in order): with six
    known the seventh is the one missing. None if they can't be a bag."""
    seen = list(seen)[:7]
    if len(set(seen)) != len(seen) or any(p not in PIECES for p in seen) or len(seen) < 6:
        return None
    return seen + [p for p in PIECES if p not in seen] if len(seen) == 6 else seen


def is_t_spin(cells, board, rows):
    """A T at `cells` going into `board` is a T-spin clearing `rows`: pointing
    down (its flat side in the upper row, as a T-spin Double has it; one row:
    pointing down too, or up / sideways for a Single or Mini), touching every
    row it clears, and 3 of the 4 corners around its center blocked (the
    game's rule; the floor and walls count)."""
    cells = set(cells)
    if not all(any(y == r for _, y in cells) for r in rows):
        return False
    center = next(c for c in cells if sum((c[0] + dx, c[1] + dy) in cells for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))) == 3)
    cx, cy = center
    if len(rows) >= 2 and not ((cx - 1, cy) in cells and (cx + 1, cy) in cells and (cx, cy - 1) in cells):
        return False
    blocked = sum(1 for dx in (-1, 1) for dy in (-1, 1)
                  if not (0 <= cx + dx < COLS) or cy + dy < 0 or (cx + dx, cy + dy) in board)
    return blocked >= 3


@lru_cache(maxsize=4096)
def tilings(target):
    """Every way to cut `target` (a frozenset of cells) into tetrominoes, as
    tuples of (piece, cells)."""
    out = []

    def cut(left, parts):
        if not left:
            out.append(tuple(parts))
            return
        x0, y0 = min(left, key=lambda c: (c[1], c[0]))   # the lowest, leftmost cell left
        for piece in PIECES:
            for shape in set(SHAPES[piece]):
                for ax, ay in shape:   # each of the shape's cells on it
                    cells = frozenset((x0 + dx - ax, y0 + dy - ay) for dx, dy in shape)
                    if cells <= left:
                        cut(left - cells, parts + [(piece, cells)])
    if len(target) % 4 == 0:
        cut(target, [])
    return tuple(dict.fromkeys(tuple(sorted(t, key=lambda pc: sorted(pc[1]))) for t in out))


def _cuts(target, pieces, colors=None):
    """The cuts of `target` into the pieces available (counted), with the
    T-spin at the end if it has full rows; colors: {cell: piece} the cut
    must keep (a colored テト譜)."""
    have = {p: list(pieces).count(p) for p in PIECES}
    cuts = [t for t in tilings(target) if all(sum(1 for p, _ in t if p == k) <= have[k] for k in PIECES)]
    if colors:
        cuts = [t for t in cuts if all(colors.get(c, p) == p for p, cells in t for c in cells)]
    full = {y for _, y in target if all((x, y) in target for x in range(COLS))}
    if full:   # the shape's full rows are its T-spin: only cuts with that T
        cuts = [t for t in cuts if any(p == "T" and is_t_spin(cells, target - cells, full) for p, cells in t)]
    return cuts


def _search(target, queue, cuts, placed, i, hold):
    """The rest of a plan from `placed` ((piece, cells) down), queue[i] in
    play and `hold` in HOLD; None if there's none."""
    full = {y for _, y in target if all((x, y) in target for x in range(COLS))}

    @lru_cache(maxsize=None)
    def go(placed, i, hold):
        board = frozenset(c for _, cells in placed for c in cells)
        if board == target:
            return ()
        left = [t for t in cuts if placed <= set(t)]
        if not left:
            return None
        options = []
        if i < len(queue):
            options.append((queue[i], i + 1, hold, False))
            if hold is None and i + 1 < len(queue):
                options.append((queue[i + 1], i + 2, queue[i], True))
            elif hold is not None and hold != queue[i]:
                options.append((hold, i + 1, queue[i], True))
        for piece, ni, nh, held in options:
            wanted = {cells for t in left for p, cells in t if p == piece and (p, cells) not in placed}
            if not wanted:
                continue
            spots = landing_spots(piece, board)
            for cells in wanted:
                if cells not in spots:
                    continue
                after = board | cells
                # a row filling early clears and breaks the shape; the last
                # piece of a shape with full rows is its T-spin
                if after != target and any(all((x, y) in after for x in range(COLS)) for y in {y for _, y in cells}):
                    continue
                if after == target and full and not (piece == "T" and is_t_spin(cells, board, full)):
                    continue
                rest = go(placed | {(piece, cells)}, ni, nh)
                if rest is not None:
                    return ({"piece": piece, "cells": sorted(cells), "hold": held},) + rest
        return None

    plan = go(frozenset(placed), i, hold)
    return list(plan) if plan is not None else None


def solve(target, queue, done=(), colors=None):
    """A plan building `target` (cells, row 0 the bottom) from `queue` (the
    pieces in order) with HOLD: [{"piece", "cells", "hold"}], hold = press
    HOLD first. None if it can't be done.

    Only the cuts of the shape into pieces this queue has are tried (a
    first bag has each piece once), each piece only where it can get to."""
    target, queue = frozenset(target), tuple(queue)
    cuts = _cuts(target, queue, colors)
    if not cuts:
        return None
    placed, i, hold = replay(queue, done)
    if not all(any(pc in t for t in cuts) for pc in placed):
        return None
    rest = _search(target, queue, cuts, placed, i, hold)
    return list(done) + rest if rest is not None else None


def solve_from(target, queue, board, i, hold, colors=None):
    """The rest of a plan for `target` from a board already part built (in any
    order): its cells must be whole pieces of one of the cuts. queue[i] is
    the piece in play, `hold` the one in HOLD (or None). None if there's none."""
    target, queue, board = frozenset(target), tuple(queue), frozenset(map(tuple, board))
    if not board <= target:
        return None
    cuts = _cuts(target, queue + ((hold,) if hold else ()), colors)
    starts = []
    for t in cuts:
        placed = frozenset(pc for pc in t if pc[1] <= board)
        if frozenset(c for _, cells in placed for c in cells) == board and placed not in starts:
            starts.append(placed)
    for placed in starts:
        rest = _search(target, queue, cuts, placed, i, hold)
        if rest is not None:
            return rest
    return None


def opener_shapes(name, path=OPENERS_PATH):
    """The opener's shapes (wiki tags, mirrored and hold variants included)
    as cell sets, row 0 the bottom; by its shown name (opener_detect.screen_name)."""
    from opener_detect import screen_name
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for op in data["openers"]:
        if screen_name(op.get("display") or op["name"]) != name:
            continue
        for f in op["shapes"]:
            rows = decode(f)[0].board_with_piece()
            cells = frozenset((x, y) for y, r in enumerate(rows) for x, v in enumerate(r) if v)
            if cells and len(cells) % 4 == 0 and cells not in out:
                out.append(cells)
    return out


def plan_for(name, queue, shapes=None, done=()):
    """(shape, plan) for the first of the opener's shapes this queue builds
    (only `shapes` if given; starting with the steps `done`), or (None, None)."""
    for shape in shapes or opener_shapes(name):
        plan = solve(shape, queue, done)
        if plan is not None:
            return shape, plan
    return None, None


def replay(queue, steps):
    """(placed, next queue index, hold) after the plan's `steps` were done."""
    i, hold, placed = 0, None, set()
    for st in steps:
        if st["hold"]:
            if hold is None:
                hold, i = queue[i], i + 1
            else:
                hold = queue[i]
        i += 1
        placed.add((st["piece"], frozenset(map(tuple, st["cells"]))))
    return frozenset(placed), i, hold




# --- following a match: what to show (data_server, state["practice"]) ---
import threading


class Practice:
    """Your practice in the match going on: the deck (candidates() of it),
    the pieces read off NEXT, and the plan from the board as it stands.

    Each time the board settles into something new, the rest is worked out
    again from it, trying the deck's openers and forms in their order — so
    pieces put down in another order than the guide's, or the mirrored
    shape, or another opener of the deck, still count. update() is called
    ~10 times a second and never waits: the search runs on its own thread
    and its answer is picked up on a later call.

    status: "wait" (the order isn't known yet / still working it out),
    "ok" (the guide shows the next piece), "maybe" (only with some of the
    pieces not seen yet: decided as they show), "no" (nothing in the deck
    with these pieces), "off" (the board isn't part of any of them), "done".

    Once the opener is built, the wiki's 派生 of it (routes) go on from there:
    the same statuses with "route" set, plus "end" (the board left every
    route), "stuck" (still on a route, but no way on was found: a Perfect
    Clear that clears rows on the way isn't searched) and "lost" (the piece
    order was lost, nothing is guided)."""

    def __init__(self):
        self._key = None
        self.target_key = None
        self._retry, self._undo = False, None

    def _start(self, fn):
        box = {"ready": False}

        def run():
            try:
                box["out"] = fn()
            except Exception:   # never take the server down over a plan
                import logging
                logging.getLogger("practice").exception("practice search failed")
                box["out"] = None
            box["ready"] = True
        threading.Thread(target=run, daemon=True).start()
        return box

    def update(self, cands, match_key, seen, from_start, board, hold, placed=None, routes=None, live=None):
        """cands: candidates(deck) ([] = off). match_key: changes with each
        match. seen: the pieces in the order they came through NEXT;
        from_start: its first is the match's first piece. board: the settled
        cells (x, row up). hold: the piece in HOLD or None. placed: pieces
        placed so far (None: from the board). routes: {opener: [Route]}, the
        派生 to go on with. live: the cells read just now (a falling piece
        too): the guide moves on the moment the piece it shows is there,
        without waiting for the board to settle. Returns the state to show."""
        if not cands:
            self._key = None
            return None
        key = (id(cands), match_key)
        if key != self._key:
            self._key, self._job, self._asked = key, None, None
            self.cands, self.pick, self.target, self.plan, self.status = cands, None, None, None, "wait"
            self.routes, self.on_route, self.opener = routes or {}, False, None
            self.target_key = None
            self._retry, self._undo = False, None
        if self.on_route and not from_start:
            self._job, self._asked = None, None
            self.status, self.plan = "lost", None   # (no index into the order any more: no guess)
            return self._out()
        if not from_start or len(seen) < 6 or bag_order(seen[:6]) is None:
            return self._out()
        queue = tuple(seen) if len(seen) >= 7 else tuple(bag_order(seen[:6]))
        board = frozenset(map(tuple, board))
        n = len(board) // 4 if placed is None else placed
        if self._job is not None and self._job["ready"]:
            out, self._job = self._job["out"], None
            if out is not None and out[0] == self._asked:
                if out[1] == "wait" and self.on_route and self.plan:
                    self._retry = True      # still looking: the guide shown stays
                else:
                    self._retry, self._undo = False, None
                    _, self.status, self.pick, self.target, self.plan = out
        self._advance(None if live is None else frozenset(map(tuple, live)))
        if self.on_route:
            return self._follow_route(board, queue, n, hold)
        if self.status == "done":
            if self.pick and self.routes.get(self.pick[0]):
                self.on_route, self.opener = True, self.pick[0]
                self.base = self.target.cells if self.target is not None else None
                self._job, self._asked = None, None
                return self._follow_route(board, queue, n, hold)
            return self._out()
        if self.plan and self.status in ("ok", "maybe") and len(self.plan) == 1 and self._last_cleared(board, n):
            self.status, self.plan = "done", []   # the last piece went in and rows cleared
            return self._out()
        if n * 4 != len(board):
            return self._out()   # mid-change (counts and board not in step yet): wait
        ask = (board, queue, n, hold)
        if self._job is None and ask != self._asked:
            self._asked = ask
            self._job = self._start(lambda: (ask,) + self._plan(board, queue, n, hold))
        return self._out()

    def _advance(self, live):
        """The piece shown is on the board: on to the next step of the plan
        at once (the plan is worked out again when the board has settled). If
        it was only passing through, the step comes back."""
        if live is None:
            return
        if self._undo is not None:
            cells, plan = self._undo
            if not cells <= live:
                self.plan, self._undo = plan, None
                return
        if not self.plan or self.status not in ("ok", "maybe") or len(self.plan) < 2:
            return
        cells = frozenset(map(tuple, self.plan[0]["cells"]))
        if not cells <= live:
            return
        if any(all((x, y) in live for x in range(COLS)) for y in {y for _, y in cells}):
            return      # (rows clear: what's next moves down, so it waits for the new plan)
        self._undo = (cells, self.plan)
        self.plan = self.plan[1:]

    def _last_cleared(self, board, n):
        """The board is the shape with its full rows gone, and the count of
        pieces says rows did go (the next piece showing above the board, or a
        last piece put elsewhere, isn't that)."""
        cells = self.target.cells
        left = after_clear(cells)
        gone = n * 4 - len(board)
        return left != cells and board == left and gone > 0 and gone % 10 == 0

    def _follow_route(self, board, queue, n, hold):
        """On a route: asks for a plan when the board settles on something new."""
        gone = n * 4 - len(board)
        if gone < 0 or gone % 10:
            return self._out()      # mid-change (a falling piece or a clear): wait
        ask = (board, queue, n, hold)
        if self._job is None and (self.status == "wait" or self._retry) and ask == self._asked:
            self._asked = None      # the look over the pages ran out of time: on from where it got to
        if self._job is None and ask != self._asked:
            self._asked = ask
            self._job = self._start(lambda: (ask,) + self._route_plan(board, queue, n, hold))
        return self._out()

    def _route_plan(self, board, queue, n, hold):
        """(status, pick, target, plan) on the routes from this board: the
        first of their pages (route in your order, the one followed first)
        that the board is part of and the pieces seen can go on to."""
        routes = self.routes.get(self.opener, [])
        now = self.pick[1] if self.pick else None
        order = sorted(routes, key=lambda r: r.name != now)
        if not board:
            return "done", self.pick, None, None    # a Perfect Clear
        i = n + (1 if hold else 0)
        import time
        until = time.monotonic() + ROUTE_SEARCH_S
        key = (board, queue, n, hold)
        scan = getattr(self, "_scan", None)
        start, reached, inside = scan[1:] if scan and scan[0] == key else (0, False, False)
        now_key = self.target_key
        pages = [(r, t) for r in order for t in r.points]
        pages.sort(key=lambda rt: rt[1].key() != now_key)      # the page being followed first
        for k in range(start, len(pages)):
            r, t = pages[k]
            reached = reached or t.cells == board
            for rows in page_rows(t.cells, board):
                if not _colors_whole(t, board, rows):
                    continue
                got = plan_towards(t.cells, queue, board, i, hold, t.colors, rows, until)
                if got is not None and got[0]:
                    self._scan = None
                    self.target_key = t.key()
                    view = frozenset((x, rows.index(y)) for x, y in t.cells if y in rows)
                    return ("ok" if got[1] else "maybe"), (self.opener, r.name), Target(view), list(got[0])
                if time.monotonic() > until:    # (a page too big for one look is passed over)
                    self._scan = (key, k if k > start else k + 1, reached, inside)
                    return "wait", self.pick, None, None
                inside = inside or _fits_page(t, board, rows, until)
        self._scan = None
        if inside:
            return "stuck", self.pick, None, None
        if reached or board == getattr(self, "base", None) or board in opener_starts(self.opener):
            # the opener stands (its T may still go in), with no route on from
            # this board: not off anything, and it's looked at again as it changes
            return "done", self.pick, None, None
        return "end", self.pick, None, None

    def _order(self):
        """(pick, Target) in the deck's order, the one followed now first."""
        out = [((o, f), t) for o, f, ts in self.cands for t in ts]
        if self.target is not None:
            out.sort(key=lambda pt: pt[1].key() != self.target.key())
        return out

    def _plan(self, board, queue, n, hold):
        """(status, pick, target, plan) from this board."""
        i = n + (1 if hold else 0)   # queue[i]: the piece in play
        order = self._order()
        for pick, t in order:
            if board == t.cells:
                if hold is None:    # a shape on the way to a bigger one of the same opener isn't the end
                    for p2, t2 in order:
                        if p2[0] == pick[0] and board < t2.cells:
                            more = solve_from(t2.cells, queue, board, i, hold, t2.colors)
                            if more is not None:
                                return "ok", p2, t2, more
                return "done", pick, t, []
            plan = solve_from(t.cells, queue, board, i, hold, t.colors)
            if plan is not None:
                return "ok", pick, t, plan
        # with a piece not seen yet: the first in the deck's order that some
        # (or every) next piece builds
        best = None
        for pick, t in order:
            works = [solve_from(t.cells, queue + (e,), board, i, hold, t.colors) for e in PIECES]
            good = [w for w in works if w is not None]
            if len(good) == len(PIECES):
                return "ok", pick, t, good[0]
            if good and best is None:
                best = ("maybe", pick, t, good[0])
        if best:
            return best
        if not any(board <= t.cells for _, t in order):
            return "off", self.pick, self.target, None
        return "no", self.pick, self.target, None

    def _out(self):
        out = {"status": self.status}
        names = {o for o, _, _ in self.cands}
        out["single"] = len(names) == 1     # one opener: the words say if it builds
        if self.pick:
            out["name"], out["form"] = self.pick
        elif len(names) == 1:
            out["name"] = next(iter(names))
        if self.target is not None:
            out["shape"] = sorted(self.target.cells)
        if self.plan and self.status in ("ok", "maybe"):
            out["next"] = dict(self.plan[0])
            out["left"] = len(self.plan)
        if self.on_route:
            out["route"] = True
            if self.status == "maybe":
                out.pop("left", None)   # (how many more depends on pieces not seen)
        return out


# --- the deck: openers in order, each with its forms (形) -------------------
# A form is the wiki's shapes for that opener, or the user's own (a テト譜).
# What counts as set up (the same rule as the wiki's setup rates for first-bag
# openers — 開幕TSD Flat Top's 61.67% / 66.67% come out exactly): the shape
# built from the first bag (and the 8th piece, with HOLD); for a shape whose
# rows are full (its T-spin), the board just before the T goes in.
from fumen import PIECES as FUMEN_PIECES

DECK_PATH = Path(__file__).resolve().parent.parent / "config" / "practice_deck.json"
WIKI_FORM = "wiki"
MIRROR_PIECE = {"L": "J", "J": "L", "S": "Z", "Z": "S"}


def mirror_cells(cells):
    return frozenset((COLS - 1 - x, y) for x, y in cells)


def setup_targets(cells):
    """What counts as set up for a finished shape: itself, or (full rows: its
    T-spin) each board just before a T-spin T goes in."""
    cells = frozenset(cells)
    rows = {y for _, y in cells if all((x, y) in cells for x in range(COLS))}
    if not rows:
        return [cells]
    # (sorted: a set's order changes from run to run, and the first is tried first)
    return sorted((cells - c for p, c in {pc for t in tilings(cells) for pc in t}
                   if p == "T" and is_t_spin(c, cells - c, rows)), key=sorted)


class Target:
    """One shape to build: its cells, and the piece of each cell when the
    form says (a colored テト譜), else None."""
    __slots__ = ("cells", "colors")

    def __init__(self, cells, colors=None):
        self.cells, self.colors = frozenset(cells), colors

    def mirrored(self):
        colors = None if self.colors is None else {(COLS - 1 - x, y): MIRROR_PIECE.get(p, p)
                                                   for (x, y), p in self.colors.items()}
        return Target(mirror_cells(self.cells), colors)

    def key(self):
        return (tuple(sorted(self.cells)), tuple(sorted(self.colors.items())) if self.colors else None)


def fumen_targets(fumen):
    """A form's own テト譜: its last page, as setup targets. Pieces drawn in
    color must be those pieces; gray (or a fumen without colors) any."""
    pages = decode(fumen.strip())
    rows = pages[-1].board_with_piece()
    cells = {(x, y): v for y, r in enumerate(rows) for x, v in enumerate(r) if v}
    colored = {c: FUMEN_PIECES[v] for c, v in cells.items() if FUMEN_PIECES.get(v) not in (None, "X")}
    out = []
    for t in setup_targets(cells.keys()):
        colors = {c: p for c, p in colored.items() if c in t}
        out.append(Target(t, colors if colors else None))
    return out


# A form painted on the settings' board: rows bottom first, ten characters
# each, "." empty, a piece's letter, or "X" for gray (any piece).
MAX_PAINT_CELLS = 32    # 8 pieces: the first bag and the next one


def paint_rows(cells):
    """{(x, y): piece or "X"} as the rows a form keeps."""
    top = max((y for _, y in cells), default=-1)
    return ["".join(cells.get((x, y), ".") for x in range(COLS)) for y in range(top + 1)]


def paint_cells(rows):
    return {(x, y): v for y, row in enumerate(rows) for x, v in enumerate(row) if v != "."}


def paint_targets(rows):
    """A painted form as setup targets (as fumen_targets)."""
    cells = paint_cells(rows)
    colored = {c: v for c, v in cells.items() if v != "X"}
    out = []
    for t in setup_targets(cells.keys()):
        colors = {c: p for c, p in colored.items() if c in t}
        out.append(Target(t, colors if colors else None))
    return out


def paint_problem(rows):
    """Why this painting can't be a form: "empty", "count" (not whole
    pieces), "big" (more than 8 pieces), "shape" (the colors don't make
    pieces, or full rows with no T-spin); None if it can."""
    cells = paint_cells(rows)
    if not cells:
        return "empty"
    if len(cells) % 4:
        return "count"
    if len(cells) > MAX_PAINT_CELLS:
        return "big"
    colors = {c: v for c, v in cells.items() if v != "X"}

    @lru_cache(maxsize=None)
    def tiles(room):
        if not room:
            return True
        low = min(room, key=lambda c: (c[1], c[0]))
        return any(low in part and all(colors.get(c, p) == p for c in part) and tiles(room - part)
                   for p in PIECES for part in fits(p, room))
    if not tiles(frozenset(cells)):
        return "shape"
    targets = [t for t in paint_targets(rows)
               if tiles(frozenset(t.cells))]
    return None if targets else "shape"


def _sides(shapes):
    """The wiki's shapes split into one side and the mirrored others."""
    a, b = [], []
    for c in shapes:
        (b if mirror_cells(c) in a else a).append(c)
    return a, b


def form_targets(opener, form, mirror):
    """The targets of one form (deck entry): [Target], mirrored ones after
    (when `mirror`)."""
    if form.get("paint"):
        try:
            base = paint_targets(form["paint"])
        except Exception:
            return []
        return base + ([t.mirrored() for t in base] if mirror else [])
    if form.get("fumen"):
        try:
            base = fumen_targets(form["fumen"])
        except Exception:
            return []
        return base + ([t.mirrored() for t in base] if mirror else [])
    # in the wiki's order (its main shape first), each with its mirror right
    # after: a variant used to come before the main shape's mirror, and was
    # guided on bags the main shape builds mirrored
    shapes = opener_shapes(opener)
    out, have = [], set()
    for c in (shapes if mirror else _sides(shapes)[0]):
        for t in setup_targets(c):
            for cells in ((t, mirror_cells(t)) if mirror else (t,)):
                if cells not in have:
                    have.add(cells)
                    out.append(Target(cells))
    return out


def default_deck():
    return {"mode": "deck", "mirror": True, "openers": []}


def new_entry(opener):
    return {"name": opener, "forms": [{"name": "Wiki", "source": WIKI_FORM, "on": True}]}


def load_deck(path=None):
    try:
        deck = json.loads(Path(path or DECK_PATH).read_text(encoding="utf-8"))
        if not isinstance(deck, dict) or not isinstance(deck.get("openers"), list):
            raise ValueError
    except (OSError, ValueError):
        return default_deck()
    deck.setdefault("mirror", True)
    if deck.get("mode") not in ("deck", "single"):
        deck["mode"] = "deck"
    # forms added before they became routes (2巡目以降) go on as your routes
    for entry in deck["openers"] + list(deck.get("single_forms", {}).values()):
        mine = [f for f in entry.get("forms", []) if f.get("source") != WIKI_FORM]
        if mine:
            entry["forms"] = [f for f in entry["forms"] if f.get("source") == WIKI_FORM] or new_entry(entry["name"])["forms"]
            entry.setdefault("own_routes", []).extend(
                {k: f[k] for k in ("name", "fumen", "paint") if k in f} for f in mine)
    return deck


def save_deck(deck, path=None):
    path = Path(path or DECK_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(deck, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _free_name(taken, base):
    name, k = base, 2
    while name in taken:
        name, k = f"{base} {k}", k + 1
    return name


def load_library(deck):
    """Your named decks: {"current", "decks": {name: deck}, "deleted": [...]}.
    The one in use is always `deck` (practice_deck.json, what the game reads);
    the others wait here."""
    try:
        got = json.loads(Path(DECK_PATH).with_name("practice_decks.json").read_text(encoding="utf-8"))
        decks = {n: d for n, d in got["decks"].items() if isinstance(d, dict) and isinstance(d.get("openers"), list)}
        current, deleted = got.get("current"), [x for x in got.get("deleted", []) if x.get("name") and x.get("deck")]
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        decks, current, deleted = {}, None, []
    if current not in decks:
        current = _free_name(decks, "デッキ1")     # (the deck in use is never dropped)
    decks[current] = deck
    return {"current": current, "decks": decks, "deleted": deleted}


def save_library(lib):
    path = Path(DECK_PATH).with_name("practice_decks.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".lib.tmp")
    tmp.write_text(json.dumps(lib, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def library_add(lib, name, source=None):
    """A new deck (a copy of `source`, else empty), now in use; returns it."""
    deck = json.loads(json.dumps(source)) if source is not None else default_deck()
    name = _free_name(lib["decks"], name)
    lib["decks"][name] = deck
    lib["current"] = name
    return deck


def library_rename(lib, name):
    """The deck in use gets `name` (made unique); returns the name it got."""
    name = name.strip()
    old = lib["current"]
    if not name or name == old:
        return old
    name = _free_name(lib["decks"], name)
    lib["decks"] = {(name if n == old else n): d for n, d in lib["decks"].items()}
    lib["current"] = name
    return name


def library_delete(lib):
    """Set the deck in use aside (it can come back) and use its neighbor;
    returns that deck. The last deck stays: None."""
    names = list(lib["decks"])
    if len(names) < 2:
        return None
    k = names.index(lib["current"])
    lib["deleted"].append({"name": lib["current"], "deck": lib["decks"].pop(lib["current"])})
    lib["current"] = names[k + 1] if k + 1 < len(names) else names[k - 1]
    return lib["decks"][lib["current"]]


def library_restore(lib, k):
    """Bring back deleted deck number k, now in use; returns it."""
    item = lib["deleted"].pop(k)
    name = _free_name(lib["decks"], item["name"])
    lib["decks"][name] = item["deck"]
    lib["current"] = name
    return item["deck"]


def load_editor():
    """How the deck's settings page was left (the board being painted, what
    was typed, the opener selected, the last rates). A file of its own: the
    running game reloads the deck whenever that file changes."""
    try:
        got = json.loads(Path(DECK_PATH).with_name("practice_editor.json").read_text(encoding="utf-8"))
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def save_editor(view):
    path = Path(DECK_PATH).with_name("practice_editor.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(view, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def single_entry(deck, keep=False):
    """The opener of the テンプレ単体 practice with its forms: the deck's own
    entry if it's in the deck, else one kept aside (keep: stored there, so
    forms added to it stay). None when none is picked."""
    name = deck.get("single")
    if not name:
        return None
    for entry in deck.get("openers", []):
        if entry["name"] == name:
            return entry
    aside = deck.get("single_forms", {})
    if name in aside:
        return aside[name]
    entry = new_entry(name)
    if keep:
        deck.setdefault("single_forms", {})[name] = entry
    return entry


def candidates(deck):
    """[(opener, form name, [Target])] in order: the deck's openers first to
    last (or only the one of テンプレ単体), each one's forms in order (only
    those switched on)."""
    out = []
    if deck.get("mode") == "single":
        one = single_entry(deck)
        entries = [one] if one else []
    else:
        entries = deck.get("openers", [])
    for entry in entries:
        for form in entry.get("forms", []):
            if form.get("on", True):
                ts = form_targets(entry["name"], form, deck.get("mirror", True))
                if ts:
                    out.append((entry["name"], form.get("name", ""), ts))
    return out



class SettledBoard:
    """The board's cells that stayed filled over the last few readings (a
    falling piece moves on), for the whole game."""

    def __init__(self, frames=3):
        from collections import deque
        self._recent = deque(maxlen=frames)
        self.last = frozenset()     # this reading as it is, a falling piece included

    def update(self, frame, box):
        from opener_detect import read_occupancy
        now = frozenset((x, y) for y, row in enumerate(read_occupancy(frame, box)) for x, v in enumerate(row) if v)
        self.last = now
        self._recent.append(now)
        return sorted(frozenset.intersection(*self._recent))


# --- the wiki's 派生: what the opener goes on to, from the second bag ---
# assets/opener_routes.json (tools/opener_import/build_routes.py): each one a
# テト譜 of boards. A board on the way is one of its pages; the guide goes to
# the next page the board is part of, with the pieces seen so far (the page's
# colors are the pieces it has there).
ROUTES_PATH = Path(__file__).resolve().parent.parent / "assets" / "opener_routes.json"
_WIKI_ROUTES = None
_MIN_COVERS = None
MIN_COVER_PATH = Path(__file__).resolve().parent.parent / "assets" / "opener_min_cover.json"
MAX_PLAN_NODES = 800
ROUTE_SEARCH_S = 2.0    # one look over all the routes (out of time: says "wait", not "off the route")


class Route:
    """One 派生: its name and its boards in page order (mirrored ones after)."""
    __slots__ = ("name", "points")

    def __init__(self, name, points):
        self.name, self.points = name, points


def route_points(fumen):
    """The boards of a route's テト譜 (one, or a list: a route the wiki gives
    in several), in order, each once (Target, colored)."""
    out, seen = [], set()
    pages = [p for f in ([fumen] if isinstance(fumen, str) else fumen) for p in decode(f)]
    for page in pages:
        for t in route_points_of_page(page):
            if t.key() not in seen:
                seen.add(t.key())
                out.append(t)
    return out


def route_points_of_page(page):
    """One テト譜 page as boards ([Target], top one first). The wiki often
    draws several on a page, one above the other with an empty row between
    (BT砲's 妥協形): a real board has no empty row under a block, so each
    block of rows is a board of its own, standing on the floor."""
    cells = {(x, y): v for y, row in enumerate(page.board_with_piece()) for x, v in enumerate(row) if v}
    if not cells:
        return []
    blocks, now = [], []
    for y in range(max(y for _, y in cells) + 1):
        if any((x, y) in cells for x in range(COLS)):
            now.append(y)
        elif now:
            blocks.append(now)
            now = []
    blocks.append(now)
    out = []
    for rows in reversed(blocks):
        low = rows[0] if len(blocks) > 1 else 0
        part = {(x, y - low): cells[(x, y)] for y in rows for x in range(COLS) if (x, y) in cells}
        if max(y for _, y in part) >= 20:
            continue
        colors = {c: FUMEN_PIECES[v] for c, v in part.items() if FUMEN_PIECES.get(v) in tuple(PIECES)}
        out.append(Target(part.keys(), colors or None))
    return out


def wiki_routes(opener):
    """[{"name", "fumen"}] the wiki lists for this opener (its shown name)."""
    global _WIKI_ROUTES
    if _WIKI_ROUTES is None:
        try:
            _WIKI_ROUTES = json.loads(ROUTES_PATH.read_text(encoding="utf-8"))["routes"]
        except (OSError, ValueError, KeyError):
            _WIKI_ROUTES = {}
    return _WIKI_ROUTES.get(opener, [])


def min_cover_routes(opener):
    """The opener's 最少パターン as routes: the fewest next-bag boards covering
    the next bag's orders (assets/opener_min_cover.json)."""
    global _MIN_COVERS
    if _MIN_COVERS is None:
        try:
            _MIN_COVERS = json.loads(MIN_COVER_PATH.read_text(encoding="utf-8"))["covers"]
        except (OSError, ValueError, KeyError):
            _MIN_COVERS = {}
    got = _MIN_COVERS.get(opener)
    if not got:
        return []
    if got.get("groups"):       # the wiki's own Standard / Advance / Extra: those alone
        return [{"name": g["name"], "paint": g["rows"], "cover": g["on"], "only": True} for g in got["groups"]]
    n = len(got["boards"])
    names = got.get("names") or [""] * n
    return [{"name": f"最少パターン {k + 1}/{n}（{n}個で {got['rate'] * 100:.2f}%）" + (f" {names[k]}" if names[k] else ""),
             "paint": rows, "cover": True} for k, rows in enumerate(got["boards"])]


def page_orders(base, page, hold=None, spare=False):
    """Which of the next bag's orders (a bit per all_bags()) build `page` from
    `base`, with `hold` in HOLD to begin with. The board may leave one T out
    (most next-bag shapes are the setup, its T kept for the T-spin); spare:
    one more piece may be left out too, kept in HOLD (the wiki's ホールド地形).
    Worked out per set of pieces placed, so the 5040 orders share the work."""
    room = frozenset(page.cells) - frozenset(base)
    if len(room) % 4 or len(room) > 32:
        return 0
    colors = page.colors or {}
    have = sorted(list(PIECES) + ([hold] if hold else []))
    no_t = list(have)
    no_t.remove("T")
    allowed = [have, no_t]
    if spare:
        allowed += [no_t[:k] + no_t[k + 1:] for k in range(len(no_t))]
    cuts = [c for c in tilings(room)
            if all(colors.get(x, p) == p for p, cells in c for x in cells)
            and sorted(p for p, _ in c) in allowed]
    target = frozenset(page.cells)
    out = 0
    for cut in cuts[:12]:
        parts = list(cut)
        whole = (1 << len(parts)) - 1
        fit = {}

        def can_place(mask, k):
            if (mask, k) not in fit:
                board = frozenset(base).union(*[parts[j][1] for j in range(len(parts)) if mask >> j & 1])
                piece, cells = parts[k]
                after = board | cells
                ok = cells in landing_spots(piece, board) and (after == target or not any(
                    all((x, y) in after for x in range(COLS)) for y in {y for _, y in cells}))
                fit[(mask, k)] = ok
            return fit[(mask, k)]

        memo = {}

        def go(mask, rest, held):
            if mask == whole:
                return True
            key = (mask, rest, held)
            if key in memo:
                return memo[key]
            options = []
            if rest:
                options.append((rest[0], rest[1:], held))
                if held is None and len(rest) > 1:
                    options.append((rest[1], rest[2:], rest[0]))
                elif held is not None and held != rest[0]:
                    options.append((held, rest[1:], rest[0]))
            elif held is not None:
                options.append((held, (), None))    # (swapped for the piece after this bag)
            found = False
            for piece, nrest, nheld in options:
                for k, (p, _) in enumerate(parts):
                    if p == piece and not mask >> k & 1 and can_place(mask, k) and go(mask | 1 << k, nrest, nheld):
                        found = True
                        break
                if found:
                    break
            memo[key] = found
            return found

        for b, bag in enumerate(all_bags()):
            if not out >> b & 1 and go(0, tuple(bag), hold):
                out |= 1 << b
    return out


def smallest_cover(masks, seconds=4.0):
    """(keys, orders covered): the fewest of `masks` ({key: bits}) that cover
    all that any of them does. Keys are ranks, the wiki's order: among sets
    of the same size, the one with the wiki's earlier boards."""
    import time
    every = 0
    for m in masks.values():
        every |= m
    # a board whose orders an earlier board has too is never needed
    kept = []
    for k, m in sorted(masks.items()):
        if not any(m | o == o for _, o in kept):
            kept.append((k, m))
    left, greedy = every, []
    while left:
        k, m = max(kept, key=lambda kv: (bin(kv[1] & left).count("1"), -kv[0]))
        greedy.append(k)
        left &= ~m
    best = sorted(greedy)
    until = time.monotonic() + seconds
    biggest = max(bin(m).count("1") for _, m in kept)

    def search(left, chosen):
        nonlocal best
        if not left:
            if (len(chosen), sorted(chosen)) < (len(best), best):
                best = sorted(chosen)
            return
        if time.monotonic() > until:
            return
        need = -(-bin(left).count("1") // biggest)
        if len(chosen) + need > len(best):
            return
        low = left & -left              # some order still open: one of the boards with it is in
        for k, m in sorted((k, m) for k, m in kept if m & low):
            search(left & ~m, chosen + [k])

    search(every, [])
    return best, bin(every).count("1")


def entry_routes(entry):
    """The opener's routes in your order: [{"name", "fumen" or "paint", "on",
    "own"}]. Your own (added by テト譜 or painted) come first when new. Until
    you change them, only the 最少パターン are on: the fewest boards covering
    the next bag's orders (min_cover_routes). An opener whose wiki page labels
    its boards Standard / Advance / Extra lists those alone, Standard on (and
    what Advance / Extra it takes to cover more). One without any: the wiki's
    最小 patterns and the first route from each of its shapes ("start")."""
    cover = min_cover_routes(entry["name"])
    only = any(r.get("only") for r in cover)
    wiki = {r["name"]: dict(r) for r in (cover if only else cover + wiki_routes(entry["name"]))}
    own = {r["name"]: dict(r, own=True) for r in entry.get("own_routes", [])}
    pool = {**wiki, **own}
    saved = [dict(pool[s["name"]], on=s.get("on", True)) for s in entry.get("routes", []) if s.get("name") in pool]
    have = {r["name"] for r in saved}
    new_own = [dict(r, on=True) for n, r in own.items() if n not in have]
    has_start = any(r.get("start") for r in wiki.values())
    new_wiki = [dict(r, on=bool(r.get("cover")) if cover else
                     bool(r.get("min") or r.get("start")) or (not has_start and k == 0))
                for k, (n, r) in enumerate(wiki.items()) if n not in have and n not in own]
    return new_own + saved + new_wiki


def delete_route(entry, name):
    """Delete one of your own routes, kept in entry["deleted_routes"] (with
    its place and tick) so restore_route can bring it back."""
    routes = entry_routes(entry)
    at = next((k for k, r in enumerate(routes) if r["name"] == name and r.get("own")), None)
    if at is None:
        return False
    kept = next(x for x in entry["own_routes"] if x["name"] == name)
    entry["own_routes"] = [x for x in entry["own_routes"] if x is not kept]
    entry.setdefault("deleted_routes", []).append(dict(kept, on=routes[at]["on"], at=at))
    entry["routes"] = [{"name": r["name"], "on": r["on"]} for k, r in enumerate(routes) if k != at]
    return True


def restore_route(entry, name):
    """Bring a deleted route back where it was; its row, or None. (If another
    route took its name meanwhile, it comes back as "name 2".)"""
    gone = entry.get("deleted_routes", [])
    k = next((k for k in range(len(gone) - 1, -1, -1) if gone[k]["name"] == name), None)
    if k is None:
        return None
    routes = entry_routes(entry)
    item = dict(gone.pop(k))
    on, at = item.pop("on", True), item.pop("at", 0)
    taken = {r["name"] for r in routes}
    shown, n = name, 2
    while shown in taken:
        shown, n = f"{name} {n}", n + 1
    item["name"] = shown
    entry.setdefault("own_routes", []).append(item)
    at = max(0, min(at, len(routes)))
    routes.insert(at, {"name": shown, "on": on})
    entry["routes"] = [{"name": r["name"], "on": r["on"]} for r in routes]
    return at


def route_targets(route):
    """The boards of one route of entry_routes."""
    if route.get("paint"):
        cells = paint_cells(route["paint"])
        colors = {c: v for c, v in cells.items() if v != "X"}
        return [Target(cells, colors or None)]
    return route_points(route["fumen"])


def after_clear(cells):
    """A shape with its full rows gone (what's left after its T-spin)."""
    full = {y for _, y in cells if all((x, y) in cells for x in range(COLS))}
    return frozenset((x, y - sum(1 for f in full if f < y)) for x, y in cells if y not in full)


def opener_starts(name):
    """What a route of this opener goes on from: its shapes, and each as it is
    after its T-spin (both sides)."""
    out = []
    for c in opener_shapes(name):
        for v in (c, after_clear(c)):
            for side in (v, mirror_cells(v)):
                if side and side not in out:
                    out.append(side)
    return out


def route_problem(opener, targets):
    """Why these boards can't be a route of this opener: "empty", "count"
    (an odd number of cells), "shape" (the colors don't make pieces), "far"
    (no board goes on from the opener); None if they can."""
    if not targets:
        return "empty"
    if any(len(t.cells) % 2 for t in targets):
        return "count"
    for t in targets:
        colored = frozenset(t.colors or ())
        if any(sum(1 for v in (t.colors or {}).values() if v == p) % 4 for p in PIECES):
            return "shape"
        try:
            if colored and not _tile(colored, t.colors, {}, float("inf")):
                return "shape"
        except _OutOfTime:
            pass
    starts = opener_starts(opener)
    if not any(b <= t.cells or (t.cells < b and len(b) - len(t.cells) == 4) for t in targets for b in starts):
        return "far"
    return None


def _entries(deck):
    if deck.get("mode") == "single":
        one = single_entry(deck)
        return [one] if one else []
    return deck.get("openers", [])


def deck_routes(deck):
    """{opener: [Route]}: the routes switched on, in your order."""
    out = {}
    for entry in _entries(deck):
        routes = []
        for r in entry_routes(entry):
            if not r["on"]:
                continue
            try:
                points = route_targets(r)
            except Exception:
                continue
            if deck.get("mirror", True):
                points = points + [t.mirrored() for t in points]
            if points:
                routes.append(Route(r["name"], points))
        if routes:
            out[entry["name"]] = routes
    return out


def is_perfect_clear(cells):
    """Every row the board has is full: it all clears."""
    rows = {y for _, y in cells}
    return bool(rows) and all(all((x, y) in cells for x in range(COLS)) for y in rows)


def page_rows(target, board):
    """How `board` can sit on the page `target`: tuples of the page's rows
    still on the board, bottom up (row y of the board is the page's rows[y]).
    A page that's a Perfect Clear loses its rows as they fill, so any of them
    may be gone already; on another page none is."""
    rows = sorted({y for _, y in target})
    height = max((y + 1 for _, y in board), default=0)
    if not is_perfect_clear(target):
        return [tuple(rows)] if rows == list(range(len(rows))) and frozenset(board) < frozenset(target) else []
    out = []
    for keep in range(len(rows), max(height, 1) - 1, -1):
        out += list(itertools.combinations(rows, keep))
    return out


class _OutOfTime(Exception):
    pass


def plan_towards(target, queue, board, i, hold, colors=None, rows=None, until=None):
    """From `board` towards the page `target` with the pieces known: (steps,
    whole). whole: the steps reach it; else they're as far as the pieces seen
    go, and it can still be finished. None if it can't. The steps' cells are
    where the piece goes on the board at that moment.

    rows: the page's rows still on the board (page_rows; None: all of them).
    On a Perfect Clear page rows clear as they fill, and what's above comes
    down; on any other a row may only fill with the last piece (its T-spin).
    until: time.monotonic() to give up at (then None)."""
    import time
    until = time.monotonic() + ROUTE_SEARCH_S if until is None else until
    target, board = frozenset(target), frozenset(map(tuple, board))
    colors = colors or {}
    every = sorted({y for _, y in target})
    live = tuple(every) if rows is None else tuple(rows)
    if any(y >= len(live) for _, y in board):
        return None
    done = frozenset((x, live[y]) for x, y in board) | frozenset(c for c in target if c[1] not in live)
    if not done < target or (len(target) - len(done)) % 4:
        return None
    clears = is_perfect_clear(target)
    nodes = [0]

    @lru_cache(maxsize=None)
    def tiles(room, live):
        """The cells left, as they lie on the board now, make whole pieces."""
        if not room:
            return True
        at = {(x, live.index(y)): colors.get((x, y)) for x, y in room}
        return _tile(frozenset(at), at, {}, until)

    @lru_cache(maxsize=None)
    def go(done, live, i, hold):
        room = target - done
        if not room:
            return (), True
        nodes[0] += 1
        if nodes[0] > MAX_PLAN_NODES or time.monotonic() > until:
            raise _OutOfTime
        options = []
        if i < len(queue):
            options.append((queue[i], i + 1, hold, False))
            if hold is None and i + 1 < len(queue):
                options.append((queue[i + 1], i + 2, queue[i], True))
            elif hold is not None and hold != queue[i]:
                options.append((hold, i + 1, queue[i], True))
        if not options:
            return (), False        # past what's been seen
        now = frozenset((x, live.index(y)) for x, y in done if y in live)
        best = None
        for piece, ni, nh, held in options:
            for cells in landing_spots(piece, now):
                if any(y >= len(live) for _, y in cells):
                    continue
                on_page = frozenset((x, live[y]) for x, y in cells)
                if not on_page <= room or not all(colors.get(c, piece) == piece for c in on_page):
                    continue
                after = done | on_page
                full = {y for _, y in on_page if all((x, y) in after for x in range(COLS))}
                if full and after != target and not clears:
                    continue        # a row filling early clears and breaks the shape
                left = tuple(y for y in live if y not in full) if clears else live
                if not tiles(target - after, left):
                    continue
                rest = go(after, left, ni, nh)
                if rest is None:
                    continue
                got = (({"piece": piece, "cells": sorted(cells), "hold": held},) + rest[0], rest[1])
                if got[1]:
                    return got
                best = best or got
        return best

    try:
        return go(done, live, i, hold)
    except _OutOfTime:
        return None


def _colors_whole(t, board, rows):
    """A quick no: with every cell left colored, each color must be whole
    pieces (a board that cut one of the page's pieces can't be on it)."""
    if any(y >= len(rows) for _, y in board):
        return False
    done = {(x, rows[y]) for x, y in board} | {c for c in t.cells if c[1] not in rows}
    room = t.cells - done
    if not done <= t.cells or len(room) % 4:
        return False
    colors = t.colors or {}
    if any(c not in colors for c in room):
        return True
    count = {}
    for c in room:
        count[colors[c]] = count.get(colors[c], 0) + 1
    return all(v % 4 == 0 for v in count.values())


def _fits_page(t, board, rows, until):
    """The board lies on the page this way and what's left makes whole pieces."""
    done = frozenset((x, rows[y]) for x, y in board) | frozenset(c for c in t.cells if c[1] not in rows)
    room = t.cells - done
    if not done < t.cells or len(room) % 4:
        return False
    at = {(x, rows.index(y)): (t.colors or {}).get((x, y)) for x, y in room}
    try:
        return _tile(frozenset(at), at, {}, until)
    except _OutOfTime:
        return False


def _tile(room, colors, memo, until):
    """`room` cuts into tetrominoes, each cell's color (if any) kept."""
    import time
    if not room:
        return True
    if room in memo:
        return memo[room]
    if time.monotonic() > until:
        raise _OutOfTime
    low = min(room, key=lambda c: (c[1], c[0]))
    found = False
    for piece in PIECES:
        for shape in set(SHAPES[piece]):
            for ax, ay in shape:        # each of the shape's cells on the lowest one
                part = frozenset((low[0] + dx - ax, low[1] + dy - ay) for dx, dy in shape)
                if part <= room and all(colors.get(c) in (None, piece) for c in part) \
                        and _tile(room - part, colors, memo, until):
                    found = True
                    break
            if found:
                break
        if found:
            break
    memo[room] = found
    return found


# --- setup rates: every first bag (5040) and every 8th piece (7) ---
ALL_BAGS = None


def all_bags():
    global ALL_BAGS
    if ALL_BAGS is None:
        import itertools
        ALL_BAGS = list(itertools.permutations(PIECES))
    return ALL_BAGS


def builds(targets, queue):
    return any(solve(t.cells, queue, colors=t.colors) is not None for t in targets)


def bag_mask(targets, bag):
    """For one bag: bit 7 set if the 7 build it; bits 0-6: with the 8th
    piece PIECES[i] (all set when the 7 do)."""
    bag = tuple(bag)
    if builds(targets, bag):
        return 0xFF
    m = 0
    for i, e in enumerate(PIECES):
        if builds(targets, bag + (e,)):
            m |= 1 << i
    return m


def _rate_job(args):
    keys, start, stop = args
    targets = [Target(cells, dict(colors) if colors else None) for cells, colors in keys]
    bags = all_bags()
    return start, [bag_mask(targets, bags[k]) for k in range(start, stop)]


def form_masks(targets, workers=None, progress=None):
    """bag_mask for all 5040 bags (in all_bags() order), worked on in parallel
    processes; progress(done, total) along the way."""
    from concurrent.futures import ProcessPoolExecutor, as_completed
    keys = [t.key() for t in targets]
    n, step = len(all_bags()), 120
    out = [0] * n
    jobs = [(keys, a, min(n, a + step)) for a in range(0, n, step)]
    done = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for fut in as_completed([pool.submit(_rate_job, j) for j in jobs]):
            start, masks = fut.result()
            out[start:start + len(masks)] = masks
            done += len(masks)
            if progress:
                progress(done, n)
    return out


def deck_rates(cands_masks):
    """cands_masks: [(opener, form, masks)] in the deck's order. Each game
    (bag x 8th piece, all equally likely) goes to the first that builds it.
    Returns {"total": rate, "by": [(opener, form, rate, alone)], "none": rate}:
    rate = share of games it's the one picked, alone = its own rate."""
    n = len(all_bags())
    games = n * len(PIECES)
    picked = [0] * len(cands_masks)
    alone = [0] * len(cands_masks)
    none = 0
    for b in range(n):
        for i in range(len(PIECES)):
            bit = 1 << i
            first = None
            for k, (_, _, masks) in enumerate(cands_masks):
                if masks[b] & bit:
                    alone[k] += 1
                    if first is None:
                        first = k
            if first is None:
                none += 1
            else:
                picked[first] += 1
    return {"total": 1 - none / games, "none": none / games,
            "by": [(o, f, picked[k] / games, alone[k] / games) for k, (o, f, _) in enumerate(cands_masks)]}
