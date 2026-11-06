"""縛りプレイ (challenge mode): things over your own board on the game screen
to make the game harder, drawn by the HUD only (OBS shows the game as is).

  challenge_next  "from2": NEXT from the 2nd piece covered; "all": every NEXT
  challenge_cats  a cat comes over your board for each TETRIS / T-SPIN /
                  PERFECT CLEAR this match (from match_stats), and wanders
                  about on it until the match ends

The HUD is kept out of screen captures, so the recognition still sees the
whole game. Where Windows can't keep it out (HudWindow.reading_unsafe) it
would read the covers and cats instead, so nothing here is shown there.
"""
import math
import random

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
CAT_COLORS = (   # body, darker (ears inside, stripes), eyes
    ((244, 162, 97), (214, 120, 60), (60, 40, 20)),     # orange
    ((156, 163, 175), (107, 114, 128), (30, 30, 30)),   # gray
    ((43, 43, 48), (20, 20, 24), (250, 204, 21)),       # black, yellow eyes
    ((245, 245, 244), (214, 211, 209), (59, 130, 246)),  # white, blue eyes
    ((253, 230, 190), (230, 190, 140), (60, 40, 20)),   # cream
    ((120, 85, 60), (85, 58, 40), (250, 220, 120)),     # brown
)
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


class Cat:
    """One cat: drops in at the top of the board, then walks from spot to
    spot, sitting a while at each. Its moves come from its seed, so the same
    match always gives the same cats."""

    def __init__(self, seed, side, now):
        self.rng = random.Random(seed)
        self.side = side
        x1, y1, x2, y2 = BOARD[side]
        self.size = self.rng.uniform(38, 54)
        self.colors = self.rng.choice(CAT_COLORS)
        self.speed = self.rng.uniform(55, 105)
        self.x = self.rng.uniform(x1, x2)
        self.y = y1 - 40                     # drops in from above
        self.face = self.rng.choice((-1, 1))
        self.born = now
        self.phase = self.rng.uniform(0, 6.3)
        self._target(now)

    def _target(self, now):
        x1, y1, x2, y2 = BOARD[self.side]
        m = self.size / 2
        self.tx = self.rng.uniform(x1 + m, x2 - m)
        self.ty = self.rng.uniform(y1 + m, y2 - m * 0.6)
        self.sit_until = None

    def step(self, now, dt):
        if self.sit_until is not None:
            if now >= self.sit_until:
                self._target(now)
            return
        dx, dy = self.tx - self.x, self.ty - self.y
        dist = math.hypot(dx, dy)
        go = self.speed * dt
        if dist <= go:
            self.x, self.y = self.tx, self.ty
            self.sit_until = now + self.rng.uniform(1.5, 4.5)
        else:
            self.x += dx / dist * go
            self.y += dy / dist * go
            if abs(dx) > 1:
                self.face = 1 if dx > 0 else -1

    @property
    def walking(self):
        return self.sit_until is None


def paint_cat(p, cat, s, now):
    """A cat at (cat.x, cat.y) (its feet), scaled by s (reference px -> widget px)."""
    body, dark, eye = (QtGui.QColor(*c) for c in cat.colors)
    line = QtGui.QColor(25, 25, 30)
    S = cat.size * s
    t = now + cat.phase
    bob = abs(math.sin(t * 9)) * S * 0.06 if cat.walking else 0.0
    p.save()
    p.translate(cat.x * s, cat.y * s - bob)
    p.scale(cat.face, 1)
    pen = QtGui.QPen(line, max(1.2, S * 0.045))
    pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
    # shadow
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.setBrush(QtGui.QColor(0, 0, 0, 70))
    p.drawEllipse(QtCore.QPointF(0, bob), S * 0.5, S * 0.1)
    # tail: from the back, swaying
    sway = math.sin(t * (5 if cat.walking else 2)) * S * 0.18
    tail = QtGui.QPainterPath(QtCore.QPointF(-S * 0.38, -S * 0.25))
    tail.cubicTo(-S * 0.7, -S * 0.3, -S * 0.62 + sway, -S * 0.75, -S * 0.45 + sway, -S * 0.85)
    p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    p.setPen(QtGui.QPen(line, S * 0.17, cap=QtCore.Qt.PenCapStyle.RoundCap))
    p.drawPath(tail)
    p.setPen(QtGui.QPen(body, S * 0.11, cap=QtCore.Qt.PenCapStyle.RoundCap))
    p.drawPath(tail)
    # legs (walking: stepping)
    p.setPen(pen)
    p.setBrush(body)
    step = math.sin(t * 9) * S * 0.06 if cat.walking else 0.0
    for lx, ph in ((-0.25, 1), (0.22, -1)):
        p.drawRoundedRect(QtCore.QRectF(S * lx - S * 0.07 + step * ph, -S * 0.2, S * 0.14, S * 0.2), S * 0.05, S * 0.05)
    # body
    p.drawEllipse(QtCore.QRectF(-S * 0.45, -S * 0.52, S * 0.85, S * 0.42))
    # stripes on the back
    p.setPen(QtGui.QPen(dark, S * 0.05, cap=QtCore.Qt.PenCapStyle.RoundCap))
    for k in (-0.18, -0.02):
        p.drawLine(QtCore.QPointF(S * k, -S * 0.5), QtCore.QPointF(S * (k + 0.04), -S * 0.38))
    # head
    hx, hy, hr = S * 0.32, -S * 0.62, S * 0.27
    p.setPen(pen)
    p.setBrush(body)
    for sx in (-1, 1):   # ears
        ear = QtGui.QPolygonF([QtCore.QPointF(hx + sx * hr * 0.85, hy - hr * 0.35),
                               QtCore.QPointF(hx + sx * hr * 0.75, hy - hr * 1.25),
                               QtCore.QPointF(hx + sx * hr * 0.15, hy - hr * 0.8)])
        p.drawPolygon(ear)
    p.drawEllipse(QtCore.QPointF(hx, hy), hr * 1.08, hr)
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.setBrush(dark)
    for sx in (-1, 1):   # inside of the ears
        p.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(hx + sx * hr * 0.7, hy - hr * 0.5),
                                       QtCore.QPointF(hx + sx * hr * 0.68, hy - hr * 1.0),
                                       QtCore.QPointF(hx + sx * hr * 0.32, hy - hr * 0.75)]))
    # eyes (blinking now and then), nose
    blink = (t % 3.7) < 0.15
    for sx in (-1, 1):
        ex = hx + sx * hr * 0.4 + hr * 0.15
        if blink:
            p.setPen(QtGui.QPen(line, S * 0.035))
            p.drawLine(QtCore.QPointF(ex - hr * 0.13, hy), QtCore.QPointF(ex + hr * 0.13, hy))
            p.setPen(QtCore.Qt.PenStyle.NoPen)
        else:
            p.setBrush(eye)
            p.drawEllipse(QtCore.QPointF(ex, hy - hr * 0.05), hr * 0.15, hr * 0.2)
            p.setBrush(QtGui.QColor(15, 15, 15))
            p.drawEllipse(QtCore.QPointF(ex + hr * 0.03, hy - hr * 0.05), hr * 0.07, hr * 0.15)
    p.setBrush(QtGui.QColor(236, 112, 140))
    p.drawEllipse(QtCore.QPointF(hx + hr * 0.15, hy + hr * 0.3), hr * 0.1, hr * 0.07)
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
        self._last_t = None
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
            self.cats.append(Cat(f"{match}|{side}|{len(self.cats)}", side, now))
        shown = cover is not None or bool(want)
        if cover != self.cover:
            self.cover = cover
            self.update()
        self.setVisible(shown)
        if want and shown:
            if not self._timer.isActive():
                self._last_t = None
                self._timer.start()
        else:
            self._timer.stop()
            self.update()

    def _tick(self):
        now = self.now()
        dt = 0.0 if self._last_t is None else min(0.1, now - self._last_t)
        self._last_t = now
        for cat in self.cats:
            cat.step(now, dt)
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
        for cat in sorted(self.cats, key=lambda c: c.y):   # the nearer ones over the farther
            paint_cat(p, cat, s, now)
        p.end()
