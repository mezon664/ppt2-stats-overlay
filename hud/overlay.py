"""Desktop HUD overlay: transparent, always-on-top, click-through.

Connects to the same local WebSocket server as the OBS overlay (data_server.py),
so capture/recognition runs exactly once and both displays just show it.

Layout (like TETRA e-sports): a small APM / PPS block at the lower-left (or
lower-right) of each board, optionally the recent events above it, and the
match time above the マッチポイント banner. Everything is configurable from
the settings window (tray icon -> 表示設定) or config/overlay_settings.json
"display"; see config_store.DISPLAY_DEFAULTS. The OBS overlay
(obs/overlay.html) uses the same layout numbers — keep them in sync.

The window covers the game's client area and follows it; blocks are placed in
reference coordinates (1232x692 client) and scaled with the window.

The HUD is drawn on top of the game, so a normal window would also show up in
the screen capture recognition reads. SetWindowDisplayAffinity
(WDA_EXCLUDEFROMCAPTURE) keeps it visible on the monitor but absent from
captures (verified with the same mss capture the server uses: a test window
read 100% in the capture before, 0% after), so it can overlap the game's own
badges without affecting recognition. Side effect: it also won't appear in
screenshots or OBS display capture — use the OBS browser source for that.
"""
import asyncio
import ctypes
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from config_store import load_settings, display_settings

import websockets
from PyQt6 import QtCore, QtGui, QtWidgets

try:
    import win32gui
    import win32con
    from live_capture import find_game_hwnd
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

WDA_EXCLUDEFROMCAPTURE = 0x11

REFERENCE_W, REFERENCE_H = 1232, 692  # client size all positions below refer to

# --- layout, reference px (same numbers in obs/overlay.html) ---
# Stat blocks: the edge on the board side, per stats_position.
#   "left":  right edge just left of each board's frame
#   "right": left edge just right of each board's frame
STAT_ANCHOR_X = {
    "left": {"left": 186, "right": 790},
    "right": {"left": 448, "right": 1052},
}
STAT_BOTTOM_Y = 562       # the height the user picked by hand (was 600, beside the score)
EVENT_GAP = 2             # between the event lines and the stat block
VERSUS_GAP = 4            # between the versus block and the clock below it
# display keys each draggable part moves
OFFSET_KEYS = {"stats": ("offset_x", "offset_y"),
               "clock": ("clock_offset_x", "clock_offset_y"),
               "event": ("event_offset_x", "event_offset_y"),
               "summary": ("summary_offset_x", "summary_offset_y")}
# End-of-match summary: centered between the boards, top edge at this y.
SUMMARY_TOP_Y = 120
# Match time: centered above the マッチポイント banner (x 542-693, y 579-604).
CLOCK_CENTER_X, CLOCK_BOTTOM_Y = 617, 576



BAND_RGB = (12, 22, 60)

# The HUD's own text, by display.language (event text comes from the server
# in both languages: "text" / "text_en").
UI_TEXT = {
    "ja": {"frozen": "試合終了", "paused": "試合中断中", "waiting": "スタート待ち",
           "capture_down": "認識不可",
           "summary": "試合結果", "s_apm": "APM", "s_pps": "PPS", "s_app": "APP",
           "s_lines": "送った段数", "s_pieces": "置いたミノ", "s_max_ren": "最大REN",
           "s_tetris": "TETRIS", "s_tspin": "T-SPIN", "s_pc": "パーフェクト",
           "edit_hint": "位置調整中：黄色い枠をドラッグして動かせます（設定画面の「完了」で終了）"},
    "en": {"frozen": "Match over", "paused": "Paused", "waiting": "Waiting for start",
           "capture_down": "Can't read the game",
           "summary": "Match summary", "s_apm": "APM", "s_pps": "PPS", "s_app": "APP",
           "s_lines": "Lines sent", "s_pieces": "Pieces", "s_max_ren": "Max REN",
           "s_tetris": "TETRIS", "s_tspin": "T-SPIN", "s_pc": "Perfect clear",
           "edit_hint": "Adjusting: drag the yellow boxes to move them (press Done in the settings to finish)"},
}


class WsClient(QtCore.QObject):
    state_received = QtCore.pyqtSignal(dict)

    def __init__(self, uri):
        super().__init__()
        self.uri = uri

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        asyncio.run(self._loop())

    async def _loop(self):
        while True:
            try:
                async with websockets.connect(self.uri) as ws:
                    async for message in ws:
                        self.state_received.emit(json.loads(message))
            except Exception:
                await asyncio.sleep(2)  # retry — server may not be up yet / restarted


def fmt_clock(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def set_px(widget, px):
    f = widget.font()
    f.setPixelSize(max(7, int(round(px))))
    widget.setFont(f)


class Band(QtWidgets.QWidget):
    """Dark band fading out away from the board, like TETRA's stat plates.
    fade: "left" (transparent at the left end), "right", or None (solid)."""

    def __init__(self, parent, fade="left", draggable=False):
        super().__init__(parent)
        self.fade = fade
        self.opacity = 0.85
        self.dim = False
        self.draggable = draggable
        self.drag_target = "stats"   # which offsets dragging this moves (see OFFSET_KEYS)
        self.editing = False   # position-adjust mode: outlined, and can be dragged

    def paintEvent(self, event):
        alpha = int(255 * self.opacity * (0.4 if self.dim else 1.0))
        p = QtGui.QPainter(self)
        r = self.rect()
        if self.editing:
            # Some fill everywhere so the whole box can be grabbed (fully
            # transparent pixels of a layered window let clicks through).
            p.fillRect(r, QtGui.QColor(*BAND_RGB, max(alpha, 110)))
            pen = QtGui.QPen(QtGui.QColor("#fde047"), 2, QtCore.Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawRect(r.adjusted(1, 1, -1, -1))
            return
        if alpha <= 0:
            return
        solid = QtGui.QColor(*BAND_RGB, alpha)
        if self.fade:
            clear = QtGui.QColor(*BAND_RGB, 0)
            g = QtGui.QLinearGradient(r.left(), 0, r.right(), 0)
            ends = (clear, solid) if self.fade == "left" else (solid, clear)
            g.setColorAt(0.0, ends[0])
            g.setColorAt(0.55 if self.fade == "left" else 0.45, solid)
            g.setColorAt(1.0, ends[1])
            p.fillRect(r, g)
        else:
            p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            p.setBrush(solid)
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.drawRoundedRect(QtCore.QRectF(r), 4, 4)

    # Dragging is handled by the HUD window, which moves both sides together.
    def mousePressEvent(self, event):
        if self.editing and self.draggable and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.window().drag_start(event.globalPosition(), self.drag_target)

    def mouseMoveEvent(self, event):
        if self.editing and self.draggable:
            self.window().drag_move(event.globalPosition())

    def mouseReleaseEvent(self, event):
        if self.editing and self.draggable:
            self.window().drag_end()


PLAYER_COLORS = {"left": (59, 142, 234), "right": (229, 72, 77)}        # 1P blue / 2P red
PLAYER_TEXT_COLORS = {"left": (140, 200, 255), "right": (255, 154, 158)}  # lighter, for text
# Gauge style: the value that fills the bar (higher values just show it full).
GAUGE_MAX = {"apm": 120.0, "pps": 4.0, "app": 1.0}
OUTLINE_RGB = (27, 36, 64)

BOLD, SEMI = QtGui.QFont.Weight.Bold, QtGui.QFont.Weight.DemiBold


def _font(px, weight):
    font = QtGui.QFont()
    font.setPixelSize(max(7, int(round(px))))
    font.setWeight(weight)
    return font


def text_width(px, weight, text):
    return QtGui.QFontMetricsF(_font(px, weight)).horizontalAdvance(text)


def draw_text(p, x, y, text, px, weight, color, align="left", outline=0.0, alpha=1.0):
    """Draws text with its left / right / center at x and its baseline at y,
    optionally with a dark outline (the "text" style, like the score digits).
    Returns the text's width."""
    font = _font(px, weight)
    w = QtGui.QFontMetricsF(font).horizontalAdvance(text)
    if align == "right":
        x -= w
    elif align == "center":
        x -= w / 2
    path = QtGui.QPainterPath()
    path.addText(QtCore.QPointF(x, y), font, text)
    if outline > 0:
        oc = QtGui.QColor(*OUTLINE_RGB)
        oc.setAlphaF(alpha)
        pen = QtGui.QPen(oc, outline * 2)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        p.strokePath(path, pen)
    c = QtGui.QColor(*color)
    c.setAlphaF(alpha)
    p.fillPath(path, c)
    return w


def fmt_value(key, value):
    if value is None:
        return "--"
    return f"{value:.1f}" if key == "apm" else f"{value:.2f}"   # pps / app: 2 decimals


def side_values(side):
    side = side or {}
    return {"apm": (side.get("apm") or {}).get("apm"), "pps": side.get("pps"), "app": side.get("app")}


WHITE = (255, 255, 255)
SOFT = (220, 228, 245)


class StatBlock(Band):
    """APM / PPS for one player, drawn in the chosen style ("band", "pop",
    "gauge", "text"). The content hugs the board side of the block (mode =
    stats_position); sizes are reference px x u."""

    KEYS = ("apm", "pps", "app")
    WIDTH = {"band": 92, "pop": 104, "gauge": 104, "text": 104}
    ROW_H = {"band": 21, "pop": 26, "gauge": 27, "text": 23}
    PAD = {"band": 3, "pop": 1, "gauge": 3, "text": 1}

    def __init__(self, parent, side):
        super().__init__(parent, draggable=True)
        self.side = side
        self.style = "band"
        self.mode = "left"
        self.shown = list(self.KEYS)
        self.u = 1.0
        self.values = {"apm": None, "pps": None, "app": None}

    def configure(self, style, mode, shown, u):
        self.style, self.mode, self.shown, self.u = style, mode, list(shown), u
        self.fade = mode
        n = max(1, len(self.shown))
        self.setFixedSize(int(self.WIDTH[style] * u),
                          int((self.ROW_H[style] * n + self.PAD[style] * 2) * u))
        self.update()

    def update_side(self, side):
        self.values = side_values(side)
        self.update()

    def paintEvent(self, event):
        # band / gauge draw the dark band behind; any style shows the edit outline
        if self.editing or self.style in ("band", "gauge"):
            super().paintEvent(event)
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        u, W, st = self.u, self.width(), self.style
        a = 0.45 if self.dim else 1.0
        hug_right = self.mode == "left"   # placed left of the board: hug the right edge
        for i, key in enumerate(self.shown):
            top = (self.PAD[st] + i * self.ROW_H[st]) * u
            label, value = key.upper(), fmt_value(key, self.values[key])
            if st in ("band", "text"):
                big = 17 if st == "band" else 20
                outline = 1.6 * u if st == "text" else 0
                base = top + (16 if st == "band" else 18) * u
                if hug_right:
                    x = W - 5 * u
                    vw = draw_text(p, x, base, value, big * u, SEMI, WHITE, "right", outline, a)
                    draw_text(p, x - vw - 4 * u, base, label, 12 * u, BOLD, WHITE, "right", outline, a)
                else:
                    x = 5 * u
                    lw = draw_text(p, x, base, label, 12 * u, BOLD, WHITE, "left", outline, a)
                    draw_text(p, x + lw + 4 * u, base, value, big * u, SEMI, WHITE, "left", outline, a)
            elif st == "pop":
                h = 22 * u
                lw, vw = text_width(11 * u, BOLD, label), text_width(16 * u, BOLD, value)
                pw = lw + vw + 27 * u
                x0 = W - pw - 2 * u if hug_right else 2 * u
                fill = QtGui.QColor(*PLAYER_COLORS[self.side])
                fill.setAlphaF(a)
                rim = QtGui.QColor(255, 255, 255)
                rim.setAlphaF(a)
                p.setBrush(fill)
                p.setPen(QtGui.QPen(rim, 2.5 * u))
                p.drawRoundedRect(QtCore.QRectF(x0, top + 2 * u, pw, h), h / 2, h / 2)
                base = top + 2 * u + h / 2 + 5.5 * u
                draw_text(p, x0 + 11 * u, base, label, 11 * u, BOLD, (225, 236, 255), alpha=a)
                draw_text(p, x0 + 16 * u + lw, base, value, 16 * u, BOLD, WHITE, alpha=a)
            else:  # gauge
                base = top + 14 * u
                x_l, x_r = 6 * u, W - 6 * u
                draw_text(p, x_l, base, label, 11 * u, BOLD, SOFT, alpha=a)
                draw_text(p, x_r, base, value, 15 * u, SEMI, WHITE, "right", alpha=a)
                bar = QtCore.QRectF(x_l, top + 18 * u, x_r - x_l, 4.5 * u)
                r = bar.height() / 2
                p.setPen(QtCore.Qt.PenStyle.NoPen)
                p.setBrush(QtGui.QColor(255, 255, 255, int(60 * a)))
                p.drawRoundedRect(bar, r, r)
                v = self.values[key]
                frac = 0.0 if v is None else max(0.0, min(1.0, v / GAUGE_MAX[key]))
                if frac > 0:
                    fill = QtCore.QRectF(bar)
                    fill.setWidth(bar.width() * frac)
                    if hug_right:  # grow from the board side
                        fill.moveRight(bar.right())
                    c = QtGui.QColor(*PLAYER_COLORS[self.side])
                    c.setAlphaF(a)
                    p.setBrush(c)
                    p.drawRoundedRect(fill, r, r)


class VersusBlock(Band):
    """"versus" style: one block between the boards with both players' APM /
    PPS and a split bar showing who is ahead (left = 1P blue, right = 2P red)."""

    ROW_H = 34
    WIDTH = 150

    def __init__(self, parent):
        super().__init__(parent, fade=None, draggable=True)
        self.shown = ["apm", "pps", "app"]
        self.u = 1.0
        self.values = {"left": side_values(None), "right": side_values(None)}

    def configure(self, shown, u):
        self.shown, self.u = list(shown), u
        self.setFixedSize(int(self.WIDTH * u), int((self.ROW_H * max(1, len(shown)) + 6) * u))
        self.update()

    def update_sides(self, left, right):
        self.values = {"left": side_values(left), "right": side_values(right)}
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        u, W = self.u, self.width()
        a = 0.45 if self.dim else 1.0
        for i, key in enumerate(self.shown):
            top = (3 + i * self.ROW_H) * u
            lv, rv = self.values["left"][key], self.values["right"][key]
            draw_text(p, W / 2, top + 11 * u, key.upper(), 10 * u, BOLD, SOFT, "center", alpha=a)
            draw_text(p, 7 * u, top + 15 * u, fmt_value(key, lv), 15 * u, BOLD, PLAYER_TEXT_COLORS["left"], alpha=a)
            draw_text(p, W - 7 * u, top + 15 * u, fmt_value(key, rv), 15 * u, BOLD,
                      PLAYER_TEXT_COLORS["right"], "right", alpha=a)
            bar = QtCore.QRectF(7 * u, top + 20 * u, W - 14 * u, 6 * u)
            total = (lv or 0) + (rv or 0)
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            if total <= 0:  # nothing yet: an even, neutral bar
                p.setBrush(QtGui.QColor(255, 255, 255, int(60 * a)))
                p.drawRoundedRect(bar, 3 * u, 3 * u)
                continue
            split = bar.left() + bar.width() * (lv or 0) / total
            clip = QtGui.QPainterPath()
            clip.addRoundedRect(bar, 3 * u, 3 * u)
            p.setClipPath(clip)
            for x0, x1, side in ((bar.left(), split, "left"), (split, bar.right(), "right")):
                c = QtGui.QColor(*PLAYER_COLORS[side])
                c.setAlphaF(a)
                p.fillRect(QtCore.QRectF(x0, bar.top(), x1 - x0, bar.height()), c)
            p.setClipping(False)


EVENT_RGB = (228, 228, 231)
STATE_RGB = (253, 230, 138)    # 試合終了 / 試合中断中 / スタート待ち
STATUS_RGB = (252, 165, 165)   # capture problems
POP_CLOCK_RGB = (30, 42, 85)   # the pop clock: navy pill with a white rim


class EventBlock(Band):
    """The most recent events (oldest on top, newest next to the stats),
    drawn to match the chosen style:
      band / versus  fading band, text on the board side
      gauge          the same band plus a player-color line on the board side
      pop            one small player-color pill with a white rim per event
      text           text only, white with a dark outline"""

    MAX = 5
    LINE_H = {"band": 14, "gauge": 14, "versus": 14, "text": 15, "pop": 19}

    def __init__(self, parent, side):
        super().__init__(parent, draggable=True)
        self.drag_target = "event"
        self.side = side
        self.style = "band"
        self.mode = "left"
        self.count = 3
        self.u = 1.0
        self.texts = []
        self.language = "ja"

    def configure(self, style, mode, count, u):
        self.style, self.mode, self.count, self.u = style, mode, count, u
        self.fade = mode
        self._resize()

    def update_side(self, side):
        """Shows up to `count` events, oldest on top; True if there are any."""
        log = (side or {}).get("event_log") or []   # newest first
        key = "text_en" if self.language == "en" else "text"
        texts = [e.get(key) or e.get("text", "") for e in log[:self.count]][::-1]
        if texts != self.texts:
            self.texts = texts
            self._resize()
            self.update()
        return bool(texts)

    def _px(self):
        return 10 * self.u

    def _resize(self):
        u = self.u
        widest = max((text_width(self._px(), SEMI, t) for t in self.texts), default=0)
        extra = {"pop": 18, "text": 10}.get(self.style, 17)
        n = max(1, len(self.texts))
        self.setFixedSize(int(widest + extra * u) + 2, int((self.LINE_H[self.style] * n + 4) * u))

    def paintEvent(self, event):
        st = self.style
        if self.editing or st in ("band", "gauge", "versus"):
            super().paintEvent(event)
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        u, W = self.u, self.width()
        a = 0.45 if self.dim else 1.0
        hug_right = self.mode == "left"
        if st == "gauge" and not self.editing:
            c = QtGui.QColor(*PLAYER_COLORS[self.side])
            c.setAlphaF(a)
            x = W - 2 * u if hug_right else 0
            p.fillRect(QtCore.QRectF(x, 0, 2 * u, self.height()), c)
        for i, text in enumerate(self.texts):
            top = (2 + i * self.LINE_H[st]) * u
            if st == "pop":
                tw = text_width(self._px(), SEMI, text)
                h = 16 * u
                x0 = W - tw - 16 * u if hug_right else 2 * u
                fill = QtGui.QColor(*PLAYER_COLORS[self.side])
                fill.setAlphaF(a)
                rim = QtGui.QColor(255, 255, 255)
                rim.setAlphaF(a)
                p.setBrush(fill)
                p.setPen(QtGui.QPen(rim, 1.5 * u))
                p.drawRoundedRect(QtCore.QRectF(x0, top + 1 * u, tw + 14 * u, h), h / 2, h / 2)
                draw_text(p, x0 + 7 * u, top + 12.5 * u, text, self._px(), SEMI, WHITE, alpha=a)
                continue
            base = top + 11 * u
            outline = 1.0 * u if st == "text" else 0
            color = WHITE if st == "text" else EVENT_RGB
            if hug_right:
                draw_text(p, W - 6 * u, base, text, self._px(), SEMI, color, "right", outline, a)
            else:
                draw_text(p, 6 * u, base, text, self._px(), SEMI, color, "left", outline, a)


class ClockBlock(Band):
    """Match time (and the match state / capture status under it), drawn to
    match the chosen style:
      band / versus  rounded dark box
      gauge          square box with a blue / red line along the bottom
      pop            navy pill with a white rim
      text           text only, white with a dark outline
    Game time, so it stops while paused and resumes after."""

    def __init__(self, parent):
        super().__init__(parent, fade=None, draggable=True)
        self.drag_target = "clock"
        self.style = "band"
        self.u = 1.0
        self.clock_text, self.state_text, self.status_text = "0:00", "", ""

    def configure(self, style, u):
        self.style, self.u = style, u
        self._resize()

    def set_texts(self, clock, state, status):
        if (clock, state, status) != (self.clock_text, self.state_text, self.status_text):
            self.clock_text, self.state_text, self.status_text = clock, state, status
            self._resize()
            self.update()

    def _lines(self):
        lines = [(self.clock_text, 18, BOLD, WHITE, 20)]
        if self.state_text:
            lines.append((self.state_text, 10, SEMI, STATE_RGB, 13))
        if self.status_text:
            lines.append((self.status_text, 10, SEMI, STATUS_RGB, 13))
        return lines

    def _pad(self):
        return {"pop": (13, 4), "text": (4, 1)}.get(self.style, (8, 2))

    def _resize(self):
        u = self.u
        lines = self._lines()
        widest = max(text_width(px * u, w, t) for t, px, w, _, _ in lines)
        px_pad, py_pad = self._pad()
        h = sum(lh for *_, lh in lines) + py_pad * 2 + (3 if self.style == "gauge" else 0)
        self.setFixedSize(int(widest + px_pad * 2 * u) + 2, int(h * u))

    def paintEvent(self, event):
        st, u = self.style, self.u
        if self.editing:
            super().paintEvent(event)   # the draggable outline instead of the style's box
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        a = 0.45 if self.dim else 1.0
        r = QtCore.QRectF(self.rect())
        band = QtGui.QColor(*BAND_RGB)
        band.setAlphaF(self.opacity * a)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        if self.editing:
            pass
        elif st in ("band", "versus"):
            p.setBrush(band)
            p.drawRoundedRect(r, 4 * u, 4 * u)
        elif st == "gauge":
            p.fillRect(r, band)
            line_h = 2.5 * u
            for x0, x1, side in ((0, r.width() / 2, "left"), (r.width() / 2, r.width(), "right")):
                c = QtGui.QColor(*PLAYER_COLORS[side])
                c.setAlphaF(a)
                p.fillRect(QtCore.QRectF(x0, r.height() - line_h, x1 - x0, line_h), c)
        elif st == "pop":
            fill = QtGui.QColor(*POP_CLOCK_RGB)
            fill.setAlphaF(max(self.opacity, 0.6) * a)
            rim = QtGui.QColor(255, 255, 255)
            rim.setAlphaF(a)
            inner = r.adjusted(1.5 * u, 1.5 * u, -1.5 * u, -1.5 * u)
            radius = min(inner.height() / 2, 12 * u)
            p.setBrush(fill)
            p.setPen(QtGui.QPen(rim, 2.5 * u))
            p.drawRoundedRect(inner, radius, radius)
        outline = 1.6 * u if st == "text" else 0
        y = self._pad()[1] * u
        for text, px, weight, color, lh in self._lines():
            y += lh * u
            draw_text(p, r.width() / 2, y - (4 if lh == 20 else 3) * u, text, px * u, weight,
                      color, "center", outline, a)


SUMMARY_ROWS = (   # (key in the row data, label key in UI_TEXT, format)
    ("apm", "s_apm", "{:.1f}"),
    ("pps", "s_pps", "{:.2f}"),
    ("app", "s_app", "{:.2f}"),
    ("lines_sent", "s_lines", "{:d}"),
    ("pieces", "s_pieces", "{:d}"),
    ("max_ren", "s_max_ren", "{:d}"),
    ("tetris", "s_tetris", "{:d}"),
    ("tspin", "s_tspin", "{:d}"),
    ("perfect_clear", "s_pc", "{:d}"),
)


def summary_side(side):
    """One player's row values for the summary, from their snapshot."""
    side = side or {}
    stats = side.get("match_stats") or {}
    out = side_values(side)
    out.update({k: stats.get(k) for k in ("lines_sent", "pieces", "max_ren", "tetris", "tspin", "perfect_clear")})
    return out


class SummaryBlock(Band):
    """End-of-match summary: both players' totals side by side, shown while
    the finished match is on screen (frozen). Label in the middle, 1P on the
    left in blue, 2P on the right in red; the box follows the chosen style."""

    WIDTH = 212   # fits between the left NEXT column and the right HOLD box
    TITLE_H = 24
    ROW_H = 16

    def __init__(self, parent):
        super().__init__(parent, fade=None, draggable=True)
        self.drag_target = "summary"
        self.style = "band"
        self.u = 1.0
        self.language = "ja"
        self.duration = 0.0
        self.sides = {"left": summary_side(None), "right": summary_side(None)}

    def configure(self, style, language, u):
        self.style, self.language, self.u = style, language, u
        self.setFixedSize(int(self.WIDTH * u),
                          int((self.TITLE_H + self.ROW_H * len(SUMMARY_ROWS) + 8) * u))
        self.update()

    def update_match(self, state):
        self.duration = state.get("match_elapsed_s", 0) or 0
        self.sides = {"left": summary_side(state.get("left")), "right": summary_side(state.get("right"))}
        self.update()

    def paintEvent(self, event):
        st, u = self.style, self.u
        if self.editing:
            super().paintEvent(event)
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        a = 0.45 if self.dim else 1.0
        r = QtCore.QRectF(self.rect())
        if not self.editing:
            if st == "pop":
                fill = QtGui.QColor(*POP_CLOCK_RGB)
                fill.setAlphaF(max(self.opacity, 0.6) * a)
                rim = QtGui.QColor(255, 255, 255)
                rim.setAlphaF(a)
                p.setBrush(fill)
                p.setPen(QtGui.QPen(rim, 2.5 * u))
                p.drawRoundedRect(r.adjusted(1.5 * u, 1.5 * u, -1.5 * u, -1.5 * u), 12 * u, 12 * u)
            elif st != "text":
                band = QtGui.QColor(*BAND_RGB)
                band.setAlphaF(max(self.opacity, 0.5) * a)   # a table needs some backing to be readable
                p.setPen(QtCore.Qt.PenStyle.NoPen)
                p.setBrush(band)
                p.drawRoundedRect(r, (0 if st == "gauge" else 6) * u, (0 if st == "gauge" else 6) * u)
                if st == "gauge":
                    for x0, x1, side in ((0, r.width() / 2, "left"), (r.width() / 2, r.width(), "right")):
                        c = QtGui.QColor(*PLAYER_COLORS[side])
                        c.setAlphaF(a)
                        p.fillRect(QtCore.QRectF(x0, 0, x1 - x0, 2.5 * u), c)
        ui = UI_TEXT[self.language]
        outline = 1.3 * u if st == "text" else 0
        W = r.width()
        title = f"{ui['summary']}  {fmt_clock(self.duration)}"
        draw_text(p, W / 2, 17 * u, title, 13 * u, BOLD, WHITE, "center", outline, a)
        for i, (key, label_key, fmt) in enumerate(SUMMARY_ROWS):
            base = (self.TITLE_H + 4 + i * self.ROW_H + 12) * u
            draw_text(p, W / 2, base, ui[label_key], 10 * u, SEMI, SOFT, "center", outline, a)
            for side, x, align in (("left", 12 * u, "left"), ("right", W - 12 * u, "right")):
                v = self.sides[side].get(key)
                text = "--" if v is None else fmt.format(v)
                draw_text(p, x, base, text, 13 * u, BOLD, PLAYER_TEXT_COLORS[side], align, outline, a)


class HudWindow(QtWidgets.QWidget):
    # New offset_x, offset_y (reference px) while the user drags the stats;
    # finished=True on release (the settings window saves then).
    offset_dragged = QtCore.pyqtSignal(str, int, int, bool)
    language_changed = QtCore.pyqtSignal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.edit_mode = False
        self._drag = None
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.Tool
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)

        self.stats = {"left": StatBlock(self, "left"), "right": StatBlock(self, "right")}
        self.versus = VersusBlock(self)
        self.summary = SummaryBlock(self)
        self.events = {"left": EventBlock(self, "left"), "right": EventBlock(self, "right")}
        self.clock = ClockBlock(self)
        self.edit_hint = QtWidgets.QLabel(
            "位置調整中：黄色い枠をドラッグして動かせます（設定画面の「完了」で終了）", self)
        self.edit_hint.setStyleSheet(
            "color:#111; background:#fde047; padding:4px 10px; border-radius:4px; font-weight:700;")
        self.edit_hint.setVisible(False)
        self._hwnd = None
        self._last_geom = None
        self._size = (REFERENCE_W, REFERENCE_H)
        self._scale = 1.0
        self._last_state = {}
        self._last_server_display = None
        self._local_until = 0.0
        # Applied right away from the file, then kept in step with the server's
        # copy (state["display"]) and the settings window.
        self.display = display_settings(settings)
        self._layout()

        if settings["hud"]["follow_game"]:
            self._follow = QtCore.QTimer(self)
            self._follow.timeout.connect(self._follow_game_window)
            self._follow.start(500)
        else:
            pos = settings["hud"]["position"]
            self.move(pos["x"], pos["y"])

        self.ws_client = WsClient(f"ws://{settings['server']['host']}:{settings['server']['port']}")
        self.ws_client.state_received.connect(self.on_state)
        self.ws_client.start()

    # --- layout ---
    # After a change made here (settings window / drag), the server's copy of
    # the settings is ignored this long: it re-reads the file only every ~1s,
    # so while the user is still adjusting it sends values from a moment ago,
    # and applying them made the display jump back and forth.
    LOCAL_PRIORITY_S = 3.0

    def apply_display(self, display, local=False):
        """local=True: from the settings window or a drag — applied at once,
        without waiting for the server to pick up the saved file."""
        if local:
            self._local_until = time.monotonic() + self.LOCAL_PRIORITY_S
        if display != self.display:
            old_lang = self.display["language"]
            self.display = display
            self._layout()
            if display["language"] != old_lang:
                self.language_changed.emit(display["language"])

    def _layout(self):
        w, h = self._size
        s = self._scale
        d = self.display
        u = s * d["scale"]
        mode = d["stats_position"]
        shown = [k for k in StatBlock.KEYS if d[f"show_{k}"]]
        self.resize(int(w), int(h))
        for side in ("left", "right"):
            stat, ev = self.stats[side], self.events[side]
            for band in (stat, ev):
                band.opacity = d["background_opacity"]
            if shown and d["style"] != "versus":
                stat.configure(d["style"], mode, shown, u)
            ev.language = d["language"]
            ev.configure(d["style"], mode, d["event_log_count"], u)
        self.versus.opacity = d["background_opacity"]
        if shown and d["style"] == "versus":
            self.versus.configure(shown, u)
        self.clock.opacity = d["background_opacity"]
        self.clock.configure(d["style"], u)
        self.summary.opacity = d["background_opacity"]
        self.summary.configure(d["style"], d["language"], u)
        self._place()

    def _place(self):
        """Positions everything whose size depends on content: the stat blocks
        (bottom-anchored beside the score), the events stacked above them, and
        the clock (bottom-anchored above the マッチポイント banner)."""
        s, d = self._scale, self.display
        u = s * d["scale"]
        mode = d["stats_position"]
        any_stat = any(d[f"show_{k}"] for k in StatBlock.KEYS)
        versus = d["style"] == "versus"
        shown = any_stat and not versus
        for side in ("left", "right"):
            stat, ev = self.stats[side], self.events[side]
            anchor_x = (STAT_ANCHOR_X[mode][side] + d["offset_x"]) * s
            bottom = (STAT_BOTTOM_Y + d["offset_y"]) * s
            stat.setVisible(shown)
            if shown:
                x = anchor_x - stat.width() if mode == "left" else anchor_x
                stat.move(int(x), int(bottom - stat.height()))
                bottom -= stat.height() + EVENT_GAP * u
            # (Not ev.isVisible(): that is also False whenever the window
            # itself isn't shown, which would skip placing it.)
            show_events = d["show_event_log"] and ev.update_side(self._last_state.get(side))
            ev.setVisible(show_events)
            if show_events:
                # stacked above the stats by default; its own offsets move it from there
                ev.adjustSize()
                ex = anchor_x + d["event_offset_x"] * s
                x = ex - ev.width() if mode == "left" else ex
                ev.move(int(x), int(bottom + d["event_offset_y"] * s - ev.height()))
        self.clock.setVisible(d["show_clock"])
        self.clock.adjustSize()
        clock_top = CLOCK_BOTTOM_Y * s - self.clock.height()   # default spot (the versus block uses it)
        self.clock.move(int((CLOCK_CENTER_X + d["clock_offset_x"]) * s - self.clock.width() / 2),
                        int(clock_top + d["clock_offset_y"] * s))
        # summary: while a finished match is on screen (or always while
        # positioning, so it can be found and dragged)
        show_summary = d["show_summary"] and (self._summary_ready() or self.edit_mode)
        self.summary.setVisible(show_summary)
        if show_summary:
            self.summary.move(int((CLOCK_CENTER_X + d["summary_offset_x"]) * s - self.summary.width() / 2),
                              int((SUMMARY_TOP_Y + d["summary_offset_y"]) * s))
        # versus: centered between the boards, just above the clock's default
        # spot (or where the clock would be); the APM/PPS offsets move it.
        self.versus.setVisible(versus and any_stat)
        if versus and any_stat:
            vb = (clock_top - VERSUS_GAP * u) if d["show_clock"] else CLOCK_BOTTOM_Y * s
            self.versus.move(int((CLOCK_CENTER_X + d["offset_x"]) * s - self.versus.width() / 2),
                             int(vb + d["offset_y"] * s - self.versus.height()))

    def _follow_game_window(self):
        """Covers the game's client area as it moves or resizes. Win32 reports
        physical pixels; Qt positions in logical ones."""
        if not HAS_WIN32:
            return
        try:
            if self._hwnd is None or not win32gui.IsWindow(self._hwnd):
                self._hwnd = find_game_hwnd()
            if self._hwnd is None or win32gui.IsIconic(self._hwnd):
                return
            _, _, cw, ch = win32gui.GetClientRect(self._hwnd)
            left, top = win32gui.ClientToScreen(self._hwnd, (0, 0))
        except Exception:
            self._hwnd = None
            return
        if cw <= 0 or ch <= 0:
            return
        dpr = self.screen().devicePixelRatio() if self.screen() else 1.0
        geom = (left, top, cw, ch, dpr)
        if geom == self._last_geom:
            return
        self._last_geom = geom
        self.move(int(left / dpr), int(top / dpr))
        self._size = (cw / dpr, ch / dpr)
        self._scale = cw / (REFERENCE_W * dpr)
        self._layout()

    # --- data ---
    def on_state(self, state):
        self._last_state = state
        # Follow the server's copy only when IT changes (someone edited the
        # file): a change made in the settings window is applied here at once,
        # and the server's copy lags it by up to ~1s — applying that stale copy
        # would flick the display back for a moment.
        server_display = state.get("display")
        if server_display and server_display != self._last_server_display:
            self._last_server_display = server_display
            if time.monotonic() >= self._local_until:
                self.apply_display(display_settings({"display": server_display}))
        ui = UI_TEXT[self.display["language"]]
        if state.get("frozen"):
            text = ui["frozen"]
        elif state.get("paused"):
            text = ui["paused"]
        elif state.get("waiting_start"):
            text = ui["waiting"]
        else:
            text = ""
        cap = state.get("capture", {})
        stale = cap.get("ok") is False
        msg = (cap.get("message_en") if self.display["language"] == "en" else None) or cap.get("message")
        self.clock.set_texts(fmt_clock(state.get("match_elapsed_s", 0)), text,
                             f"⚠ {msg or ui['capture_down']}" if stale else "")
        for side in ("left", "right"):
            self.stats[side].update_side(state.get(side))
        self.versus.update_sides(state.get("left"), state.get("right"))
        self.summary.update_match(state)
        # Dim rather than hide when capture is down: the numbers shown are the
        # last real measurement, not a fabricated live one.
        for band in (*self.stats.values(), *self.events.values(), self.versus, self.clock, self.summary):
            band.dim = stale
            band.update()
        self._place()

    def _summary_ready(self):
        """A match was played and has ended: the server froze the numbers."""
        st = self._last_state
        return bool(st.get("frozen")) and (st.get("match_elapsed_s") or 0) > 0

    # --- position adjust (drag) mode, toggled from the settings window ---
    def set_edit_mode(self, on):
        """While on, the stat blocks are outlined and can be dragged. The window
        stops being click-through so it can receive the mouse; only the blocks
        themselves catch clicks (transparent pixels still pass through to the
        game), and it goes back to click-through when done."""
        if on == self.edit_mode:
            return
        self.edit_mode = on
        self._drag = None
        for band in (*self.stats.values(), *self.events.values(), self.versus, self.clock, self.summary):
            band.editing = on
            band.setCursor(QtCore.Qt.CursorShape.SizeAllCursor if on else QtCore.Qt.CursorShape.ArrowCursor)
            band.update()
        self.edit_hint.setVisible(on)
        if on:
            self.edit_hint.setText(UI_TEXT[self.display["language"]]["edit_hint"])
            set_px(self.edit_hint, max(11, 13 * self._scale))
            self.edit_hint.adjustSize()
            self.edit_hint.move(int(self.width() / 2 - self.edit_hint.width() / 2), int(70 * self._scale))
        self._place()   # e.g. show the summary box while positioning
        if self.isVisible():
            self.apply_click_through(not on and self.settings["hud"]["click_through"])

    def drag_start(self, global_pos, target):
        """target: which offsets the dragged block owns — "stats", "clock" or "event"."""
        kx, ky = OFFSET_KEYS[target]
        self._drag = (global_pos, target, self.display[kx], self.display[ky])

    def drag_move(self, global_pos):
        if self._drag is None:
            return
        origin, target, ox, oy = self._drag
        kx, ky = OFFSET_KEYS[target]
        # screen px -> reference px, so the offset means the same at any window size
        dx = (global_pos.x() - origin.x()) / max(self._scale, 1e-6)
        dy = (global_pos.y() - origin.y()) / max(self._scale, 1e-6)
        display = display_settings({"display": {**self.display,
                                                kx: int(round(ox + dx)),
                                                ky: int(round(oy + dy))}})
        self.apply_display(display, local=True)
        self.offset_dragged.emit(target, display[kx], display[ky], False)

    def drag_end(self):
        if self._drag is not None:
            target = self._drag[1]
            kx, ky = OFFSET_KEYS[target]
            self._drag = None
            self.offset_dragged.emit(target, self.display[kx], self.display[ky], True)

    def apply_click_through(self, enabled):
        if not HAS_WIN32:
            return
        hwnd = int(self.winId())
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        if enabled:
            ex_style |= win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT
        else:
            ex_style &= ~win32con.WS_EX_TRANSPARENT
            ex_style |= win32con.WS_EX_LAYERED
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)

    def hide_from_capture(self):
        ctypes.windll.user32.SetWindowDisplayAffinity(int(self.winId()), WDA_EXCLUDEFROMCAPTURE)


def make_tray_icon():
    """A small generic icon drawn in code (no image file to ship)."""
    pm = QtGui.QPixmap(32, 32)
    pm.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pm)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.setBrush(QtGui.QColor(*BAND_RGB))
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.drawRoundedRect(0, 0, 32, 32, 6, 6)
    for i, (x, hgt, color) in enumerate(((5, 12, "#60a5fa"), (14, 20, "#ffffff"), (23, 16, "#f87171"))):
        p.setBrush(QtGui.QColor(color))
        p.drawRect(x, 27 - hgt, 5, hgt)
    p.end()
    return QtGui.QIcon(pm)


def main():
    from settings_window import SettingsWindow

    settings = load_settings()
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # closing the settings window keeps the HUD
    win = HudWindow(settings)
    if settings["hud"]["visible"]:
        win.show()
        # These need the native window handle, which exists only after show().
        # Click-through matters even more now: the window covers the whole game.
        if settings["hud"]["click_through"]:
            win.apply_click_through(True)
        if settings["hud"]["hide_from_capture"]:
            win.hide_from_capture()

    settings_win = SettingsWindow(drag_available=True)
    settings_win.display_changed.connect(lambda d: win.apply_display(d, local=True))
    settings_win.edit_mode_changed.connect(win.set_edit_mode)
    win.offset_dragged.connect(settings_win.set_offset_from_hud)

    tray = QtWidgets.QSystemTrayIcon(make_tray_icon(), app)
    tray.setToolTip("PPT2 Stats Overlay")
    menu = QtWidgets.QMenu()
    act_settings = menu.addAction("", settings_win.open)
    menu.addSeparator()
    act_quit = menu.addAction("", app.quit)
    tray.setContextMenu(menu)

    def tray_language(lang):
        act_settings.setText("Display settings…" if lang == "en" else "表示設定…")
        act_quit.setText("Quit" if lang == "en" else "終了")
    tray_language(win.display["language"])
    win.language_changed.connect(tray_language)
    tray.activated.connect(lambda reason: settings_win.open()
                           if reason == QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick else None)
    tray.show()
    # Open the settings right away, so someone launching the tool for the
    # first time sees where to change things; closing it keeps the HUD.
    settings_win.open()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
