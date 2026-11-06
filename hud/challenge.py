"""縛りプレイ (challenge mode): things over your own board on the game screen
to make the game harder, drawn by the HUD only (OBS shows the game as is).

  challenge_next  "from2": NEXT from the 2nd piece covered; "all": every NEXT
  challenge_cats  a cat comes over your board for each TETRIS / T-SPIN /
                  PERFECT CLEAR this match (from match_stats), and stays
                  until the match ends: real cats, the user's green-screen
                  clips (assets/challenge_cats/, tools/cat/make_challenge_cat.py)
                  played over the board, each at its own height and pace

The HUD is kept out of screen captures, so the recognition still sees the
whole game. Where Windows can't keep it out (HudWindow.reading_unsafe) it
would read the covers and cats instead, so nothing here is shown there.
"""
import json
import random
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

# NEXT column (reference 1232x692 px): the label's top-left is where the gate
# finds it (gameplay_gate NEXT_WINDOWS: (455, 83) / (1060, 83) on the
# recordings), the five pieces below it (QUEUE_SLOTS)
NEXT_X = {"left": (447, 517), "right": (1052, 1122)}
NEXT_TOP = {"all": 100, "from2": 144}
NEXT_BOTTOM = 341
SLOT_CENTERS_Y = (119, 169, 219, 269, 319)
# where the cats wander: each board (board_read LEFT_BOX / RIGHT_BOX), a
# little inside it
BOARD = {"left": (206, 120, 421, 548), "right": (811, 120, 1026, 548)}
MAX_CATS = 12
CLIPS_DIR = Path(__file__).resolve().parent.parent / "assets" / "challenge_cats"
FPS = 30


def challenge_side(display, state):
    """Whose board: display.challenge_side, or yours ("auto")."""
    side = display.get("challenge_side", "auto")
    if side in ("left", "right"):
        return side
    you = (state or {}).get("you_side")
    return you if you in ("left", "right") else "left"


def cat_count(state, side):
    """One cat for each TETRIS / T-SPIN / PERFECT CLEAR of that side this match."""
    stats = ((state or {}).get(side) or {}).get("match_stats") or {}
    n = sum(int(stats.get(k) or 0) for k in ("tetris", "tspin", "perfect_clear"))
    return max(0, min(MAX_CATS, n))


def next_cover(mode, side):
    """The covered part of the NEXT column, reference px (x1, y1, x2, y2), or None."""
    if mode not in NEXT_TOP:
        return None
    x1, x2 = NEXT_X[side]
    return x1, NEXT_TOP[mode], x2, NEXT_BOTTOM


_CLIPS = None


def load_clips():
    """The cat clips (assets/challenge_cats/*/clip.json), in name order; read
    once. Their frame images are read when first shown (Clip.image)."""
    global _CLIPS
    if _CLIPS is None:
        _CLIPS = []
        for path in sorted(CLIPS_DIR.glob("*/clip.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                _CLIPS.append(Clip(path.parent, data))
            except (OSError, ValueError, KeyError):
                pass
    return _CLIPS


class Clip:
    """One cat clip: frames cropped to the cat (x, y in the clip), and the
    part the cat ever covers (span), which is fitted to the board's width."""

    def __init__(self, folder, data):
        self.folder = Path(folder)
        self.fps = float(data["fps"])
        self.frames = data["frames"]
        self.span = data["span"]
        self.first = next((i for i, f in enumerate(self.frames) if f.get("file")), 0)
        self._images = {}

    def image(self, index):
        """Frame `index`'s image (kept while there are cats, see release), or None."""
        if index not in self._images:
            f = self.frames[index]
            img = None
            if f.get("file"):
                img = QtGui.QImage(str(self.folder / f["file"]))
                img = None if img.isNull() else img.convertToFormat(
                    QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            self._images[index] = img
        return self._images[index]

    def release(self):
        self._images = {}


class Cat:
    """One cat: plays its clip over the board, from the cat coming in to it
    going off, again and again. Each time round it comes from a side and at a
    height of its own (from its seed: the same match gives the same cats)."""

    def __init__(self, seed, side, now, clip):
        self.seed = seed
        self.side = side
        self.clip = clip
        rng = random.Random(seed)
        self.pace = rng.uniform(0.9, 1.1)
        self.born = now
        self.y = 0.0   # its floor (reference px), for drawing the nearer ones last

    def at(self, now):
        """(frame index, mirrored, floor y in reference px) at `now`. A new
        cat starts as it comes in (the clip's first frame with the cat)."""
        n = len(self.clip.frames)
        pos = self.clip.first + (now - self.born) * self.clip.fps * self.pace
        lap = int(pos // n)
        rng = random.Random(f"{self.seed}|{lap}")
        mirrored = rng.random() < 0.5
        x1, y1, x2, y2 = BOARD[self.side]
        sx1, sy1, sx2, sy2 = self.clip.span
        k = (x2 - x1) / (sx2 - sx1)
        floor = rng.uniform(min(y2, y1 + (sy2 - sy1) * k), y2)
        self.y = floor
        return int(pos) % n, mirrored, floor


def paint_cat(p, cat, s, now):
    """A cat over its board, scaled by s (reference px -> widget px)."""
    clip = cat.clip
    index, mirrored, floor = cat.at(now)
    img = clip.image(index)
    if img is None:
        return
    f = clip.frames[index]
    x1, y1, x2, y2 = BOARD[cat.side]
    sx1, sy1, sx2, sy2 = clip.span
    k = (x2 - x1) / (sx2 - sx1)               # clip px -> reference px
    w, h = img.width() * k, img.height() * k
    left = (sx2 - (f["x"] + img.width())) * k if mirrored else (f["x"] - sx1) * k
    top = floor - (sy2 - f["y"]) * k
    p.save()
    p.setClipRect(QtCore.QRectF(x1 * s, 0, (x2 - x1) * s, 10000))   # comes in from the board's edge
    target = QtCore.QRectF((x1 + left) * s, top * s, w * s, h * s)
    if mirrored:
        p.translate(target.center())
        p.scale(-1, 1)
        p.translate(-target.center())
    p.drawImage(target, img)
    p.restore()


class ChallengeLayer(QtWidgets.QWidget):
    """The covers and cats, over the whole HUD window (click-through)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.scale = 1.0
        self.side = "left"
        self.cover = None
        self.cats = []
        self._match = None
        self._clock = QtCore.QElapsedTimer()
        self._clock.start()
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(int(1000 / FPS))
        self._timer.timeout.connect(self._tick)
        self.setVisible(False)

    def now(self):
        return self._clock.elapsed() / 1000.0

    def update_state(self, state, display, scale, active):
        """active: shown at all now (a match on screen, the HUD kept out of
        captures, not positioning)."""
        self.scale = scale
        side = challenge_side(display, state)
        player = (state or {}).get(side) or {}
        puyo = bool(player.get("puyo"))   # (a side hidden by display.players still counts)
        active = active and not puyo
        cover = next_cover(display.get("challenge_next"), side) if active else None
        match = (state or {}).get("match_start_t")
        if match != self._match or side != self.side:
            self._match, self.side, self.cats = match, side, []
        want = cat_count(state, side) if active and display.get("challenge_cats") else 0
        now = self.now()
        while len(self.cats) < want:
            clips = load_clips()
            if not clips:
                break
            i = len(self.cats)
            self.cats.append(Cat(f"{match}|{side}|{i}", side, now, clips[i % len(clips)]))
        shown = cover is not None or bool(want)
        if cover != self.cover:
            self.cover = cover
            self.update()
        self.setVisible(shown)
        if want and shown:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            self.update()
            if not self.cats:   # no cats now: their images go
                for clip in _CLIPS or ():
                    clip.release()

    def _tick(self):
        self.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        s = self.scale
        if self.cover:
            x1, y1, x2, y2 = self.cover
            r = QtCore.QRectF(x1 * s, y1 * s, (x2 - x1) * s, (y2 - y1) * s)
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 60), max(1.0, 1.5 * s)))
            p.setBrush(QtGui.QColor(18, 20, 28, 250))
            p.drawRoundedRect(r, 6 * s, 6 * s)
            font = QtGui.QFont()
            font.setPixelSize(max(6, int(26 * s)))
            font.setBold(True)
            p.setFont(font)
            p.setPen(QtGui.QColor(255, 255, 255, 70))
            for cy in SLOT_CENTERS_Y:
                if y1 < cy < y2:
                    p.drawText(QtCore.QRectF(x1 * s, (cy - 20) * s, (x2 - x1) * s, 40 * s),
                               QtCore.Qt.AlignmentFlag.AlignCenter, "?")
        now = self.now()
        p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        for cat in self.cats:
            cat.at(now)
        for cat in sorted(self.cats, key=lambda c: c.y):   # the nearer ones over the farther
            paint_cat(p, cat, s, now)
        p.end()
