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
  challenge_dopamine  each TETRIS / T-SPIN / PC of yours bursts out loud
                  (hud/dopamine.py)
  challenge_mosaic  a mosaic over your board, coarser as a number goes up
                  (scripts/mosaic.py: the server works out the strength;
                  the board is grabbed here, MOSAIC_FPS a second, so the
                  mosaic has no delay — the HUD isn't in the grab)

The HUD is kept out of screen captures, so the recognition still sees the
whole game. Where Windows can't keep it out (HudWindow.reading_unsafe) it
would read the covers and cats instead, so nothing here is shown there.
"""
import json
import logging
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
ANCHORED_SIZE = 1.5   # a cat kept to the screen's top or bottom (Clip.anchor): over the board, this many boards wide
ANCHORED_SHIFT = 0.2   # ... a little to either side: at most this share of a board, either way, in all
SCREEN_H = 692
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
END_FADE_S = 0.3   # one that goes on the spot: its last frame fades out over this
PLAY_OUT_FADE_S = 0.8   # a clip that plays out (Clip.play_out): its last frame (the glass) fades over this
WALK_FADE_S = 0.7       # one leaving by the inner side fades over its last this long, walking
SCREEN_W = 1232
IMAGE_CACHE = 32        # frames kept read per clip
MAX_CATS = 4   # on one player's side at once (each comes and goes)
# (v0.2.14 shipped NEXT only, with this False; back on in v0.2.16, the
# glass-breaking cat added as cat3: user)
CATS_ENABLED = True
CLIPS_DIR = Path(__file__).resolve().parent.parent / "assets" / "challenge_cats"
FPS = 30
MOSAIC_FPS = 30
GARBAGE_FPS = 60   # the garbage rows read from the screen this often (challenge_garbage)


def _safely(fn, *args):
    """Run fn from a timer: an error there is logged, not fatal (PyQt ends the
    whole process on an exception escaping a slot)."""
    try:
        fn(*args)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("a background step failed")


_log = logging.getLogger(__name__)   # (_log: "log" is the event_log in places)
# a clear only bursts / is said while it's new: this many game seconds at most
# after it happened (one that turns up "new" later — a log seen half-empty once,
# then whole again — said nothing then: user heard the voice with nothing done)
FRESH_S = 4.0


def game_now(state):
    """The match's clock now (the event_log's "t" clock), or None."""
    st = state or {}
    try:
        return float(st["match_start_t"]) + float(st.get("match_elapsed_s") or 0)
    except (KeyError, TypeError, ValueError):
        return None


def fresh(e, state):
    """Has this event_log entry just happened (FRESH_S)? Unknown clock: yes."""
    t_now = game_now(state)
    return t_now is None or t_now - float(e.get("t") or 0) <= FRESH_S


def event_key(e):
    """An event_log entry as itself (time, what, a PERFECT CLEAR or not): its
    place in the log or being on top says nothing (entries go in late)."""
    return round(float(e.get("t") or 0), 3), str(e.get("label") or ""), bool(e.get("perfect_clear"))


def challenge_side(display, state):
    """Whose board: display.challenge_side, or yours ("auto")."""
    side = display.get("challenge_side", "auto")
    if side in ("left", "right"):
        return side
    you = (state or {}).get("you_side")
    return you if you in ("left", "right") else "left"


def cat_sides(display):
    """The players whose cats come (display.challenge_cats_side): both, or one."""
    v = display.get("challenge_cats_side", "both")
    return (v,) if v in ("left", "right") else ("left", "right")


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


RARE_CHANCE = 0.1   # a rare clip (clip.json "rare": the がんばれ cat) instead, now and then


def pick_clip(clips, seed, sent):
    """The cats in turn, but now and then (RARE_CHANCE) a rare one (the same
    pick as obs/overlay.html challengePick)."""
    common = [c for c in clips if not c.rare] or clips
    rare = [c for c in clips if c.rare]
    if rare and _mix(seed + "|rare") < RARE_CHANCE:
        return rare[int(_mix(seed + "|which") * len(rare)) % len(rare)]
    # each round of len(common) cats: all of them, shuffled anew (user: not
    # the same order every time), by the match and side (seed's first part)
    base = seed.rsplit("|", 1)[0]
    n = len(common)
    order = sorted(common, key=lambda c: _mix(f"{base}|{sent // n}|{c.folder.name}"))
    return order[sent % n]


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
        # "bottom" / "top": cut by that edge of the clip the whole time (peeking
        # up, hanging from a drone): kept to that edge of the screen, over the board
        self.anchor = data.get("anchor")
        self.rare = bool(data.get("rare"))   # not in turn: now and then (pick_clip)
        self.scale = float(data.get("scale") or 1.0)   # this clip's cat bigger / smaller (the drone cat: smaller, user)
        # where the cat itself is across the clip, middle of the shown frames
        # (an anchored cat is centred on it, not on the span: user, the
        # Persian sat a little right)
        mids = sorted(f.get("cx", f["x"]) + f.get("cw", f.get("w", 0)) / 2
                      for f in self.frames[self.start:self.end + 1] if f.get("file"))
        self.center_x = mids[len(mids) // 2] if mids else (self.span[0] + self.span[2]) / 2
        self.mirror = data.get("mirror", True) is not False   # may be turned round to come in by the screen's edge
        # plays to `end` and fades there, glass and all (the glass cat: it
        # walks off but its hole in the glass stays: nothing slides away)
        self.play_out = bool(data.get("play_out"))
        files = [i for i, f in enumerate(self.frames) if f.get("file")]
        self.first, self.last = files[0], files[-1]
        self.enters = self._cut(self.frames[self.first])
        self.leaves = self._cut(self.frames[self.last])
        # going off: the last frames with the whole cat, and its speed then (clip px a frame)
        e = self.end
        self.off_cycle = list(range(max(self.start, e - OFF_CYCLE + 1), e + 1))
        back = self.frames[max(self.start, e - OFF_CYCLE)]
        # (the cat's own place: a clip with glass has the glass in its frames' x)
        self.off_speed = (cat_x(self.frames[e]) - cat_x(back)) / max(1, e - max(self.start, e - OFF_CYCLE))
        self._images = {}

    def _cut(self, f):
        x, w = f.get("cx", f["x"]), f.get("cw", f.get("w", 0))   # (the cat alone, when the picture has glass)
        if x <= 1:
            return "l"
        if x + w >= self.width - 1:
            return "r"
        return None

    def image(self, index):
        """Frame `index`'s image, or None. The last IMAGE_CACHE read stay (a
        clip with glass has big frames: not all 240 at once)."""
        if index in self._images:
            self._images[index] = self._images.pop(index)   # (now the newest)
        else:
            while len(self._images) >= IMAGE_CACHE:
                self._images.pop(next(iter(self._images)))
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


def cat_x(f):
    """Where the cat itself starts in a frame (cx when the frame has glass around it)."""
    return f.get("cx", f["x"])


def _flip(side, mirrored):
    return {"l": "r", "r": "l"}.get(side) if mirrored else side


class Visit:
    """How a cat comes on: which frames, which way round, how big, where."""

    def __init__(self, cat, rng, t0):
        clip = cat.clip
        outer = "l" if cat.side == "left" else "r"
        # turned so it comes in by the screen's edge
        self.mirrored = (clip.enters != outer) if clip.enters else rng.random() < 0.5
        if clip.play_out and clip.leaves:   # leaves by the screen's edge (it plays out, all of it)
            self.mirrored = clip.leaves != outer
        if not clip.mirror:   # words on it (the がんばれ cat): never turned round
            self.mirrored = False
        self.fade_in = _flip(clip.enters, self.mirrored) != outer
        self.fade_out = _flip(clip.leaves, self.mirrored) != outer
        self.a = clip.start if self.fade_in else clip.first
        # walks off by the inner side (it really goes by a side: clip.leaves);
        # one that goes on the spot (sinking down, flying up) plays to its
        # end and fades — looping its last frames there jittered (user)
        # one going off by the inner side plays on till its last whole frame
        # and fades out walking (looping its last frames on, to walk it off the
        # screen, looked stitched together: user); no frame made up
        self.walk_off = False
        self.fades_walking = self.fade_out and clip.leaves is not None and not clip.play_out
        self.b = clip.end if self.fades_walking else clip.last   # (the rest of the clip: as long as it can stay)
        bx1, _, bx2, _ = BOARD[cat.side]
        sx1, sy1, sx2, sy2 = clip.span
        size = (ANCHORED_SIZE if clip.anchor else CAT_SIZE) * clip.scale
        self.k = (bx2 - bx1) / (sx2 - sx1) * size * rng.uniform(0.9, 1.1)
        r = rng.uniform(0, 0.05)
        push = r * clip.width * self.k   # sometimes stops a little short
        w = clip.width * self.k
        self.x0 = EDGE_X[cat.side] - push if outer == "l" else EDGE_X[cat.side] + push - w
        self.floor = rng.uniform(min(FLOOR_Y[1], FLOOR_Y[0] + (sy2 - sy1) * self.k), FLOOR_Y[1])
        if clip.anchor:
            # over the board, a little to either side (r), at the screen's edge
            mid = clip.width - clip.center_x if self.mirrored else clip.center_x
            self.x0 = (bx1 + bx2) / 2 - mid * self.k + (r / 0.05 - 0.5) * ANCHORED_SHIFT * (bx2 - bx1)
            self.floor = SCREEN_H if clip.anchor == "bottom" else sy2 * self.k
        self.t0 = t0
        self.t_end = t0 + (self.b - self.a + 1) / (clip.fps * cat.pace)   # the clip's part played
        self.t1 = self.t_end + (0.0 if self.fades_walking else PLAY_OUT_FADE_S if clip.play_out
                                else END_FADE_S if self.fade_out else 0.0)   # when it's gone


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
        if v.fades_walking:   # fading over its last WALK_FADE_S, still walking
            opacity = min(opacity, (v.t_end - now) / WALK_FADE_S)
        if now < v.t_end:
            return min(v.b, v.a + int(t * clip.fps * self.pace)), 0.0, v, max(0.0, min(1.0, opacity))
        if not v.walk_off:   # gone on the spot (or played out, the glass left): its last frame, fading
            fade = PLAY_OUT_FADE_S if clip.play_out else END_FADE_S
            return v.b, 0.0, v, max(0.0, min(opacity, (v.t1 - now) / fade))
        # going off by the inner side: on at its own pace, fading at the end
        m = (now - v.t_end) * clip.fps * self.pace          # frames since
        index = clip.off_cycle[int(m) % len(clip.off_cycle)]
        x = cat_x(clip.frames[clip.end]) + clip.off_speed * m
        opacity = min(opacity, (v.t1 - now) / OFF_FADE_S)
        return index, x - cat_x(clip.frames[index]), v, max(0.0, min(1.0, opacity))


COMMENT_FLOW_S = 6.0     # (comments.FLOW_S)
COMMENT_TOP, COMMENT_LANE_H = 30, 58   # reference px: the first lane's top, and a lane's height (11 lanes)
COMMENT_PX, COMMENT_BIG_PX = 34, 50
COMMENT_SUPER = 2        # comments are drawn this many times bigger, then scaled down (sharp at any size)


def comment_image(text, big):
    """A comment's text, white with a black edge, as a picture (made once)."""
    font = QtGui.QFont("Yu Gothic UI")
    font.setBold(True)
    font.setPixelSize(int((COMMENT_BIG_PX if big else COMMENT_PX) * COMMENT_SUPER))
    path = QtGui.QPainterPath()
    path.addText(0, 0, font, text)
    r = path.boundingRect().adjusted(-8, -8, 8, 8)
    img = QtGui.QImage(max(1, int(r.width())), max(1, int(r.height())), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.translate(-r.left(), -r.top())
    p.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 200), 3.5 * COMMENT_SUPER, QtCore.Qt.PenStyle.SolidLine,
                        QtCore.Qt.PenCapStyle.RoundCap, QtCore.Qt.PenJoinStyle.RoundJoin))
    p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    p.drawPath(path)
    p.fillPath(path, QtGui.QColor(255, 255, 255))
    p.end()
    return img


GARBAGE_FILL = (196, 198, 204)   # a garbage block, as the game draws them (no hole)
GARBAGE_EDGE = (150, 152, 160)


def paint_garbage(p, side, rows, s):
    """The bottom `rows` rows of that board as garbage blocks, every cell
    filled: the holes don't show (obs/overlay.html challengePaintGarbage)."""
    import mosaic as mz
    x1, y1, x2, y2 = mz.GRID[side]
    cw, ch = (x2 - x1) / 10, (y2 - y1) / mz.ROWS
    p.save()
    p.setPen(QtGui.QPen(QtGui.QColor(*GARBAGE_EDGE), max(1.0, 1.2 * s)))
    p.setBrush(QtGui.QColor(*GARBAGE_FILL))
    for r in range(rows):
        y = y2 - (r + 1) * ch
        for c in range(10):
            p.drawRect(QtCore.QRectF((x1 + c * cw + 0.5) * s, (y + 0.5) * s, (cw - 1) * s, (ch - 1) * s))
    p.restore()


BOTTOM_FILL = (18, 20, 28)   # the bottom rows' cover (as the NEXT cover)


def paint_bottom(p, side, rows, s):
    """The bottom `rows` rows of that board covered (obs/overlay.html challengePaintBottom)."""
    import mosaic as mz
    x1, y1, x2, y2 = mz.GRID[side]
    top = y2 - rows * (y2 - y1) / mz.ROWS
    p.save()
    p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 60), max(1.0, 1.5 * s)))
    p.setBrush(QtGui.QColor(*BOTTOM_FILL, 250))
    p.drawRect(QtCore.QRectF(x1 * s, top * s, (x2 - x1) * s, (y2 - top) * s))
    p.restore()


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


class GarbageReader(QtCore.QObject):
    """challenge_garbage: reads the board's garbage rows off the screen
    GARBAGE_FPS times a second on a thread of its own (a grab takes ~6 ms:
    not on the HUD's), and says so (counted) when the count changes."""

    counted = QtCore.pyqtSignal(str, int)

    def __init__(self):
        super().__init__()
        self._target = None    # (side, geom) to read, or None
        self._thread = None
        self._last = None

    def watch(self, side, geom):
        import threading
        self._target = (side, tuple(geom)) if side and geom else None
        if self._target and (self._thread is None or not self._thread.is_alive()):
            self._last = None
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _run(self):
        import time
        import mss
        import numpy as np
        import mosaic as mz
        period = 1.0 / GARBAGE_FPS
        hold = mz.GarbageHold()   # (fewer rows only once it lasts: a line clear's flash)
        with mss.mss() as grabber:
            while self._target:
                t0 = time.perf_counter()
                side, geom = self._target
                left, top, cw = geom[0], geom[1], geom[2]
                k = cw / mz.REFERENCE_W
                x1, y1, x2, y2 = mz.GRID[side]
                region = {"left": int(left + x1 * k), "top": int(top + y1 * k),
                          "width": max(1, int((x2 - x1) * k)), "height": max(1, int((y2 - y1) * k))}
                try:
                    rows = mz.count_garbage(np.asarray(grabber.grab(region)), hold.shown)
                except Exception:
                    rows = 0
                rows = hold.update(rows, time.monotonic())
                if (side, rows) != self._last:
                    self._last = (side, rows)
                    self.counted.emit(side, rows)
                time.sleep(max(0.0, period - (time.perf_counter() - t0)))
        self._last = None


class CommentView(QtWidgets.QWidget):
    """The flowing comments, a layer of their own over every part of the HUD
    (the numbers, the result: user), drawn from the ChallengeLayer's."""

    def __init__(self, parent, layer):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.layer = layer
        layer.view = self
        self.setVisible(False)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        self.layer.paint_comments(p, self.layer.now())
        p.end()


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
        self._seen = {}      # each side: the count (cat_count) cats have come for
        self._sent = {}      # each side: cats sent this match (which clip is next)
        self._clock = QtCore.QElapsedTimer()
        self._clock.start()
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(int(1000 / FPS))
        self._timer.timeout.connect(self._tick)
        # the mosaic (challenge_mosaic): (side, strength) while it shows, the
        # game's picture on the screen (physical px: left, top, w, h, dpr),
        # and the last grabbed board, coarse
        self.mosaic = None
        self.garbage = None         # (side, rows): the garbage rows covered (challenge_garbage)
        self.bottom = None          # (side, rows): the bottom rows covered (challenge_bottom_rows)
        self.bursts = []            # ドーパミンモード (hud/dopamine.py): the bursts going now
        self._burst_seen = None     # (match, the newest event_log time of yours seen)
        self._burst_chain = 0       # bursts this match (連チャン)
        self._sounds = None         # their sounds (dopamine.Sounds), once there's one
        self._warmed = None         # the scale dopamine.warm made the texts for
        self._announcer = None      # the clear's name read out (dopamine.Announcer), once wanted
        self.comments = {}          # id -> (born, local clock; QImage of its text; lane; width) (challenge_comments)
        self.comments_ok = True     # (the HUD: switched on, over the game, out of captures)
        self.view = None            # CommentView: the comments drawn over the HUD's parts
        self.garbage_side = None
        self._garbage_reader = GarbageReader()   # (its own thread: a screen grab takes ~6 ms)
        self._garbage_reader.counted.connect(self._garbage_counted)
        self.overlay_image = None   # (side, opacity, QImage) for challenge_mosaic_style "image"
        self._pictures = {}
        self.geom = None
        self.mosaic_image = None
        self._grabber = None
        self._mosaic_timer = QtCore.QTimer(self)
        self._mosaic_timer.setInterval(int(1000 / MOSAIC_FPS))
        self._mosaic_timer.timeout.connect(self._grab_mosaic)
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
        # after the match (frozen, the result) the cats stay till the screen
        # goes black (a new match_start_t: user); nothing new comes then
        cats_on = active and CATS_ENABLED and bool(display.get("challenge_cats"))
        playing = active and not (state or {}).get("frozen")
        active = playing and not puyo
        cover = next_cover(display.get("challenge_next"), side) if active else None
        self.side = side
        match = (state or {}).get("match_start_t")
        if match != self._match:
            self._match, self.cats = match, []
            self._seen, self._sent = {}, {}
        now = self.now()
        # the cats: each player's own TETRIS / T-SPIN / PC, on that player's
        # side (user: 2P too; display.challenge_cats_side picks one)
        sides = cat_sides(display)
        self.cats = [c for c in self.cats if cats_on and c.side in sides and not c.gone(now)]
        clips = load_clips() if cats_on and playing else []
        for sd in ("left", "right"):
            count = cat_count(state, sd)
            # the first count seen is where it starts (the app opened mid-match: no flood of cats)
            new = 0 if sd not in self._seen else max(0, count - self._seen[sd])
            self._seen[sd] = count
            if not clips or sd not in sides or ((state or {}).get(sd) or {}).get("puyo"):
                continue
            for _ in range(new):
                if sum(c.side == sd for c in self.cats) >= MAX_CATS:
                    break
                sent = self._sent.get(sd, 0)
                seed = cat_seed(match, sd, sent)
                self.cats.append(Cat(seed, sd, now, pick_clip(clips, seed, sent)))
                self._sent[sd] = sent + 1
        # the garbage rows covered: read here from the screen, GARBAGE_FPS a
        # second (the server's count came up to 0.1 s late: the holes showed
        # for a moment as garbage came up, user); the server's while there's
        # no game window to read (tests)
        self.garbage_side = side if active and display.get("challenge_garbage") else None
        if self.garbage_side and self.geom:
            self._garbage_reader.watch(self.garbage_side, self.geom)
        else:
            self._garbage_reader.watch(None, None)
            g = (state or {}).get("challenge_garbage") or {}
            rows = int(g.get("rows") or 0)
            garbage = (g.get("side", side), rows) if self.garbage_side and rows > 0 and g.get("side") in ("left", "right") else None
            if garbage != self.garbage:
                self.garbage = garbage
                self.update()
        self._take_bursts(state, display, side, playing and not puyo, now)
        # the comments (scripts/comments.py): their own clock from their age at the server
        self._take_comments((state or {}).get("comments") if self.comments_ok else None)
        # the bottom rows covered (challenge_bottom_rows: so many, whatever's there)
        n = int(display.get("challenge_bottom_rows") or 0)
        bottom = (side, min(19, n)) if active and n > 0 else None
        if bottom != self.bottom:
            self.bottom = bottom
            self.update()
        info = (state or {}).get("challenge_mosaic") or {}
        s = float(info.get("strength") or 0)
        image = info.get("image")
        # the picture over the board ("image"): its opacity follows the number
        self.overlay_image = (info.get("side", side), s, self._picture(image)) if active and s > 0 and image else None
        self.mosaic = (info.get("side", side), s) if active and s > 0 and self.geom and not image else None
        self._refresh(cover)

    def _take_bursts(self, state, display, side, playing, now):
        """演出強化 (challenge_dopamine): a burst for each new TETRIS / T-SPIN /
        PC of yours (the ones going finish after the match too); 読み上げ
        (challenge_announcer): its name said — each on its own (user: the
        voice without the effects too)."""
        import dopamine
        level = display.get("challenge_dopamine", "off")
        effects = level in dopamine.LEVELS and level != "off"
        voice = bool(display.get("challenge_announcer"))
        if not effects:
            self.bursts = []
        if not effects and not voice:
            self._burst_seen = None
            return
        self.bursts = [b for b in self.bursts if not b.gone(now)]
        if effects and self._sounds is None and int(display.get("challenge_dopamine_volume", 70)) > 0:
            self._sounds = dopamine.shared_sounds()
            self._sounds.preload()
        if display.get("challenge_announcer") and self._announcer is None:   # its voice loaded ahead (~0.1 s)
            self._announcer = dopamine.shared_announcer()
            QtCore.QTimer.singleShot(0, lambda v=display.get("challenge_announcer_voice", "heart"),
                                     k=dopamine.play_level(display.get("challenge_announcer_volume", 100))[0],
                                     a=self._announcer: _safely(a.preload, v, k))
        if effects and self._warmed != round(self.scale, 3):   # the texts' slow parts made ahead, not at the first burst
            self._warmed = round(self.scale, 3)
            QtCore.QTimer.singleShot(0, lambda s=self.scale: _safely(dopamine.warm, s))
        player = (state or {}).get(side) or {}
        log = [e for e in (player.get("event_log") or []) if isinstance(e, dict) and e.get("t") is not None]
        # each entry known by what it is, not by being newer than the top one:
        # a REN break goes on top later with an earlier time, and the TETRIS
        # under it burst again every update (~10 times running: user)
        keys = {event_key(e) for e in log}
        match = (state or {}).get("match_start_t")
        if self._burst_seen is None or self._burst_seen[0] != (match, side):
            self._burst_seen = ((match, side), keys)     # (what was there before: no flood)
            self._burst_chain = 0                        # 連チャン: the bursts this match
            return
        seen = self._burst_seen[1]
        new = [e for e in log if event_key(e) not in seen]
        self._burst_seen = ((match, side), keys)
        if not playing:
            return
        for e in reversed(new):
            if not fresh(e, state):
                _log.info("an old clear turned up as new (%s at t=%s, now %s): no burst, nothing said",
                         e.get("label"), e.get("t"), game_now(state))
                continue
            # a TETRIS found a moment later to be a PERFECT CLEAR (the log entry
            # rewritten in place): its burst gives way to the PC's
            if e.get("perfect_clear"):
                self.bursts = [b for b in self.bursts if b.event_t != round(float(e["t"]), 3)]
            if dopamine.kind_of(e) and (len(self.bursts) < dopamine.MAX_BURSTS or not effects):
                self._burst_chain += 1
                burst = dopamine.Burst(f"{match}|{side}|{e['t']}", side, now, e, level if effects else "lite",
                                       int(player.get("b2b") or 0), self._burst_chain)
                if effects:
                    self.bursts.append(burst)
                    if self._sounds is None:
                        self._sounds = dopamine.shared_sounds()
                    self._sounds.play(burst, int(display.get("challenge_dopamine_volume", 70)))
                if voice:   # the clear's name said out loud (演出強化 on or not)
                    _log.info("announcer: %s (%s at t=%s, now %s)", dopamine.phrase(burst), e.get("label"),
                             e.get("t"), game_now(state))
                    if self._announcer is None:
                        self._announcer = dopamine.shared_announcer()
                    self._announcer.say(burst, int(display.get("challenge_announcer_volume", 100)),
                                        display.get("challenge_announcer_voice", "heart"))

    def _take_comments(self, info):
        if not info or not info.get("items"):
            self.comments = {}
            return
        now = self.now()
        live = {}
        for c in info["items"]:
            cid = c.get("id")
            if cid in self.comments:
                live[cid] = self.comments[cid]
                continue
            born = now - (float(info.get("now") or 0) - float(c.get("t") or 0))
            live[cid] = (born, comment_image(str(c.get("text") or ""), bool(c.get("big"))), int(c.get("lane") or 0))
        self.comments = live

    def _refresh(self, cover):
        want = bool(self.cats) or bool(self.comments) or bool(self.bursts)
        if self.mosaic:
            if not self._mosaic_timer.isActive():
                self._mosaic_timer.start()
                self._grab_mosaic()
        else:
            self._mosaic_timer.stop()
            if self.mosaic_image is not None:
                self.mosaic_image = None
                self.update()
        # (comments: 60 a second, smooth as they cross; the bursts alone 30 —
        # a whole-screen window redrawn 60 times a second was heavy)
        self._timer.setInterval(16 if self.comments else int(1000 / FPS))
        shown = (cover is not None or want or self.mosaic is not None or self.overlay_image is not None
                 or self.garbage is not None or self.garbage_side is not None or self.bottom is not None)
        self.update()
        if cover != self.cover:
            self.cover = cover
            self.update()
        self.setVisible(shown)
        self._update_view()
        if want and shown:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            self.update()
            if not self.cats:   # no cats now: their images go
                for clip in _CLIPS or ():
                    clip.release()

    def _picture(self, rel):
        """A picture under assets/ (the cat, or the user's), read once."""
        if rel not in self._pictures:
            img = QtGui.QImage(str(Path(__file__).resolve().parent.parent / "assets" / rel))
            self._pictures = {rel: None if img.isNull() else img}   # (only the one in use is kept)
        return self._pictures[rel]

    def _grab(self, box):
        """The screen under `box` (reference px) as BGRA (the HUD isn't in it)."""
        import mss
        import numpy as np
        import mosaic as mz
        left, top, cw, ch = self.geom[:4]
        k = cw / mz.REFERENCE_W
        x1, y1, x2, y2 = box
        region = {"left": int(left + x1 * k), "top": int(top + y1 * k),
                  "width": max(1, int((x2 - x1) * k)), "height": max(1, int((y2 - y1) * k))}
        if self._grabber is None:
            self._grabber = mss.mss()
        return np.asarray(self._grabber.grab(region)), k

    def _garbage_counted(self, side, rows):
        """From GarbageReader (this thread): that board's garbage rows now."""
        garbage = (side, rows) if rows > 0 and side == self.garbage_side else None
        if garbage != self.garbage:
            self.garbage = garbage
            self.update()

    def _grab_mosaic(self):
        """The board as it is on the screen now (the HUD isn't in screen
        grabs), coarse."""
        if not self.mosaic or not self.geom:
            return
        side, s = self.mosaic
        try:
            import mss
            import numpy as np
            import mosaic as mz
            left, top, cw, ch = self.geom[:4]
            k = cw / mz.REFERENCE_W
            x1, y1, x2, y2 = mz.BOARD[side]
            region = {"left": int(left + x1 * k), "top": int(top + y1 * k),
                      "width": max(1, int((x2 - x1) * k)), "height": max(1, int((y2 - y1) * k))}
            if self._grabber is None:
                self._grabber = mss.mss()
            shot = np.asarray(self._grabber.grab(region))       # BGRA
            small = np.ascontiguousarray(mz.pixelate(shot, max(1.0, mz.block_px(s) * k)))
            h, w = small.shape[:2]
            self.mosaic_image = QtGui.QImage(small.data, w, h, 4 * w, QtGui.QImage.Format.Format_RGB32).copy()
        except Exception:
            self.mosaic_image = None
        self.update()

    def _tick(self):
        now = self.now()
        if self.comments and all(now - born >= COMMENT_FLOW_S for born, _, _ in self.comments.values()):
            self.comments = {}
            self._refresh(self.cover)
        if any(b.gone(now) for b in self.bursts):
            self.bursts = [b for b in self.bursts if not b.gone(now)]
            self._refresh(self.cover)
        if any(c.gone(now) for c in self.cats):
            self.cats = [c for c in self.cats if not c.gone(now)]
            self._refresh(self.cover)
        self.update()
        self._update_view()

    def _update_view(self):
        if self.view is not None:
            self.view.setVisible(bool(self.comments) and self.isVisible())
            if self.view.isVisible():
                self.view.update()

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        s = self.scale
        if self.mosaic and self.mosaic_image is not None:
            import mosaic as mz
            x1, y1, x2, y2 = mz.BOARD[self.mosaic[0]]
            # (no smoothing: the blocks stay blocks)
            p.drawImage(QtCore.QRectF(x1 * s, y1 * s, (x2 - x1) * s, (y2 - y1) * s), self.mosaic_image)
        if self.overlay_image and self.overlay_image[2] is not None:
            import mosaic as mz
            side, opacity, img = self.overlay_image
            x1, y1, x2, y2 = mz.BOARD[side]
            target = QtCore.QRectF(x1 * s, y1 * s, (x2 - x1) * s, (y2 - y1) * s)
            p.save()
            p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
            p.setOpacity(max(0.0, min(1.0, opacity)))
            p.drawImage(target, img, QtCore.QRectF(*mz.cover_rect(img.width(), img.height(), target.x(), target.y(),
                                                                  target.width(), target.height())))
            p.restore()
        if self.garbage:
            paint_garbage(p, *self.garbage, s)
        if self.bottom:
            paint_bottom(p, *self.bottom, s)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
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
        if self.bursts:
            import dopamine
            p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            for b in self.bursts:
                dopamine.paint(p, b, s, now, self.width(), self.height())
        if self.view is None:   # (no view of their own: drawn here)
            self.paint_comments(p, now)
        p.end()

    def paint_comments(self, p, now):
        """The comments, right to left (CommentView draws them over the HUD's parts)."""
        s = self.scale
        p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        for born, img, lane in self.comments.values():
            age = now - born
            if 0 <= age < COMMENT_FLOW_S:
                w, h = img.width() * s / COMMENT_SUPER, img.height() * s / COMMENT_SUPER
                x = SCREEN_W * s - age / COMMENT_FLOW_S * (SCREEN_W * s + w)
                y = (COMMENT_TOP + lane * COMMENT_LANE_H) * s
                p.drawImage(QtCore.QRectF(x, y, w, h), img)
