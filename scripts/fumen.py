"""Decoder for テト譜 / fumen strings (v115@...), the format opener wikis use
to share board diagrams. Follows the published format as implemented by
knewjade/tetris-fumen (MIT): 64-character little-endian values, a run-length
field diff per page, a 3-value action (piece, rotation, position, flags) and
an optional comment; a locked piece is merged into the next page's field and
full lines are cleared.

Only what opener matching needs is kept: each page's field (after applying
that page's diff) and its piece. Boards are lists of rows, bottom row first,
10 cells each; 0 = empty, 1 I, 2 L, 3 O, 4 Z, 5 T, 6 J, 7 S, 8 gray.
"""
from dataclasses import dataclass, field as dc_field

ENCODE_TABLE = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
WIDTH = 10
FIELD_TOP = 23                  # v115
GARBAGE_LINE = 1
MAX_HEIGHT = FIELD_TOP + GARBAGE_LINE
NUM_BLOCKS = MAX_HEIGHT * WIDTH

PIECES = {0: None, 1: "I", 2: "L", 3: "O", 4: "Z", 5: "T", 6: "J", 7: "S", 8: "X"}
PIECE_NUMBER = {v: k for k, v in PIECES.items() if v}
ROTATIONS = {0: "reverse", 1: "right", 2: "spawn", 3: "left"}

# Spawn-orientation block offsets (x right, y up) around the piece's center.
SHAPES = {
    "I": [(0, 0), (-1, 0), (1, 0), (2, 0)],
    "T": [(0, 0), (-1, 0), (1, 0), (0, 1)],
    "O": [(0, 0), (1, 0), (0, 1), (1, 1)],
    "L": [(0, 0), (-1, 0), (1, 0), (1, 1)],
    "J": [(0, 0), (-1, 0), (1, 0), (-1, 1)],
    "S": [(0, 0), (-1, 0), (0, 1), (1, 1)],
    "Z": [(0, 0), (1, 0), (0, 1), (-1, 1)],
}


def piece_blocks(piece, rotation, x, y):
    blocks = SHAPES[piece]
    if rotation == "right":
        blocks = [(b, -a) for a, b in blocks]
    elif rotation == "left":
        blocks = [(-b, a) for a, b in blocks]
    elif rotation == "reverse":
        blocks = [(-a, -b) for a, b in blocks]
    return [(x + dx, y + dy) for dx, dy in blocks]


@dataclass
class Page:
    field: list                 # rows bottom-up (row 0 = bottom), FIELD_TOP rows of WIDTH cells
    piece: str = None           # piece of this page's operation (not yet in `field`)
    rotation: str = None
    x: int = 0
    y: int = 0
    lock: bool = True
    comment: str = None
    extra: dict = dc_field(default_factory=dict)

    def board_with_piece(self):
        """The field with this page's piece drawn in (as the diagram shows it)."""
        rows = [r[:] for r in self.field]
        if self.piece and self.piece != "X":
            for bx, by in piece_blocks(self.piece, self.rotation, self.x, self.y):
                if 0 <= by < len(rows) and 0 <= bx < WIDTH:
                    rows[by][bx] = PIECE_NUMBER[self.piece]
        return rows


class _Values:
    def __init__(self, data):
        self.v = [ENCODE_TABLE.index(c) for c in data]
        self.i = 0

    def empty(self):
        return self.i >= len(self.v)

    def poll(self, n):
        value = 0
        for k in range(n):
            value += self.v[self.i] * (64 ** k)
            self.i += 1
        return value


def _decode_position(n, piece, rotation):
    x = n % WIDTH
    y = FIELD_TOP - n // 10 - 1
    # fumen stores O / I / S / Z by a different reference cell in some rotations
    if piece == "O" and rotation == "left":
        x, y = x + 1, y - 1
    elif piece == "O" and rotation == "reverse":
        x += 1
    elif piece == "O" and rotation == "spawn":
        y -= 1
    elif piece == "I" and rotation == "reverse":
        x += 1
    elif piece == "I" and rotation == "left":
        y -= 1
    elif piece == "S" and rotation == "spawn":
        y -= 1
    elif piece == "S" and rotation == "right":
        x -= 1
    elif piece == "Z" and rotation == "spawn":
        y -= 1
    elif piece == "Z" and rotation == "left":
        x += 1
    return x, y


COMMENT_TABLE = (" !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`"
                 "abcdefghijklmnopqrstuvwxyz{|}~")
COMMENT_MAX = len(COMMENT_TABLE) + 1


def _decode_comment(values, length):
    chars = []
    for _ in range((length + 3) // 4):
        v = values.poll(5)
        for _ in range(4):
            chars.append(v % COMMENT_MAX)
            v //= COMMENT_MAX
    text = "".join(COMMENT_TABLE[c] if c < len(COMMENT_TABLE) else "" for c in chars[:length])
    try:  # comments are URL-escaped (non-ASCII as %uXXXX)
        import re
        text = re.sub(r"%u([0-9A-Fa-f]{4})", lambda m: chr(int(m.group(1), 16)), text)
        from urllib.parse import unquote
        text = unquote(text)
    except Exception:
        pass
    return text


def _empty_field():
    return [[0] * WIDTH for _ in range(MAX_HEIGHT)]   # index 0 = garbage row, 1.. = playfield? see _cell


def decode(fumen):
    """Pages of a v115 fumen string. Each Page.field is FIELD_TOP rows,
    bottom row first (the garbage row below the field is dropped)."""
    data = fumen.strip()
    if "@" in data:
        prefix, data = data.split("@", 1)
        if not prefix.endswith("115"):
            raise ValueError(f"unsupported fumen version: {prefix}")
    data = data.replace("?", "")
    values = _Values(data)

    # internal field: rows 0..FIELD_TOP-1 = playfield bottom-up, row -1 = garbage
    prev = [[0] * WIDTH for _ in range(FIELD_TOP)]
    prev_garbage = [0] * WIDTH
    pages = []
    repeat = -1
    while not values.empty():
        if repeat > 0:
            cur, cur_garbage = [r[:] for r in prev], prev_garbage[:]
            repeat -= 1
        else:
            cur, cur_garbage = [r[:] for r in prev], prev_garbage[:]
            changed = True
            index = 0
            while index < NUM_BLOCKS:
                diff_block = values.poll(2)
                diff = diff_block // NUM_BLOCKS
                count = diff_block % NUM_BLOCKS
                if diff == 8 and count == NUM_BLOCKS - 1:
                    changed = False
                for _ in range(count + 1):
                    x = index % WIDTH
                    y = FIELD_TOP - index // WIDTH - 1
                    if y >= 0:
                        cur[y][x] += diff - 8
                    else:
                        cur_garbage[x] += diff - 8
                    index += 1
            if not changed:
                repeat = values.poll(1)

        v = values.poll(3)
        ptype = PIECES[v % 8]; v //= 8
        rotation = ROTATIONS[v % 4]; v //= 4
        pos = v % NUM_BLOCKS; v //= NUM_BLOCKS
        rise = v % 2 == 1; v //= 2
        mirror = v % 2 == 1; v //= 2
        _colorize = v % 2 == 1; v //= 2
        has_comment = v % 2 == 1; v //= 2
        lock = v % 2 != 1
        x, y = _decode_position(pos, ptype, rotation) if ptype else (0, 0)
        comment = None
        if has_comment:
            comment = _decode_comment(values, values.poll(2))

        page = Page(field=[r[:] for r in cur], piece=ptype, rotation=rotation, x=x, y=y,
                    lock=lock, comment=comment)
        pages.append(page)

        # the next page starts from this one's field, with the piece locked in
        nxt = [r[:] for r in cur]
        if lock:
            if ptype and ptype != "X":
                for bx, by in piece_blocks(ptype, rotation, x, y):
                    if 0 <= by < FIELD_TOP and 0 <= bx < WIDTH:
                        nxt[by][bx] = PIECE_NUMBER[ptype]
            nxt = [r for r in nxt if not all(r)]                 # clear full lines
            nxt += [[0] * WIDTH for _ in range(FIELD_TOP - len(nxt))]
            if rise:
                nxt = [cur_garbage[:]] + nxt[:-1]
                cur_garbage = [0] * WIDTH
            if mirror:
                nxt = [r[::-1] for r in nxt]
        prev, prev_garbage = nxt, cur_garbage
    return pages


def to_text(rows, height=None):
    """Board as text, top row first ('.' empty, piece letters, X gray)."""
    rows = list(rows)
    if height is None:
        height = max((i + 1 for i, r in enumerate(rows) if any(r)), default=1)
    return "\n".join("".join(PIECES[c] or "." if c else "." for c in rows[y]) for y in range(height - 1, -1, -1))
