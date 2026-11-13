"""縛りプレイ (challenge mode): things over your own board on the game screen
to make the game harder. The OBS page draws the same (obs/overlay.html
challenge*: the same numbers and steps, keep the two in sync), so viewers
see them too.

  challenge_next  "from2": NEXT from the 2nd piece covered; "all": every NEXT
  challenge_cats  each TETRIS / T-SPIN / PERFECT CLEAR (a rise in
                  match_stats), a cat comes in from the screen's edge on your
                  side, over your board, and goes: real cats, the user's
                  green-screen clips (assets/challenge_cats/,
                  tools/cat/make_challenge_cat.py), taken in turn

The HUD is kept out of screen captures, so the recognition still sees the
whole game. Where Windows can't keep it out (HudWindow.reading_unsafe) it
would read the covers and cats instead, so nothing here is shown there.
"""
import json
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

# NEXT column (reference 1232x692 px): the label's top-left is where the gate
# finds it (gameplay_gate NEXT_WINDOWS: (455, 83) / (1060, 83) on the
# recordings), the five pieces below it (QUEUE_SLOTS)
NEXT_X = {"left": (447, 517), "right": (1052, 1122)}
# the gaps between the five boxes are at 144, 194, 244, 294 (user: choose how many show)
NEXT_TOP = {"all": 100, "from2": 144, "from3": 194, "from4": 244, "from5": 294}
NEXT_BOTTOM = 341
SLOT_CENTERS_Y = (119, 169, 219, 269, 319)
# each board (board_read LEFT_BOX / RIGHT_BOX), a little inside it: what a
# cat's size is measured against
BOARD = {"left": (206, 120, 421, 548), "right": (811, 120, 1026, 548)}
CAT_SIZE = 2.2   # the part a cat covers in its clip is this many boards wide (user: big enough to hide the board)
# cats come in from the screen's edge on that player's side (1P the left, 2P
# the right; user: as if from outside the screen), at any height in here
EDGE_X = {"left": 0, "right": 1232}
FLOOR_Y = (40, 680)
FADE_S = 0.35     # a cat that turns up mid-screen fades in
# A cat that leaves by the inner side (the go-kart) isn't cut off mid-screen:
# it keeps going for this long, its last frames over and over, speeding up
# to OFF_SPEEDUP times its speed, and fades out over the last OFF_FADE_S
# (user: let it drive off before it goes)
OFF_S, OFF_SPEEDUP, OFF_FADE_S, OFF_CYCLE = 1.5, 3.0, 0.6, 8
MAX_CATS = 4   # on the screen at once (each comes and goes)
# The cats aren't in the release yet (user, v0.2.14: NEXT only): off whatever
# the setting says, and their clips aren't in the zip (make_release.SKIP_DIRS).
CATS_ENABLED = False
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
    """That side's TETRIS + T-SPIN + PERFECT CLEAR this match: a cat comes each time it goes up."""
    stats = ((state or {}).get(side) or {}).get("match_stats") or {}
    return max(0, sum(int(stats.get(k) or 0) for k in ("tetris", "tspin", "perfect_clear")))


def next_cover(mode, side):
    """The covered part of the NEXT column, reference px (x1, y1, x2, y2), or None."""
    if mode not in NEXT_TOP:
        return None
    x1, x2 = NEXT_X[side]
    return x1, NEXT_TOP[mode], x2, NEXT_BOTTOM


def _mix(text):
    """A number in [0, 1) from text: FNV-1a then murmur3's finish (the same in
    obs/overlay.html challengeMix, so the page picks the same cats)."""
    h = 0x811C9DC5
    for b in text.encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    h ^= h >> 16
    h = (h * 0x85EBCA6B) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0xC2B2AE35) & 0xFFFFFFFF
    h ^= h >> 16
    return h / 2 ** 32


class Rand:
    """random.Random's random / uniform, from a seed text (see _mix)."""

    def __init__(self, seed):
        self.seed, self.n = seed, 0

    def random(self):
        self.n += 1
        return _mix(f"{self.seed}|{self.n}")

    def uniform(self, a, b):
        return a + (b - a) * self.random()


def cat_seed(match, side, sent):
    """A cat's seed: the match, the side and how many came before it this match."""
    return f"{round(float(match or 0) * 10)}|{side}|{sent}"


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
    """One cat clip: frames cropped to the cat (x, y, w, h in the clip); the
    frames with the whole cat in the picture (start..end) and the part it
    covers in them (span); and which side of the picture the cat comes in by
    and leaves by ("l", "r", or None: it's there from the start / to the end)."""

    def __init__(self, folder, data):
        self.folder = Path(folder)
        self.fps = float(data["fps"])
        self.frames = data["frames"]
        self.width = int(data["size"][0])
        self.span = data["span"]
        self.start, self.end = int(data["start"]), int(data["end"])
        files = [i for i, f in enumerate(self.frames) if f.get("file")]
        self.first, self.last = files[0], files[-1]
        self.enters = self._cut(self.frames[self.first])
        self.leaves = self._cut(self.frames[self.last])
        # going off: the last frames with the whole cat, and its speed then (clip px a frame)
        e = self.end
        self.off_cycle = list(range(max(self.start, e - OFF_CYCLE + 1), e + 1))
        back = self.frames[max(self.start, e - OFF_CYCLE)]
        self.off_speed = (self.frames[e]["x"] - back["x"]) / max(1, e - max(self.start, e - OFF_CYCLE))
        self._images = {}

    def _cut(self, f):
        if f["x"] <= 1:
            return "l"
        if f["x"] + f["w"] >= self.width - 1:
            return "r"
        return None

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


def _flip(side, mirrored):
    return {"l": "r", "r": "l"}.get(side) if mirrored else side


class Visit:
    """How a cat comes on: which frames, which way round, how big, where."""

    def __init__(self, cat, rng, t0):
        clip = cat.clip
        outer = "l" if cat.side == "left" else "r"
        # turned so it comes in by the screen's edge
        self.mirrored = (clip.enters != outer) if clip.enters else rng.random() < 0.5
        self.fade_in = _flip(clip.enters, self.mirrored) != outer
        self.fade_out = _flip(clip.leaves, self.mirrored) != outer
        self.a = clip.start if self.fade_in else clip.first
        self.b = clip.end if self.fade_out else clip.last
        bx1, _, bx2, _ = BOARD[cat.side]
        sx1, sy1, sx2, sy2 = clip.span
        self.k = (bx2 - bx1) / (sx2 - sx1) * CAT_SIZE * rng.uniform(0.9, 1.1)
        push = rng.uniform(0, 0.05) * clip.width * self.k   # sometimes stops a little short
        w = clip.width * self.k
        self.x0 = EDGE_X[cat.side] - push if outer == "l" else EDGE_X[cat.side] + push - w
        self.floor = rng.uniform(min(FLOOR_Y[1], FLOOR_Y[0] + (sy2 - sy1) * self.k), FLOOR_Y[1])
        self.t0 = t0
        self.t_end = t0 + (self.b - self.a + 1) / (clip.fps * cat.pace)   # the clip's part played
        self.t1 = self.t_end + (OFF_S if self.fade_out else 0.0)          # when it's gone


class Cat:
    """One cat: comes on from the screen's edge on its player's side, does
    what its clip shows, and goes (from its seed: the same match gives the
    same cats)."""

    def __init__(self, seed, side, now, clip):
        self.side = side
        self.clip = clip
        rng = Rand(seed)
        self.pace = rng.uniform(0.9, 1.1)
        self.v = Visit(self, rng, now)
        self.y = self.v.floor   # its floor (reference px), for drawing the nearer ones last

    def gone(self, now):
        return now >= self.v.t1

    def at(self, now):
        """(frame index, extra x (clip px), visit, opacity) at `now`, or None
        once it's gone."""
        v = self.v
        if now >= v.t1:
            return None
        clip = self.clip
        t = max(0.0, now - v.t0)
        opacity = min(1.0, t / FADE_S) if v.fade_in else 1.0
        if now < v.t_end:
            return min(v.b, v.a + int(t * clip.fps * self.pace)), 0.0, v, max(0.0, opacity)
        # going off by the inner side: on and on, faster, fading out
        m = (now - v.t_end) * clip.fps * self.pace          # frames since
        n = OFF_S * clip.fps * self.pace
        index = clip.off_cycle[int(m) % len(clip.off_cycle)]
        x = clip.frames[clip.end]["x"] + clip.off_speed * (m + (OFF_SPEEDUP - 1) / 2 * m * m / n)
        opacity = min(opacity, (v.t1 - now) / OFF_FADE_S)
        return index, x - clip.frames[index]["x"], v, max(0.0, min(1.0, opacity))


def paint_cat(p, cat, s, now):
    """A cat on its player's side of the screen, scaled by s (reference px -> widget px)."""
    shown = cat.at(now)
    if shown is None:
        return
    index, dx, v, opacity = shown
    clip = cat.clip
    img = clip.image(index)
    if img is None or opacity <= 0:
        return
    f = clip.frames[index]
    k = v.k
    fx = f["x"] + dx
    x = v.x0 + ((clip.width - fx - img.width()) if v.mirrored else fx) * k
    top = v.floor - (clip.span[3] - f["y"]) * k
    p.save()
    p.setOpacity(opacity)
    target = QtCore.QRectF(x * s, top * s, img.width() * k * s, img.height() * k * s)
    if v.mirrored:
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
        self._seen = None    # the count (cat_count) cats have come for
        self._sent = 0       # cats sent this match (which clip is next)
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
            self._seen, self._sent = None, 0
        count = cat_count(state, side)
        # the first count seen is where it starts (the app opened mid-match: no flood of cats)
        new = 0 if self._seen is None else max(0, count - self._seen)
        self._seen = count
        now = self.now()
        if not (active and CATS_ENABLED and display.get("challenge_cats")):
            self.cats = []
        else:
            self.cats = [c for c in self.cats if not c.gone(now)]
            clips = load_clips()
            for _ in range(new if clips else 0):
                if len(self.cats) >= MAX_CATS:
                    break
                self.cats.append(Cat(cat_seed(match, side, self._sent), side, now,
                                     clips[self._sent % len(clips)]))
                self._sent += 1
        self._refresh(cover)

    def _refresh(self, cover):
        want = bool(self.cats)
        shown = cover is not None or want
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
        now = self.now()
        if any(c.gone(now) for c in self.cats):
            self.cats = [c for c in self.cats if not c.gone(now)]
            self._refresh(self.cover)
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
        for cat in sorted(self.cats, key=lambda c: c.y):   # the nearer ones over the farther
            paint_cat(p, cat, s, now)
        p.end()
