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
import logging
import sys
import threading
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "scripts"))
import opener_stats
from challenge import ChallengeLayer
from config_store import DISPLAY_DEFAULTS, DISPLAY_RANGES, load_settings, display_settings, part_value, opener_language

log_hud = logging.getLogger("hud")

from collections import deque

import numpy as np

import websockets
from PyQt6 import QtCore, QtGui, QtNetwork, QtWidgets

try:
    import win32gui
    import win32con
    from live_capture import find_game_hwnd
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

WDA_EXCLUDEFROMCAPTURE = 0x11
WS_EX_NOACTIVATE = 0x08000000

REFERENCE_W, REFERENCE_H = 1232, 692  # client size all positions below refer to

# --- layout, reference px (same numbers in obs/overlay.html) ---
# Stat blocks: the edge on the board side, per stats_position.
#   "left":  right edge just left of each board's frame
#   "right": left edge just right of each board's frame
STAT_ANCHOR_X = {
    "left": {"left": 184, "right": 789.2},   # 1.3 px short of each board frame's white line (measured: 185.3 / 790.5)
    "right": {"left": 448, "right": 1052},
}
# Against a Puyo player the Tetris board's frame is wider on the outer side:
# its white edge line sits at x 173 (1P) / 778 (2P) instead of 186 / 791
# (measured on burst_vs_puyo, burst_self_puyo, burst_english2). The stats
# move in by this much then, so they still run along the line (user: they
# looked shifted right). The far edge (right-hand mode) doesn't move.
VS_PUYO_SHIFT_X = {"left": -12, "right": 0}   # by display.stats_position
STAT_BOTTOM_Y = 562       # the height the user picked by hand (was 600, beside the score)
EVENT_GAP = 2             # between the event lines and the stat block
VERSUS_GAP = 4            # between the versus block and the clock below it
# display keys each draggable part moves
OFFSET_KEYS = {"stats": ("offset_x", "offset_y"),
               "clock": ("clock_offset_x", "clock_offset_y"),
               "event": ("event_offset_x", "event_offset_y"),
               "summary": ("summary_offset_x", "summary_offset_y"),
               "session": ("session_offset_x", "session_offset_y"),
               "stats_left": ("stats_left_offset_x", "stats_left_offset_y"),        # each player's
               "stats_right": ("stats_right_offset_x", "stats_right_offset_y"),     # numbers on their own
               "opener": ("opener_offset_x", "opener_offset_y"),                    # opener names, both
               "opener_left": ("opener_left_offset_x", "opener_left_offset_y"),     # and each player's
               "opener_right": ("opener_right_offset_x", "opener_right_offset_y")}
# the part (display.parts, its size) each drag target belongs to
TARGET_PART = {"stats": "stats", "stats_left": "stats", "stats_right": "stats", "clock": "clock",
               "event": "events", "summary": "summary", "session": "clock", "opener": "opener", "opener_left": "opener",
               "opener_right": "opener"}
WHEEL_SCALE_STEP = 0.05   # one wheel notch over a part while positioning: its size by this
# End-of-match summary: centered between the boards, top edge at this y.
SUMMARY_TOP_Y = 120
# Match time: centered above the マッチポイント banner (x 542-693, y 579-604).
SESSION_TOP_Y = 22   # 今日の成績: centered between the boards, top edge here
CLOCK_CENTER_X, CLOCK_BOTTOM_Y = 615.6, 576   # midway between the boards (white lines at 185.9 / 439.9 and 791.3 / 1045.4; was 617)



BAND_RGB = (0, 0, 0)
LINE_RGB = (255, 255, 255)   # the minimal design's lines (display.line_color; see set_colors)

# The HUD's own text, by display.language (event text comes from the server
# in both languages: "text" / "text_en").
UI_TEXT = {
    "ja": {"frozen": "試合終了", "paused": "試合中断中", "waiting": "スタート待ち",
           "capture_down": "認識不可",
           "summary": "試合結果", "s_opener": "開幕", "s_apm": "APM", "s_pps": "PPS", "s_app": "APP",
           "s_lines": "送った段数", "s_pieces": "置いたミノ", "s_max_ren": "最大REN",
           "s_tetris": "TETRIS", "s_tspin": "T-SPIN", "s_pc": "パーフェクト",
           "s_tss": "T-SPIN Single", "s_tsd": "T-SPIN Double", "s_tst": "T-SPIN Triple", "s_tsm": "T-SPIN Mini",
           "edit_hint": "位置調整中：黄色い枠をドラッグで移動、マウスホイールで大きさ変更（設定画面の「完了」で終了）",
           "edit_hint_zones": "位置調整中：枠をドラッグで移動、ホイールで大きさ変更。赤い場所（T-SPIN のバナーなどを読む場所）に重なる表示は、ゲーム画面に出ません（赤い枠）",
           "opener_sample": "開幕テンプレ名"},
    "en": {"frozen": "Match over", "paused": "Paused", "waiting": "Waiting for start",
           "capture_down": "Can't read the game",
           "summary": "Match summary", "s_opener": "Opener", "s_apm": "APM", "s_pps": "PPS", "s_app": "APP",
           "s_lines": "Lines sent", "s_pieces": "Pieces", "s_max_ren": "Max combo",
           "s_tetris": "TETRIS", "s_tspin": "T-SPIN", "s_pc": "Perfect clear",
           "s_tss": "T-SPIN Single", "s_tsd": "T-SPIN Double", "s_tst": "T-SPIN Triple", "s_tsm": "T-SPIN Mini",
           "edit_hint": "Adjusting: drag a yellow box to move it, use the mouse wheel to resize it (press Done in the settings to finish)",
           "edit_hint_zones": "Adjusting: drag a box to move it, wheel to resize. A part over the red areas (where T-SPIN banners etc. are read) won't show on the game screen (red box)",
           "opener_sample": "Opener name"},
}


class WsClient(QtCore.QObject):
    state_received = QtCore.pyqtSignal(dict)

    def __init__(self, uri):
        super().__init__()
        self.uri = uri
        self._stop_event = threading.Event()
        self._async_loop = None
        self._ws = None
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, name="pptetrics-hud-ws", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._async_loop is not None and self._ws is not None:
            try:
                asyncio.run_coroutine_threadsafe(self._ws.close(), self._async_loop).result(timeout=1)
            except Exception:
                pass
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)

    def _run(self):
        asyncio.run(self._loop())

    async def _loop(self):
        self._async_loop = asyncio.get_running_loop()
        while not self._stop_event.is_set():
            try:
                async with websockets.connect(self.uri, open_timeout=1) as ws:
                    self._ws = ws
                    async for message in ws:
                        if self._stop_event.is_set():
                            return
                        self.state_received.emit(json.loads(message))
            except Exception:
                if not self._stop_event.is_set():
                    await asyncio.sleep(2)  # retry — server may not be up yet / restarted
            finally:
                self._ws = None
        self._async_loop = None


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
        self.square = False   # the "simple" style: a plain square box, no fade, no rounding
        self.opacity = 0.85
        self.dim = False
        self.draggable = draggable
        self.drag_target = "stats"   # which offsets dragging this moves (see OFFSET_KEYS)
        self.editing = False   # position-adjust mode: outlined, and can be dragged

    def paintEvent(self, event):
        use_colors(self)
        alpha = int(255 * self.opacity * (0.4 if self.dim else 1.0))
        p = QtGui.QPainter(self)
        r = self.rect()
        if self.editing:
            # Some fill everywhere so the whole box can be grabbed (fully
            # transparent pixels of a layered window let clicks through).
            p.fillRect(r, QtGui.QColor(*BAND_RGB, max(alpha, 110)))
            pen = QtGui.QPen(QtGui.QColor(edit_color(self)), 2, QtCore.Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawRect(r.adjusted(1, 1, -1, -1))
            return
        if alpha <= 0:
            return
        solid = QtGui.QColor(*BAND_RGB, alpha)
        if self.square:
            p.fillRect(r, solid)
        elif self.fade:
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

    def wheelEvent(self, event):   # positioning: the wheel resizes this part
        if self.editing and self.draggable:
            self.window().wheel_resize(self.drag_target, event.angleDelta().y())
            event.accept()

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
GAUGE_MAX = {"apm": 120.0, "pps": 4.0, "app": 1.0, "attack": 100.0, "pieces": 300.0, "ren": 12.0, "b2b": 10.0}
OUTLINE_RGB = (27, 36, 64)

# display.text_weight (0-100, a slider) -> (BOLD, SEMI, THICKEN); same as
# obs/overlay.html's weightStyle. Fonts mostly come in Regular and Bold only
# (asking for 800/900 drew plain Bold — user report: the setting changed
# nothing), so the slider runs: Regular thickened a little (0-30), then Bold
# thickened more (30-100) — stroked in its own color, THICKEN x the font
# size wide, which works with any font. 65 = the old "bold" (Bold + 0.05).
WEIGHT_SWITCH = 30
REGULAR_THICKEN_MAX, BOLD_THICKEN_MAX = 0.04, 0.10


def weight_style(value):
    if isinstance(value, str):   # the old choice values
        value = {"normal": 30, "bold": 65}.get(value, 65)
    v = min(max(float(value), 0.0), 100.0)
    if v < WEIGHT_SWITCH:
        w = QtGui.QFont.Weight.Normal
        return w, w, REGULAR_THICKEN_MAX * v / WEIGHT_SWITCH
    return QtGui.QFont.Weight.Bold, QtGui.QFont.Weight.Bold, \
        BOLD_THICKEN_MAX * (v - WEIGHT_SWITCH) / (100 - WEIGHT_SWITCH)


BOLD, SEMI, THICKEN = weight_style(65)
# display.text_outline: black outline around every text, this x the font size.
# Black, not the "text" style's navy OUTLINE_RGB: navy is nearly the color of
# the band / clock / summary boxes, so on them the outline didn't show (user
# report: only some text got an outline).
TEXT_OUTLINE_RATIO = 0.10
# The opener (開幕テンプレ) names are thickened less than the rest (user's
# request: just those a little thinner). Same share in obs/overlay.html.
OPENER_NAME_THICKEN = 0.4
TEXT_OUTLINE_RGB = (0, 0, 0)
TEXT_OUTLINE = 0.0


def set_text_style(weight, outline, width_pct=None):
    """width_pct: display.text_outline_width, the outline's thickness as % of
    the text size (None: the original 10%)."""
    global BOLD, SEMI, THICKEN, TEXT_OUTLINE
    BOLD, SEMI, THICKEN = weight_style(weight)
    ratio = TEXT_OUTLINE_RATIO if width_pct is None else width_pct / 100.0
    TEXT_OUTLINE = ratio if outline else 0.0


def hex_rgb(value):
    v = value.lstrip("#")
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    """a moved t of the way toward b (RGB tuples)."""
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def set_colors(bg_hex, text_hex, line_hex="#ffffff"):
    """display.bg_color / text_color (and line_color, the minimal design's
    lines). The rest follow from bg / text so any pair stays consistent; with
    the defaults they come out about the same as the original fixed colors."""
    global BAND_RGB, WHITE, SOFT, EVENT_RGB, POP_CLOCK_RGB, OUTLINE_RGB, TEXT_OUTLINE_RGB, LINE_RGB
    BAND_RGB, WHITE, LINE_RGB = hex_rgb(bg_hex), hex_rgb(text_hex), hex_rgb(line_hex)
    SOFT = mix(WHITE, BAND_RGB, 0.12)
    EVENT_RGB = mix(WHITE, BAND_RGB, 0.1)
    POP_CLOCK_RGB = mix(BAND_RGB, (255, 255, 255), 0.08)
    OUTLINE_RGB = mix(BAND_RGB, (255, 255, 255), 0.06)
    # the "outline the text" edge contrasts with the text: black around light
    # text, white around dark text (black on dark text just thickened it into a blob)
    TEXT_OUTLINE_RGB = (0, 0, 0) if luminance(WHITE) >= 0.5 else (255, 255, 255)


def luminance(rgb):
    return (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255


FONT_FAMILY = ""        # display.font_family ("" = the system UI font)
_loaded_font_files = {}  # path -> family registered from it
USER_FONTS_DIR = ROOT_DIR / "assets"


def set_font(family, font_file):
    """display.font_family / font_file. A file (under assets/user_fonts/) is
    registered with Qt once; its own family name is used if `family` is
    empty or doesn't match what the file holds."""
    global FONT_FAMILY
    if font_file:
        path = USER_FONTS_DIR / font_file
        if str(path) not in _loaded_font_files:
            fid = QtGui.QFontDatabase.addApplicationFont(str(path))
            fams = QtGui.QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
            _loaded_font_files[str(path)] = fams[0] if fams else ""
            if not fams:
                log_hud.warning("could not load font file %s", path)
        loaded = _loaded_font_files[str(path)]
        if loaded and family != loaded:
            family = loaded
    FONT_FAMILY = family


def _font(px, weight):
    font = QtGui.QFont(FONT_FAMILY) if FONT_FAMILY else QtGui.QFont()
    font.setPixelSize(max(7, int(round(px))))
    font.setWeight(weight)
    return font


def text_width(px, weight, text):
    return QtGui.QFontMetricsF(_font(px, weight)).horizontalAdvance(text)


def draw_text(p, x, y, text, px, weight, color, align="left", outline=0.0, alpha=1.0, thicken_share=1.0):
    """Draws text with its left / right / center at x and its baseline at y,
    optionally with a dark outline (the "text" style, like the score digits).
    thicken_share: how much of the text weight's thickening it gets.
    Returns the text's width."""
    font = _font(px, weight)
    w = QtGui.QFontMetricsF(font).horizontalAdvance(text)
    if align == "right":
        x -= w
    elif align == "center":
        x -= w / 2
    path = QtGui.QPainterPath()
    path.addText(QtCore.QPointF(x, y), font, text)
    thicken = THICKEN * thicken_share * px
    outline = max(outline, TEXT_OUTLINE * px)
    if outline > 0:
        oc = QtGui.QColor(*(TEXT_OUTLINE_RGB if TEXT_OUTLINE else OUTLINE_RGB))
        oc.setAlphaF(alpha)
        pen = QtGui.QPen(oc, outline * 2 + thicken)  # still shows around the thickened glyphs
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        p.strokePath(path, pen)
    if thicken > 0 and alpha < 1.0:
        _draw_thick_faded(p, path, color, alpha, thicken)
    else:
        c = QtGui.QColor(*color)
        c.setAlphaF(alpha)
        p.fillPath(path, c)
        if thicken > 0:
            pen = QtGui.QPen(c, thicken)
            pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
            p.strokePath(path, pen)
    return w


def _draw_thick_faded(p, path, color, alpha, thicken):
    """Fill + same-color stroke for see-through text: drawn opaque on a small
    layer first, then the layer at `alpha`, so the stroke doesn't double the
    alpha where it overlaps the fill. (Merging the two into one path instead
    took up to ~43ms per string — too slow at 10 repaints a second.)"""
    rect = path.boundingRect().adjusted(-thicken, -thicken, thicken, thicken).toAlignedRect()
    if rect.isEmpty():
        return
    dpr = p.device().devicePixelRatioF() if p.device() else 1.0
    img = QtGui.QImage(int(rect.width() * dpr) + 1, int(rect.height() * dpr) + 1,
                       QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(dpr)
    img.fill(QtCore.Qt.GlobalColor.transparent)
    q = QtGui.QPainter(img)
    q.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    q.translate(-rect.left(), -rect.top())
    c = QtGui.QColor(*color)
    q.fillPath(path, c)
    pen = QtGui.QPen(c, thicken)
    pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
    q.strokePath(path, pen)
    q.end()
    p.save()
    p.setOpacity(p.opacity() * alpha)
    p.drawImage(QtCore.QPointF(rect.left(), rect.top()), img)
    p.restore()


# --- the designs added on 2026-10-30 (the user picked them from 22 samples) ---
#   frame    dark box with a border in the player color ("neon" at first; the
#            user dropped the glow and asked for a new name: カラー枠)
#   slash    each row a slanted box, stepped like stairs, player-color edge
#   hex      each number in its own hexagon, a honeycomb two wide that grows downward
#   meter    the first number as a speedometer arc, the rest under it
#   tower    a vertical bar per number, value on top
#   minimal  no box, just a line under each number; the line is this design's
#            background: the background strength, its own color (display.line_color)
#   trend    each number with a small line chart of its last minute
# Same looks in obs/overlay.html.
NEW_STYLES = ("frame", "slash", "hex", "meter", "tower", "minimal", "trend")
# the box the other parts (clock, events, summary, opener) get in each of them
FRAMES = {"frame": "frame", "slash": "slash", "hex": "square",
          "tower": "square", "meter": "rounded", "trend": "rounded", "minimal": "none"}
# Stat blocks in these designs keep this much room (reference px) from the
# board: their text / box went right up to the board's edge, further toward it
# than the band style's text (user report: "everything shifted right").
NEW_STYLE_GAP = 6


def minimal_line(a, opacity):
    """The minimal design's line: it is that design's background, so it takes
    the background strength, in its own color (display.line_color, white to start)."""
    return QtGui.QColor(*LINE_RGB, int(255 * opacity * a))
TREND_SAMPLES = 60   # trend: one value a second, the last minute


def frame_of(style):
    return FRAMES.get(style)


def hex_cells(n):
    """hex: (column, row) of each of n hexagons, in hexagon units: at most two
    side by side (user's request), the right one half a hexagon lower, and more
    rows below — a honeycomb that grows downward. Read left, right, next row."""
    return [(i % 2, i // 2 + (0.5 if i % 2 else 0)) for i in range(n)]


def slant_dx(r, u):
    return min(r.height() * 0.3, 10 * u)


def slant(r, u, dx=None):
    """A parallelogram leaning right inside r (the "slash" design)."""
    dx = slant_dx(r, u) if dx is None else dx
    return QtGui.QPolygonF([QtCore.QPointF(r.left() + dx, r.top()), QtCore.QPointF(r.right(), r.top()),
                            QtCore.QPointF(r.right() - dx, r.bottom()), QtCore.QPointF(r.left(), r.bottom())])


def paint_frame(p, r, kind, u, a, opacity, accent=None):
    """The box behind a part in the later designs (FRAMES). r: QRectF."""
    if kind in (None, "none"):
        return
    p.save()
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    fill = QtGui.QColor(*BAND_RGB)
    if kind == "square":
        fill.setAlphaF(opacity * a)
        p.fillRect(r, fill)
    elif kind == "rounded":
        fill.setAlphaF(opacity * a)
        p.setBrush(fill)
        p.drawRoundedRect(r, 6 * u, 6 * u)
    elif kind == "frame":   # the player's color (the text color for the shared parts)
        c = accent or WHITE
        inner = r.adjusted(1 * u, 1 * u, -1 * u, -1 * u)
        radius = min(5 * u, inner.height() / 2)
        fill.setAlphaF(opacity * a)
        p.setBrush(fill)
        p.setPen(QtGui.QPen(QtGui.QColor(*c, int(255 * a)), 2 * u))
        p.drawRoundedRect(inner, radius, radius)
    elif kind == "slash":
        fill.setAlphaF(opacity * a)
        p.setBrush(fill)
        p.drawPolygon(slant(r, u))
        if accent:   # a player-color edge on the slanted left side
            dx = slant_dx(r, u)
            p.setBrush(QtGui.QColor(*accent, int(255 * a)))
            p.drawPolygon(slant(QtCore.QRectF(r.left(), r.top(), dx + 4 * u, r.height()), u, dx))
    p.restore()


# Widest value each stat is given room for, digits filled in with the font's
# widest digit — so the label beside a value stays put as the number changes
# (user report: APM etc. shifted left and right with every update).
VALUE_TEMPLATES = {"apm": "{0}{0}{0}.{0}", "pps": "{0}.{0}{0}", "app": "{0}.{0}{0}",
                   "attack": "{0}{0}{0}", "pieces": "{0}{0}{0}{0}", "ren": "{0}{0}", "b2b": "x{0}{0}"}
# The stats' labels; display.labels can reword any of them (set_labels).
DEFAULT_LABELS = {"apm": "APM", "pps": "PPS", "app": "APP", "attack": "ATK",
                  "pieces": "PIECES", "ren": "REN", "b2b": "B2B"}
DEFAULT_LABELS_EN = {**DEFAULT_LABELS, "ren": "COMBO"}   # the English game says "Combo" for REN
LABELS = dict(DEFAULT_LABELS)


def default_labels(language):
    return DEFAULT_LABELS_EN if language == "en" else DEFAULT_LABELS


def set_labels(own, language="ja"):
    global LABELS
    LABELS = {**default_labels(language), **(own or {})}


def label_for(key):
    return LABELS.get(key, key.upper())


def set_player_colors(left_hex, right_hex):
    """display.player_color_left / right; the lighter text tints follow."""
    global PLAYER_COLORS, PLAYER_TEXT_COLORS
    PLAYER_COLORS = {"left": hex_rgb(left_hex), "right": hex_rgb(right_hex)}
    PLAYER_TEXT_COLORS = {sd: mix(c, (255, 255, 255), 0.45) for sd, c in PLAYER_COLORS.items()}


def use_colors(widget):
    """Each part can have its own colors (display.parts): a widget sets them
    right before it paints, since the color names below are module-wide."""
    if getattr(widget, "colors", None):
        set_colors(*widget.colors)


def value_slot_width(key, px, weight):
    d = max("0123456789", key=lambda c: text_width(px, weight, c))
    return text_width(px, weight, VALUE_TEMPLATES[key].format(d))


def fmt_value(key, value):
    if value is None:
        return "--"
    if key == "b2b":
        return f"x{value}" if value else "--"   # no chain going
    if key in ("attack", "pieces", "ren"):
        return str(int(value))
    return f"{value:.1f}" if key == "apm" else f"{value:.2f}"   # pps / app: 2 decimals


def is_puyo(side):
    """This side's display is hidden: the server saw it playing Puyo Puyo, or
    display.players shows only the other player (see mark_hidden_sides)."""
    side = side or {}
    return bool(side.get("puyo") or side.get("hidden"))


def puyo_in_match(state):
    """Someone in this match plays Puyo Puyo (really Puyo, not just a side
    hidden by display.players)."""
    return any((state.get(sd) or {}).get("puyo") for sd in ("left", "right"))


def mark_hidden_sides(state, players):
    """display.players = "left" / "right": the other side counts as hidden
    (no stats, events, opener; empty summary column), like a Puyo side."""
    if players not in ("left", "right"):
        return state
    other = "right" if players == "left" else "left"
    return {**state, other: {**(state.get(other) or {}), "hidden": True}}


def side_values(side):
    side = side or {}
    return {"apm": (side.get("apm") or {}).get("apm"), "pps": side.get("pps"), "app": side.get("app"),
            "attack": side.get("attack"), "pieces": side.get("pieces"),
            "ren": side.get("ren"), "b2b": side.get("b2b")}


WHITE = (255, 255, 255)   # the main text color (display.text_color; see set_colors)
SOFT = (220, 228, 245)    # labels: the text color a little toward the background
# Opener name: shown for POPUP_S seconds when the opener is recognized,
# fading in over POPUP_IN_S and out over the last POPUP_FADE_S — in every
# opener_display position (user's request; "hold" / "namebar" / "top" used to
# stay all match). Same numbers in obs/overlay.html.
POPUP_S = 4.0
POPUP_IN_S = 0.25
POPUP_FADE_S = 1.2


def _smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)   # eases in and out, so the fade has no hard start/stop


def popup_alpha(side_state, frozen, since_state_s=0.0, seconds=POPUP_S):
    """Opacity of one player's opener name right now (0 = not shown).
    since_state_s: time since side_state arrived, added to its age.
    seconds: how long it stays up (display.opener_seconds); 0 = until the match ends."""
    age = (side_state or {}).get("opener_age_s")
    if age is None or frozen:
        return 0.0
    age += since_state_s
    if seconds <= 0:
        return _smooth(age / POPUP_IN_S)
    if age >= seconds:
        return 0.0
    fade = min(POPUP_FADE_S, seconds / 2)
    return min(_smooth(age / POPUP_IN_S), _smooth((seconds - age) / fade))
# Where each opener display sits (reference px).
BOARD_CENTER_X = {"left": 313, "right": 918}     # "board": centered on the board...
OPENER_BOARD_TOP_Y = 150                          # ...in its upper part (empty during the opening)
HOLD_RIGHT_X = {"left": 191, "right": 797}       # "hold": right edge of each HOLD box...
OPENER_HOLD_TOP_Y = 172                           # ...just below it
NAMEBAR_RIGHT_X, NAMEBAR_LEFT_X = 466, 762        # "namebar": end of the bar away from the avatar
NAMEBAR_TOP_Y = 608                                # in the gap between the score digits and the name bar
OPENER_TOP_CENTER_X, OPENER_TOP_Y = 615.6, 14       # "top": both players, top center


def elide(text, px, weight, width):
    """Shortens text with … to fit width (opener names can be long)."""
    fm = QtGui.QFontMetricsF(_font(px, weight))
    return fm.elidedText(text, QtCore.Qt.TextElideMode.ElideRight, width)


def wrap_lines(text, px, weight, width, max_lines):
    """Text broken into lines that fit width, at most max_lines (the last
    one cut with …). Breaks after a space or before a bracket when one is
    near, else anywhere (Japanese names have no spaces). Same as the OBS
    page's wrapLines."""
    lines, rest = [], text
    while rest and len(lines) < max_lines - 1 and text_width(px, weight, rest) > width:
        n = 1
        while n < len(rest) and text_width(px, weight, rest[:n + 1]) <= width:
            n += 1
        cut = max([i + 1 for i in range(n) if rest[i] == " "] +
                  [i for i in range(1, n + 1) if i < len(rest) and rest[i] in "(（[「"] + [0])
        if cut > n // 2:   # a nice break, not too early
            n = cut
        lines.append(rest[:n].rstrip())
        rest = rest[n:].lstrip()
    if rest:
        lines.append(elide(rest, px, weight, width))
    return lines


class StatBlock(Band):
    """APM / PPS for one player, drawn in the chosen style ("band", "pop",
    "gauge", "text"). The content hugs the board side of the block (mode =
    stats_position); sizes are reference px x u."""

    KEYS = ("apm", "pps", "app", "attack", "pieces", "ren", "b2b")   # config_store.STAT_ITEMS
    WIDTH = {"band": 92, "pop": 104, "gauge": 104, "text": 104, "simple": 92}
    # gauge: the label + value sit in the GAUGE_TEXT_W nearest the board, so
    # the label starts about where the band style's text does (80 in from the
    # board side; user's requests), while the bar keeps the full width.
    GAUGE_TEXT_W = 86
    ROW_H = {"band": 21, "pop": 26, "gauge": 27, "text": 23, "simple": 21}
    PAD = {"band": 3, "pop": 1, "gauge": 3, "text": 1, "simple": 3}

    def __init__(self, parent, side):
        super().__init__(parent, draggable=True)
        self.side = side
        self.style = "band"
        self.mode = "left"
        self.shown = ["apm", "pps", "app"]
        self.u = 1.0
        self.values = side_values(None)
        self.reset_history()

    def reset_history(self):
        """trend: each number's values, one a second (TREND_SAMPLES)."""
        self.history = {k: deque(maxlen=TREND_SAMPLES) for k in self.KEYS}
        self._history_t = None

    def configure(self, style, mode, shown, u):
        self.style, self.mode, self.shown, self.u = style, mode, list(shown), u
        self.fade = None if style in ("simple",) + NEW_STYLES else mode
        self.square = style == "simple"
        n = max(1, len(self.shown))
        if style in NEW_STYLES:
            w, h = self._new_size(u)
            self.setFixedSize(int(w) + 1, int(h) + 1)
        else:
            self.setFixedSize(int(max(self.WIDTH[style] * u, self._needed_width(u))),
                              int((self.ROW_H[style] * n + self.PAD[style] * 2) * u))
        self.update()

    # --- the later designs (NEW_STYLES); sizes in reference px x u ---
    TABLE = {   # row height, padding x, padding y, label px, value px
        "frame": (21, 9, 4, 12, 17),
        "minimal": (22, 3, 2, 12, 17), "trend": (20, 6, 4, 11, 14), "slash": (22, 9, 2, 11, 15),
    }
    GAP = 6          # between a label and its value
    # trend: the little chart, and the gaps either side of it (kept small: the
    # block was much wider than the others; user's request)
    SPARK_W, SPARK_GAP = 32, 4
    STEP = 6         # slash: how far each row steps over
    HEX_W = 54
    METER_W, METER_H = 70, 48
    # tower: kept compact (user's request): short thin bars, columns close together
    TOWER_BAR_H, TOWER_COL_W, TOWER_GAP, TOWER_PAD = 58, 22, 2, 4

    def _table_cols(self, u, lab_px, val_px, keys=None):
        keys = keys or self.shown or ["apm"]
        lab_w = max(text_width(lab_px * u, BOLD, label_for(k)) for k in keys)
        slot_w = max(max(value_slot_width(k, val_px * u, SEMI),
                         text_width(val_px * u, SEMI, fmt_value(k, self.values.get(k)))) for k in keys)
        return lab_w, slot_w

    def _hex_w(self, u):
        keys = self.shown or ["apm"]
        need = max(max(value_slot_width(k, 14 * u, SEMI) for k in keys) + 14 * u,
                   max(text_width(9 * u, BOLD, label_for(k)) for k in keys) + 18 * u)
        return max(self.HEX_W * u, need)

    def _tower_col_w(self, u):
        keys = self.shown or ["apm"]
        return max(self.TOWER_COL_W * u, max(value_slot_width(k, 11 * u, SEMI) for k in keys) + 2 * u,
                   max(text_width(8 * u, BOLD, label_for(k)) for k in keys) + 2 * u)

    def _new_size(self, u):
        st, n = self.style, max(1, len(self.shown))
        if st in self.TABLE:
            row_h, pad_x, pad_y, lab_px, val_px = self.TABLE[st]
            lab_w, slot_w = self._table_cols(u, lab_px, val_px)
            w = lab_w + self.GAP * u + slot_w + 2 * pad_x * u
            if st == "trend":
                w += (self.SPARK_W + 2 * self.SPARK_GAP - self.GAP) * u
            if st == "slash":
                w += 10 * u + (n - 1) * self.STEP * u   # the slant, and the steps
            return w, n * row_h * u + 2 * pad_y * u
        if st == "hex":
            hw = self._hex_w(u)
            cells = hex_cells(n)
            return (max(c for c, _ in cells) * 0.78 + 1) * hw + 2 * u, \
                (max(r for _, r in cells) + 1) * hw * 0.88 + 2 * u
        if st == "meter":
            # the other numbers go under the meter, not beside it: about as
            # narrow as the band style (it was much wider; user's request)
            rest = self.shown[1:]
            w = self.METER_W * u
            if rest:
                lab_w, slot_w = self._table_cols(u, 10, 13, rest)
                w = max(w, lab_w + 6 * u + slot_w)
            return w + 12 * u, (self.METER_H + len(rest) * 16 + (4 if rest else 0) + 10) * u
        if st == "tower":
            cw = self._tower_col_w(u)
            return n * cw + (n - 1) * self.TOWER_GAP * u + 2 * self.TOWER_PAD * u, (14 + self.TOWER_BAR_H + 12 + 6) * u
        return 92 * u, 21 * n * u

    def _needed_width(self, u):
        """Width the shown rows need at their widest values: reworded labels
        (display.labels, e.g. Japanese) and added rows used to run past the
        fixed width and get cut off."""
        st, keys = self.style, self.shown or ["apm"]

        def cols(lab_px, val_px, val_weight):
            return (max(text_width(lab_px, BOLD, label_for(k)) for k in keys),
                    max(value_slot_width(k, val_px, val_weight) for k in keys))
        if st in ("band", "text", "simple"):
            lab_w, slot_w = cols(12 * u, (20 if st == "text" else 17) * u, SEMI)
            return lab_w + slot_w + 14 * u
        if st == "pop":
            lab_w, slot_w = cols(11 * u, 16 * u, BOLD)
            return lab_w + slot_w + 31 * u
        if st == "gauge":
            lab_w, slot_w = cols(11 * u, 15 * u, SEMI)
            return lab_w + slot_w + 18 * u + (self.WIDTH["gauge"] - self.GAUGE_TEXT_W) * u
        return 0

    def update_side(self, side, elapsed=None):
        """elapsed: the match clock, for trend's one-a-second history (it
        starts over when the clock goes back, i.e. a new match)."""
        self.values = side_values(side)
        if elapsed is not None:
            if self._history_t is not None and elapsed < self._history_t - 0.5:
                self.reset_history()
            if self._history_t is None or elapsed >= self._history_t + 1.0:
                self._history_t = elapsed
                for k in self.KEYS:
                    if self.values.get(k) is not None:
                        self.history[k].append(float(self.values[k]))
        self.update()

    def _columns(self, lab_px, lab_weight, val_px, val_weight):
        """(label width, value width) shared by every shown row, so APM / PPS /
        APP line up as columns (user's request) instead of each row sizing to
        its own label and value."""
        lab_w = max(text_width(lab_px, lab_weight, label_for(k)) for k in self.shown)
        slot_w = max(max(value_slot_width(k, val_px, val_weight),
                         text_width(val_px, val_weight, fmt_value(k, self.values[k])))
                     for k in self.shown)
        return lab_w, slot_w

    def paintEvent(self, event):
        use_colors(self)
        if self.style in NEW_STYLES:
            self._paint_new()
            return
        # band / gauge draw the dark band behind; any style shows the edit outline
        if self.editing or self.style in ("band", "gauge", "simple"):
            super().paintEvent(event)
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        u, W, st = self.u, self.width(), self.style
        a = 0.45 if self.dim else 1.0
        hug_right = self.mode == "left"   # placed left of the board: hug the right edge
        for i, key in enumerate(self.shown):
            top = (self.PAD[st] + i * self.ROW_H[st]) * u
            label, value = label_for(key), fmt_value(key, self.values[key])
            if st in ("band", "text", "simple"):
                big = 20 if st == "text" else 17
                outline = 1.6 * u if st == "text" else 0
                base = top + (18 if st == "text" else 16) * u
                lab_w, slot_w = self._columns(12 * u, BOLD, big * u, SEMI)
                # a table: labels start in one column, values end in one column
                lab_x = W - 5 * u - slot_w - 4 * u - lab_w if hug_right else 5 * u
                draw_text(p, lab_x, base, label, 12 * u, BOLD, WHITE, "left", outline, a)
                draw_text(p, lab_x + lab_w + 4 * u + slot_w, base, value, big * u, SEMI, WHITE, "right", outline, a)
            elif st == "pop":
                h = 22 * u
                lab_w, slot_w = self._columns(11 * u, BOLD, 16 * u, BOLD)
                pw = lab_w + slot_w + 27 * u  # same for every row: the pills line up and don't resize
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
                draw_text(p, x0 + pw - 11 * u, base, value, 16 * u, BOLD, WHITE, "right", alpha=a)
            else:  # gauge
                base = top + 14 * u
                x_l, x_r = 6 * u, W - 6 * u
                inset = (self.WIDTH["gauge"] - self.GAUGE_TEXT_W) * u
                text_l = x_l + inset if hug_right else x_l
                text_r = x_r if hug_right else x_r - inset
                draw_text(p, text_l, base, label, 11 * u, BOLD, SOFT, alpha=a)
                draw_text(p, text_r, base, value, 15 * u, SEMI, WHITE, "right", alpha=a)
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


    def _paint_new(self):
        st, u, W, H = self.style, self.u, self.width(), self.height()
        p = QtGui.QPainter(self)
        if self.editing:
            p.end()
            Band.paintEvent(self, None)
            p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        a = 0.45 if self.dim else 1.0
        hug_right = self.mode == "left"
        accent, tint = PLAYER_COLORS[self.side], PLAYER_TEXT_COLORS[self.side]
        r = QtCore.QRectF(0, 0, W, H)
        if st in ("frame", "trend") and not self.editing:
            paint_frame(p, r, frame_of(st), u, a, self.opacity, accent if st == "frame" else None)
        if st in ("hex", "meter", "tower"):
            if not self.editing and st in ("meter", "tower"):
                paint_frame(p, r, frame_of(st), u, a, self.opacity)
            getattr(self, "_paint_" + st)(p, u, W, H, a, accent, tint, hug_right)
            return
        row_h, pad_x, pad_y, lab_px, val_px = self.TABLE[st]
        lab_w, slot_w = self._table_cols(u, lab_px, val_px)
        extra = (self.SPARK_W + 2 * self.SPARK_GAP - self.GAP) * u if st == "trend" else 0
        table_w = lab_w + self.GAP * u + extra + slot_w
        outline = 1.6 * u if st == "minimal" else 0
        lab_color = {"frame": tint, "slash": tint, "trend": SOFT}.get(st, WHITE)
        n = len(self.shown)
        for i, key in enumerate(self.shown):
            top = (pad_y + i * row_h) * u
            if st == "slash":
                # one slanted box per row, stepping toward the board going down
                step = (n - 1 - i) * self.STEP * u
                box_w = table_w + 2 * pad_x * u + 10 * u
                x0 = W - step - box_w if hug_right else step
                row = QtCore.QRectF(x0, top + 1 * u, box_w, (row_h - 2) * u)
                if not self.editing:
                    paint_frame(p, row, "slash", u, a, self.opacity, accent)   # follows 背景の濃さ fully
                lab_x = x0 + pad_x * u + 6 * u
            else:
                lab_x = W - pad_x * u - table_w if hug_right else pad_x * u
            base = top + (row_h * 0.5 + val_px * 0.36) * u
            label, value = label_for(key), fmt_value(key, self.values.get(key))
            draw_text(p, lab_x, base, label, lab_px * u, BOLD, lab_color, "left", outline, a)
            draw_text(p, lab_x + table_w, base, value, val_px * u, SEMI, WHITE, "right", outline, a)
            if st == "minimal":   # the thin line under each number
                p.fillRect(QtCore.QRectF(lab_x, top + (row_h - 2.5) * u, table_w, 1.5 * u),
                           minimal_line(a, self.opacity))
            if st == "trend":
                self._sparkline(p, QtCore.QRectF(lab_x + lab_w + self.SPARK_GAP * u, top + 4 * u,
                                                 self.SPARK_W * u, (row_h - 8) * u), key, accent, a)

    def _sparkline(self, p, r, key, color, a):
        values = list(self.history.get(key, ()))
        p.save()
        if len(values) < 2:   # nothing to draw yet: a faint baseline
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, int(50 * a)), 1.2 * self.u))
            p.drawLine(QtCore.QPointF(r.left(), r.center().y()), QtCore.QPointF(r.right(), r.center().y()))
            p.restore()
            return
        lo, hi = min(values), max(values)
        span = hi - lo
        path = QtGui.QPainterPath()
        for i, v in enumerate(values):
            x = r.left() + r.width() * i / (len(values) - 1)
            y = r.center().y() if span < 1e-9 else r.bottom() - r.height() * (v - lo) / span
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        pen = QtGui.QPen(QtGui.QColor(*color, int(255 * a)), 1.8 * self.u)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawPath(path)
        p.restore()

    def _paint_hex(self, p, u, W, H, a, accent, tint, hug_right):
        hw = self._hex_w(u)
        hh = hw * 0.88
        for key, (col, row) in zip(self.shown, hex_cells(len(self.shown))):
            x, y = 1 * u + col * hw * 0.78, 1 * u + row * hh
            pts = [(0.25, 0.0), (0.75, 0.0), (1.0, 0.5), (0.75, 1.0), (0.25, 1.0), (0.0, 0.5)]
            poly = QtGui.QPolygonF([QtCore.QPointF(x + hw * px, y + hh * py) for px, py in pts])
            if not self.editing:
                fill = QtGui.QColor(*BAND_RGB)
                fill.setAlphaF(self.opacity * a)   # follows 背景の濃さ fully (user report: it barely changed)
                p.setBrush(fill)
                p.setPen(QtGui.QPen(QtGui.QColor(*accent, int(255 * a)), 1.6 * u))
                p.drawPolygon(poly)
            cx = x + hw / 2
            label = elide(label_for(key), 9 * u, BOLD, hw * 0.72)
            draw_text(p, cx, y + hh * 0.42, label, 9 * u, BOLD, tint, "center", 0, a)
            draw_text(p, cx, y + hh * 0.42 + 16 * u, fmt_value(key, self.values.get(key)), 14 * u, SEMI,
                      WHITE, "center", 0, a)

    def _paint_meter(self, p, u, W, H, a, accent, tint, hug_right):
        first, rest = self.shown[0], self.shown[1:]
        # the meter on top, centered; the other numbers under it
        mx = (W - self.METER_W * u) / 2
        box = QtCore.QRectF(mx, 5 * u, self.METER_W * u, self.METER_H * u)
        d = min(box.width() - 8 * u, (box.height() - 4 * u) * 2)
        arc = QtCore.QRectF(box.center().x() - d / 2, box.top() + 4 * u, d, d)
        v = self.values.get(first)
        frac = 0.0 if v is None else max(0.0, min(1.0, v / GAUGE_MAX[first]))
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255, int(55 * a)), 6.5 * u)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(arc, 180 * 16, -180 * 16)
        if frac > 0:
            pen.setColor(QtGui.QColor(*accent, int(255 * a)))
            p.setPen(pen)
            p.drawArc(arc, 180 * 16, int(-180 * 16 * frac))
        cx = box.center().x()
        draw_text(p, cx, arc.center().y() - 2 * u, fmt_value(first, v), 16 * u, SEMI, WHITE, "center", 0, a)
        draw_text(p, cx, arc.center().y() + 9 * u, elide(label_for(first), 8 * u, BOLD, d * 0.8), 8 * u, BOLD,
                  tint, "center", 0, a)
        if rest:
            y0 = box.bottom() + 4 * u
            for i, key in enumerate(rest):
                base = y0 + (i * 16 + 12) * u
                draw_text(p, 6 * u, base, label_for(key), 10 * u, BOLD, tint, "left", 0, a)
                draw_text(p, W - 6 * u, base, fmt_value(key, self.values.get(key)), 13 * u,
                          SEMI, WHITE, "right", 0, a)

    def _paint_tower(self, p, u, W, H, a, accent, tint, hug_right):
        cw = self._tower_col_w(u)
        n = len(self.shown)
        bar_top, bar_h = 17 * u, self.TOWER_BAR_H * u
        step, pad = cw + self.TOWER_GAP * u, self.TOWER_PAD * u
        for i, key in enumerate(self.shown):
            col = (n - 1 - i) if hug_right else i
            x = W - pad - cw - col * step if hug_right else pad + col * step
            cx = x + cw / 2
            v = self.values.get(key)
            draw_text(p, cx, 13 * u, fmt_value(key, v), 11 * u, SEMI, WHITE, "center", 0, a)
            bar = QtCore.QRectF(cx - 5 * u, bar_top, 10 * u, bar_h)
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QColor(255, 255, 255, int(45 * a)))
            p.drawRoundedRect(bar, 3 * u, 3 * u)
            frac = 0.0 if v is None else max(0.0, min(1.0, v / GAUGE_MAX[key]))
            if frac > 0:
                fill = QtCore.QRectF(bar.left(), bar.bottom() - bar_h * frac, bar.width(), bar_h * frac)
                g = QtGui.QLinearGradient(0, bar.top(), 0, bar.bottom())
                g.setColorAt(0.0, QtGui.QColor(*mix(accent, (255, 255, 255), 0.45), int(255 * a)))
                g.setColorAt(1.0, QtGui.QColor(*accent, int(255 * a)))
                p.setBrush(QtGui.QBrush(g))
                p.drawRoundedRect(fill, 3 * u, 3 * u)
            draw_text(p, cx, bar.bottom() + 10 * u, elide(label_for(key), 8 * u, BOLD, cw + 2 * u), 8 * u, BOLD,
                      tint, "center", 0, a)


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
        self.puyo = {"left": False, "right": False}

    def configure(self, shown, u):
        self.shown, self.u = list(shown), u
        self.setFixedSize(int(self.WIDTH * u), int((self.ROW_H * max(1, len(shown)) + 6) * u))
        self.update()

    def update_sides(self, left, right):
        self.values = {"left": side_values(left), "right": side_values(right)}
        self.puyo = {"left": is_puyo(left), "right": is_puyo(right)}   # a Puyo side's numbers are left out
        self.update()

    def paintEvent(self, event):
        use_colors(self)
        super().paintEvent(event)
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        u, W = self.u, self.width()
        a = 0.45 if self.dim else 1.0
        for i, key in enumerate(self.shown):
            top = (3 + i * self.ROW_H) * u
            lv, rv = self.values["left"][key], self.values["right"][key]
            draw_text(p, W / 2, top + 11 * u, label_for(key), 10 * u, BOLD, SOFT, "center", alpha=a)
            if not self.puyo["left"]:
                draw_text(p, 7 * u, top + 15 * u, fmt_value(key, lv), 15 * u, BOLD, PLAYER_TEXT_COLORS["left"], alpha=a)
            if not self.puyo["right"]:
                draw_text(p, W - 7 * u, top + 15 * u, fmt_value(key, rv), 15 * u, BOLD,
                          PLAYER_TEXT_COLORS["right"], "right", alpha=a)
            bar = QtCore.QRectF(7 * u, top + 20 * u, W - 14 * u, 6 * u)
            total = (lv or 0) + (rv or 0)
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            if total <= 0 or any(self.puyo.values()):  # nothing yet / nothing to compare: an even, neutral bar
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

    MAX = 10   # = the most display.event_log_count allows
    LINE_H = {"band": 14, "gauge": 14, "versus": 14, "text": 15, "pop": 19, "simple": 14}

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
        self.opener_language = "ja"   # display.opener_language, resolved

    def configure(self, style, mode, count, u):
        self.style, self.mode, self.count, self.u = style, mode, count, u
        self.fade = None if style == "simple" else mode
        self.square = style == "simple"
        self._resize()

    def _text(self, e, key):
        if e.get("ren_source") == "opener" and e.get("opener"):   # the name in display.opener_language
            name = (self.opener_language == "en" and e.get("opener_en")) or e["opener"]
            return ("Opener: " if self.language == "en" else "開幕：") + name
        return e.get(key) or e.get("text", "")

    def update_side(self, side):
        """Shows up to `count` events, oldest on top; True if there are any."""
        log = (side or {}).get("event_log") or []   # newest first
        key = "text_en" if self.language == "en" else "text"
        texts = [self._text(e, key) for e in log[:self.count]][::-1]
        if texts != self.texts:
            self.texts = texts
            self._resize()
            self.update()
        return bool(texts)

    def _px(self):
        return 10 * self.u

    # the later designs' boxes: (extra width, extra height) for their borders / slant
    NEW_PAD = {"frame": (4, 2), "slash": (14, 2), "minimal": (-7, 0)}

    def _resize(self):
        u = self.u
        widest = max((text_width(self._px(), SEMI, t) for t in self.texts), default=0)
        extra = {"pop": 18, "text": 10}.get(self.style, 17)
        add_w, add_h = self.NEW_PAD.get(self.style, (0, 0))
        n = max(1, len(self.texts))
        self.setFixedSize(int(widest + (extra + add_w) * u) + 2,
                          int((self.LINE_H.get(self.style, 14) * n + 4 + add_h) * u))

    def paintEvent(self, event):
        use_colors(self)
        st = self.style
        if self.editing or st in ("band", "gauge", "versus", "simple"):
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
        r = QtCore.QRectF(self.rect())
        if frame_of(st) and not self.editing:
            paint_frame(p, r, frame_of(st), u, a, self.opacity,
                        PLAYER_COLORS[self.side] if st in ("frame", "slash") else None)
        # how far the text sits in from the box's edges in the later designs
        x_pad = (8 if st == "frame" else 6) * u
        if st == "slash":
            x_pad = 9 * u + slant_dx(r, u)
        y_off = self.NEW_PAD.get(st, (0, 0))[1] / 2 * u
        for i, text in enumerate(self.texts):
            top = (2 + i * self.LINE_H.get(st, 14)) * u + y_off
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
            outline = 1.0 * u if st in ("text", "minimal") else 0
            color = WHITE if st in ("text", "minimal") else EVENT_RGB
            if hug_right:
                draw_text(p, W - x_pad, base, text, self._px(), SEMI, color, "right", outline, a)
            else:
                draw_text(p, x_pad, base, text, self._px(), SEMI, color, "left", outline, a)


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
        self.hide_time = False   # a Puyo player in the match: no time (see puyo_in_match)

    def configure(self, style, u):
        self.style, self.u = style, u
        self._resize()

    def set_texts(self, clock, state, status):
        if (clock, state, status) != (self.clock_text, self.state_text, self.status_text):
            self.clock_text, self.state_text, self.status_text = clock, state, status
            self._resize()
            self.update()

    def set_hide_time(self, hide):
        if hide != self.hide_time:
            self.hide_time = hide
            self._resize()
            self.update()

    def _lines(self):
        lines = [] if self.hide_time else [(self.clock_text, 18, BOLD, WHITE, 20)]
        if self.state_text:
            lines.append((self.state_text, 10, SEMI, STATE_RGB, 13))
        if self.status_text:
            lines.append((self.status_text, 10, SEMI, STATUS_RGB, 13))
        return lines

    def _pad(self):
        # band / gauge / simple: a little wider than the text needs (user's request)
        return {"pop": (13, 4), "text": (4, 1), "versus": (8, 2), "minimal": (4, 1), "frame": (14, 3),
                "slash": (20, 2)}.get(self.style, (14, 2))

    def _resize(self):
        u = self.u
        lines = self._lines()
        widest = max((text_width(px * u, w, t) for t, px, w, _, _ in lines), default=0)
        px_pad, py_pad = self._pad()
        h = sum(lh for *_, lh in lines) + py_pad * 2 + (3 if self.style == "gauge" else 0)
        self.setFixedSize(int(widest + px_pad * 2 * u) + 2, int(h * u))

    def paintEvent(self, event):
        use_colors(self)
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
        elif st == "versus":
            p.setBrush(band)
            p.drawRoundedRect(r, 4 * u, 4 * u)
        elif st in ("band", "gauge", "simple"):   # a plain square box (user's choice)
            p.fillRect(r, band)
            if st == "gauge":   # blue | red line along the bottom
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
        elif frame_of(st):
            paint_frame(p, r, frame_of(st), u, a, self.opacity)
        outline = 1.6 * u if st in ("text", "minimal") else 0
        y = self._pad()[1] * u
        for text, px, weight, color, lh in self._lines():
            y += lh * u
            draw_text(p, r.width() / 2, y - (4 if lh == 20 else 3) * u, text, px * u, weight,
                      color, "center", outline, a)


class SessionBlock(ClockBlock):
    """今日の成績 (scripts/session_stats.py): the server's lines in a box
    drawn like the match time's, in the chosen style."""
    SIZES = {"title": (9, SEMI, 12), "main": (15, BOLD, 18), "sub": (10, SEMI, 13)}
    SAMPLE = {"ja": [["今日の成績", "title"], ["12勝 8敗  60%", "main"], ["3連勝中", "sub"],
                     ["レート +35（2633）", "sub"], ["APM 54.0  PPS 1.83  APP 0.55", "sub"]],
              "en": [["Today", "title"], ["12W 8L  60%", "main"], ["3 wins in a row", "sub"],
                     ["Rating +35 (2633)", "sub"], ["APM 54.0  PPS 1.83  APP 0.55", "sub"]]}

    def __init__(self, parent):
        super().__init__(parent)
        self.drag_target = "session"
        self.rows = []

    def set_rows(self, rows):
        rows = [list(r) for r in rows or [] if isinstance(r, (list, tuple)) and len(r) == 2]
        if rows != self.rows:
            self.rows = rows
            self._resize()
            self.update()

    def _lines(self):
        out = []
        for text, kind in self.rows:
            px, weight, lh = self.SIZES.get(kind, self.SIZES["sub"])
            out.append((str(text), px, weight, STATE_RGB if kind == "title" else WHITE, lh))
        return out


SUMMARY_ROWS = (   # (key in the row data, label key in UI_TEXT, format; None = text)
    ("opener", "s_opener", None),
    ("apm", "s_apm", "{:.1f}"),
    ("pps", "s_pps", "{:.2f}"),
    ("app", "s_app", "{:.2f}"),
    ("lines_sent", "s_lines", "{:d}"),
    ("pieces", "s_pieces", "{:d}"),
    ("max_ren", "s_max_ren", "{:d}"),
    ("tetris", "s_tetris", "{:d}"),
    ("tspin", "s_tspin", "{:d}"),
    ("tspin_single", "s_tss", "{:d}"),
    ("tspin_double", "s_tsd", "{:d}"),
    ("tspin_triple", "s_tst", "{:d}"),
    ("tspin_mini", "s_tsm", "{:d}"),
    ("perfect_clear", "s_pc", "{:d}"),
)   # shown: the ones in display.summary_items (same order as config_store.SUMMARY_ITEMS)


def summary_side(side):
    """One player's row values for the summary, from their snapshot."""
    side = side or {}
    stats = side.get("match_stats") or {}
    out = side_values(side)
    out.update({k: stats.get(k) for k, _, fmt in SUMMARY_ROWS if fmt is not None and k not in out})
    out["opener"] = side.get("opener")
    out["opener_en"] = side.get("opener_en") or side.get("opener")
    out["puyo"] = is_puyo(side)
    return out


class SummaryBlock(Band):
    """End-of-match summary: both players' totals side by side, shown while
    the finished match is on screen (frozen). Label in the middle, 1P on the
    left in blue, 2P on the right in red; the box follows the chosen style."""

    WIDTH = 212   # fits between the left NEXT column and the right HOLD box
    TITLE_H = 28
    ROW_H = 20
    # text sizes (reference px x u); the user asked for these bigger than the stats' small labels
    TITLE_PX, LABEL_PX, VALUE_PX, TEXT_PX = 15, 12, 15, 12
    COL_X = 0.2   # center of the 1P column (2P mirrored), share of the width
    # opener names are long: up to this many lines in their column (user's request)
    TEXT_LINES, TEXT_LINE_H = 3, 14

    def __init__(self, parent):
        super().__init__(parent, fade=None, draggable=True)
        self.drag_target = "summary"
        self.style = "band"
        self.u = 1.0
        self.language = "ja"
        self.opener_language = "ja"
        self.duration = 0.0
        self.sides = {"left": summary_side(None), "right": summary_side(None)}
        self.rows = list(SUMMARY_ROWS)

    def configure(self, style, language, u, items=None):
        """items: display.summary_items (None = every row)."""
        self.style, self.language, self.u = style, language, u
        self.rows = [r for r in SUMMARY_ROWS if items is None or r[0] in items]
        self._resize()

    def update_match(self, state):
        self.duration = state.get("match_elapsed_s", 0) or 0
        self.sides = {"left": summary_side(state.get("left")), "right": summary_side(state.get("right"))}
        self._resize()

    def _text_lines(self, side, key):
        """A text row's (opener's) lines in its column, or None for none."""
        if self.sides[side].get("puyo"):
            return None
        v = self.sides[side].get(key)
        if self.opener_language == "en":   # the English name (Japanese where there's none)
            v = self.sides[side].get(key + "_en") or v
        if not v:
            return ["--"]
        u = self.u
        return wrap_lines(v, self.TEXT_PX * u, BOLD, 2 * self.WIDTH * u * self.COL_X - 12 * u, self.TEXT_LINES)

    def _row_heights(self):
        out = []
        for key, _, fmt in self.rows:
            n = 1
            if fmt is None:
                n = max([len(self._text_lines(sd, key) or []) for sd in ("left", "right")] + [1])
            out.append(self.ROW_H + (n - 1) * self.TEXT_LINE_H)
        return out

    def _resize(self):
        u = self.u
        size = (int(self.WIDTH * u), int((self.TITLE_H + sum(self._row_heights()) + 8) * u))
        if (self.width(), self.height()) != size:
            self.setFixedSize(*size)
        self.update()

    def paintEvent(self, event):
        use_colors(self)
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
            elif st == "minimal":   # no box: a line under the title instead
                p.fillRect(QtCore.QRectF(r.width() * 0.15, 26 * u, r.width() * 0.7, 1.5 * u),
                           minimal_line(a, max(self.opacity, 0.5)))
            elif frame_of(st):
                # a table needs some backing to be readable
                paint_frame(p, r, "square" if st == "slash" else frame_of(st), u, a, max(self.opacity, 0.5))
            elif st != "text":
                band = QtGui.QColor(*BAND_RGB)
                band.setAlphaF(max(self.opacity, 0.5) * a)   # a table needs some backing to be readable
                p.setPen(QtCore.Qt.PenStyle.NoPen)
                p.setBrush(band)
                radius = 0 if st in ("gauge", "simple") else 6 * u
                p.drawRoundedRect(r, radius, radius)
                if st == "gauge":
                    for x0, x1, side in ((0, r.width() / 2, "left"), (r.width() / 2, r.width(), "right")):
                        c = QtGui.QColor(*PLAYER_COLORS[side])
                        c.setAlphaF(a)
                        p.fillRect(QtCore.QRectF(x0, 0, x1 - x0, 2.5 * u), c)
        ui = UI_TEXT[self.language]
        outline = 1.3 * u if st in ("text", "minimal") else 0
        W = r.width()
        title = f"{ui['summary']}  {fmt_clock(self.duration)}"
        draw_text(p, W / 2, 20 * u, title, self.TITLE_PX * u, BOLD, WHITE, "center", outline, a)
        top = self.TITLE_H + 4
        for (key, label_key, fmt), row_h in zip(self.rows, self._row_heights()):
            base = (top + 15) * u
            extra = (row_h - self.ROW_H) * u    # a text row of several lines
            draw_text(p, W / 2, base + extra / 2, ui[label_key], self.LABEL_PX * u, SEMI, SOFT, "center", outline, a)
            top += row_h
            # each player's column centered on its own side (user's request)
            for side, x in (("left", W * self.COL_X), ("right", W * (1 - self.COL_X))):
                if self.sides[side].get("puyo"):   # a Puyo side's column stays empty
                    continue
                v = self.sides[side].get(key)
                if fmt is None:     # text row (opener): a little smaller, over lines in its column
                    lines = self._text_lines(side, key)
                    y = base + (extra - (len(lines) - 1) * self.TEXT_LINE_H * u) / 2
                    for line in lines:
                        draw_text(p, x, y, line, self.TEXT_PX * u, BOLD, PLAYER_TEXT_COLORS[side], "center", outline, a)
                        y += self.TEXT_LINE_H * u
                    continue
                text = "--" if v is None else fmt.format(v)
                draw_text(p, x, base, text, self.VALUE_PX * u, BOLD, PLAYER_TEXT_COLORS[side], "center", outline, a)


class OpenerBadge(Band):
    """The recognized opener (開幕テンプレ), drawn for display.opener_display,
    each for POPUP_S seconds after it's recognized (see popup_alpha):
      "board"   big over the player's own board (A)
      "hold"    small under the HOLD box (B)
      "namebar" one line on the player's name bar (C)
      "top"     both players at the top center (D)
    side is "left" / "right", or "both" for "top". The box follows the chosen
    style, with the player's color as the accent."""

    NAME_PX = {"board": 28, "hold": 15, "top": 18}
    LABEL_PX = {"board": 13, "hold": 10, "top": 11}
    NAMEBAR_PX = 12

    def __init__(self, parent, side):
        super().__init__(parent, fade=None, draggable=True)
        self.side = side
        self.drag_target = "opener"   # set_drag_targets: or just this player's
        self.mode = "board"
        self.style = "band"
        self.u = 1.0
        self.language = "ja"
        self.names = {"left": None, "right": None}
        self.alpha = 1.0

    def configure(self, mode, style, language, u):
        self.mode, self.style, self.language, self.u = mode, style, language, u
        self._resize()

    def set_names(self, names, alpha=1.0):
        """Called every frame while a name is up (the fade timer): repaints
        only when something changed — the name or the fade (it repainted 60
        times a second while nothing moved)."""
        changed = names != self.names
        if changed:
            self.names = dict(names)
            self._resize()
        if changed or abs(alpha - self.alpha) > 0.002:
            self.alpha = alpha
            self.update()

    def _label(self):
        return UI_TEXT[self.language]["s_opener"]

    def _namebar_text(self):
        sep = "：" if self.language == "ja" else ": "
        return f"{self._label()}{sep}{self.names.get(self.side) or ''}"

    def _resize(self):
        u, m = self.u, self.mode
        if m == "namebar":
            w, h = text_width(self.NAMEBAR_PX * u, BOLD, self._namebar_text()) + 22 * u, 20 * u
        elif m == "top":
            l, r = self.names["left"] or "--", self.names["right"] or "--"
            # "vs" sits in the middle, so each half fits the longer name
            w = (2 * max(text_width(18 * u, BOLD, l), text_width(18 * u, BOLD, r))
                 + text_width(13 * u, BOLD, "vs") + 52 * u)
            w, h = max(w, 200 * u), 50 * u
        else:
            name = self.names.get(self.side) or ""
            w = max(text_width(self.NAME_PX[m] * u, BOLD, name),
                    text_width(self.LABEL_PX[m] * u, BOLD, self._label())) + (44 if m == "board" else 24) * u
            h = (68 if m == "board" else 42) * u
        if self.style == "slash" and m != "namebar":
            # the slanted ends cut into the box: longer, so the name keeps clear of them (user's request)
            w += 2 * slant_dx(QtCore.QRectF(0, 0, w, h), u) + 16 * u
        self.setFixedSize(int(w), int(h))
        self.update()

    def _accents(self, a):
        sides = ("left", "right") if self.side == "both" else (self.side,)
        out = []
        for sd in sides:
            c = QtGui.QColor(*PLAYER_COLORS[sd])
            c.setAlphaF(a)
            out.append(c)
        return out

    def paintEvent(self, event):
        use_colors(self)
        st, u, m = self.style, self.u, self.mode
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        a = self.alpha * (0.45 if self.dim else 1.0)
        r = QtCore.QRectF(self.rect())
        accents = self._accents(a)
        radius = r.height() / 2 if m == "namebar" else (10 if m == "board" else 6) * u
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        if st == "pop":
            fill = accents[0] if len(accents) == 1 else QtGui.QColor(*POP_CLOCK_RGB, int(255 * a))
            rim = QtGui.QColor(255, 255, 255)
            rim.setAlphaF(a)
            p.setBrush(fill)
            p.setPen(QtGui.QPen(rim, 2.5 * u))
            inner = r.adjusted(1.5 * u, 1.5 * u, -1.5 * u, -1.5 * u)
            p.drawRoundedRect(inner, min(radius, inner.height() / 2), min(radius, inner.height() / 2))
        elif frame_of(st):
            kind = frame_of(st)
            if m == "namebar" and kind in ("square", "slash"):
                kind = "rounded"   # a pill on the name bar
            accent = PLAYER_COLORS[self.side] if self.side in PLAYER_COLORS and st in ("frame", "slash") else None
            paint_frame(p, r, kind, u, a, max(self.opacity, 0.78), accent)
        elif st != "text":
            band = QtGui.QColor(*BAND_RGB)
            band.setAlphaF(max(self.opacity, 0.78) * a)
            p.setBrush(band)
            rr = 0 if st in ("gauge", "simple") else radius
            p.drawRoundedRect(r, rr, rr)
            if m == "namebar":   # accent ring around the pill
                p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                p.setPen(QtGui.QPen(accents[0], 2 * u))
                p.drawRoundedRect(r.adjusted(1 * u, 1 * u, -1 * u, -1 * u), rr, rr)
            else:                # accent bar along the bottom (split for both players)
                bar_h = 3 * u
                n = len(accents)
                for i, c in enumerate(accents):
                    p.fillRect(QtCore.QRectF(r.width() * i / n, r.height() - bar_h, r.width() / n, bar_h), c)
        outline = 1.6 * u if st in ("text", "minimal") else 0
        W, H = r.width(), r.height()
        if m == "namebar":
            draw_text(p, W / 2, H / 2 + 4.2 * u, self._namebar_text(), self.NAMEBAR_PX * u, BOLD, WHITE,
                      "center", outline, a, OPENER_NAME_THICKEN)
        elif m == "top":
            draw_text(p, W / 2, 15 * u, self._label(), 11 * u, BOLD, SOFT, "center", outline, a)
            inset = (26 if st == "slash" else 14) * u   # past the slanted ends
            draw_text(p, inset, 38 * u, self.names["left"] or "--", 18 * u, BOLD,
                      PLAYER_TEXT_COLORS["left"], "left", outline, a, OPENER_NAME_THICKEN)
            draw_text(p, W / 2, 37 * u, "vs", 13 * u, BOLD, SOFT, "center", outline, a)
            draw_text(p, W - inset, 38 * u, self.names["right"] or "--", 18 * u, BOLD,
                      PLAYER_TEXT_COLORS["right"], "right", outline, a, OPENER_NAME_THICKEN)
        else:
            label_color = (235, 242, 255) if st == "pop" else PLAYER_TEXT_COLORS[self.side]
            name = self.names.get(self.side) or ""
            if m == "board":
                draw_text(p, W / 2, 20 * u, self._label(), self.LABEL_PX[m] * u, BOLD, label_color, "center", outline, a)
                draw_text(p, W / 2, 54 * u, name, self.NAME_PX[m] * u, BOLD, WHITE, "center", outline, a,
                          OPENER_NAME_THICKEN)
            else:   # hold
                lx = (12 + (14 if st == "slash" else 0)) * u   # past the slanted edge
                draw_text(p, lx, 14 * u, self._label(), self.LABEL_PX[m] * u, BOLD, label_color, "left", outline, a)
                draw_text(p, lx, 33 * u, name, self.NAME_PX[m] * u, BOLD, WHITE, "left", outline, a,
                          OPENER_NAME_THICKEN)
        if self.editing:   # position-adjust mode: outlined like the other parts
            p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            p.setPen(QtGui.QPen(QtGui.QColor(edit_color(self)), 2, QtCore.Qt.PenStyle.DashLine))
            p.drawRect(r.adjusted(1, 1, -1, -1))


# --- the 「猫」 opener display (user's request: a cat comes in from outside
# the screen, gets in the way of the board and holds up the opener's name on
# a sheet of paper). Frames: assets/cat/ (tools/cat/make_cat.py). 1P's cat is
# mirrored, so it comes in from the left edge; 2P's from the right.
CAT_DIR = ROOT_DIR / "assets" / "cat"
CAT_BOTTOM_Y = 632        # the clip's bottom edge, reference px (the cat stands about on the score)
CAT_SCALE = 0.625         # clip px -> reference px: the clip is 1280 wide (sharper), shown 800 wide (user: a bit bigger than the old 640)
# Where the middle of the clip goes (reference px): the standing cat
# is in the clip's middle, so it stands over each board's middle at any size;
# a bigger clip just starts its walk further off the screen's edge.
CAT_CENTER_X = {"left": 320, "right": 912}
CAT_MIN_STILL_S = 0.5     # the standing-still part is never squeezed below this
CAT_PREPARE_PER_TICK = 2  # frames read and scaled ahead of time every 15 ms (CatPopup.prepare): 130 a second, ahead of the 24 a second it shows
CAT_PAPER_MIN_PX = 30     # smallest one-line name on the paper (200x140 box); longer names run off its sides
# The second clip (assets/cat2: the cat breaks through the glass with a sign):
# one popup in CAT2_EVERY. Which one is decided from the match, the side and
# the name (pick_cat_clip), so the HUD and the OBS page show the same cat.
# 0 = never: held back for now (user, 2026-11-04), and left out of the
# release zip (tools/make_release.py).
CAT2_EVERY = 0


def load_cat(name="cat"):
    """A cat clip (assets/<name>/cat.json), or None if it isn't there. The
    frame images are read when first needed (cat_image): reading all 225 up
    front froze the app for half a second the first time the cat display was
    chosen."""
    folder = ROOT_DIR / "assets" / name
    try:
        data = json.loads((folder / "cat.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    data["_name"], data["_dir"] = name, str(folder)
    return data


def fnv1a(text):
    """A small hash, the same in obs/overlay.html (catHash)."""
    h = 0x811C9DC5
    for b in text.encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h


def pick_cat_clip(state, side, name):
    """"cat2" for about one popup in CAT2_EVERY, else "cat": from this match's
    start, the side and the opener's name, so the HUD and OBS agree."""
    start = (state or {}).get("match_start_t") or 0
    key = f"{int(round(float(start) * 10))}|{side}|{name}"
    return "cat2" if CAT2_EVERY and fnv1a(key) % CAT2_EVERY == 0 else "cat"


def cat_image(frame, folder=None):
    """A frame's image read from its file (not kept: only the scaled copies
    are, see CatFrames), or None for a frame without the cat."""
    if not frame.get("file"):
        return None
    return QtGui.QImage(str(Path(folder or CAT_DIR) / frame["file"]))


class CatFrames:
    """The cat's frames scaled to the size shown, shared by both players'
    cats (1P's is mirrored as it's drawn). Kept so none is scaled while the
    cat walks, but only one set, and nothing once the cat display isn't
    chosen: two mirrored sets plus the read files took +380 MB at a 1756-wide
    game window and +650 MB at 2560, and stayed taken after switching away
    (user: make the app lighter)."""

    def __init__(self):
        self.cat, self.u, self.frames = None, None, {}

    def get(self, cat, u, index):
        """Frame `index` at size u: (QImage, x, y) in the unmirrored clip, or None."""
        if cat is not self.cat or u != self.u:
            self.cat, self.u, self.frames = cat, u, {}
        if index not in self.frames:
            f = cat["frames"][index]
            src = cat_image(f, cat.get("_dir"))
            if src is None or src.isNull():
                self.frames[index] = None
            else:
                img = src.scaled(max(1, round(src.width() * u)), max(1, round(src.height() * u)),
                                 QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                                 QtCore.Qt.TransformationMode.SmoothTransformation)
                self.frames[index] = (img.convertToFormat(QtGui.QImage.Format.Format_ARGB32_Premultiplied),
                                      f["x"] * u, f["y"] * u)
        return self.frames[index]

    def has(self, cat, u, index):
        return cat is self.cat and u == self.u and index in self.frames

    def clear(self):
        self.cat, self.u, self.frames = None, None, {}


CAT_FRAMES = {}   # clip name -> its CatFrames (the two clips never push each other out)


def cat_frames(cat):
    return CAT_FRAMES.setdefault((cat or {}).get("_name", "cat"), CatFrames())


def cat_pos(cat, age, seconds):
    """Where in the clip `age` seconds after the opener was recognized falls:
    (frame, next frame, how far toward the next 0-1), or None once the cat has
    walked off. Between two frames they're blended (user: smoother than the
    clip's own 24 frames a second). The paper stays up for about `seconds`
    (display.opener_seconds; 0: until the match ends).

    Only the part where the cat stands still (still_start-still_end) is fitted
    to that time: played faster when it's shorter, back and forth (an odd
    number of times, so it ends where the walk off starts) when it's longer.
    The walk in and the walk off always play as filmed: before, the paper
    time ended wherever it was and cut into the walk off (user: it skipped a
    few frames as it left)."""
    n = len(cat["frames"])
    hs, he = cat["hold_start"], cat["hold_end"]
    s0, s1 = cat.get("still_start", hs), cat.get("still_end", he)
    span = max(1, s1 - s0)
    # never before the clip's start: the server's opener age can be a hair
    # below 0 right as the opener is recognized, which made a negative blend
    # weight (an exception in paintEvent: before log_errors the app closed,
    # after it the cat skipped frames — user: it closed / the paper went blank)
    t = max(0.0, age) * cat["fps"]
    if t < s0:
        pos = t
    else:
        u = t - s0
        if seconds <= 0:      # until the match ends: back and forth at normal speed
            k = u % (2 * span)
            pos = s0 + (k if k <= span else 2 * span - k)
        else:
            fit = max(CAT_MIN_STILL_S * cat["fps"], seconds * cat["fps"] - (s0 - hs) - (he - s1))
            if u < fit:
                passes = 2 * round((fit / span - 1) / 2) + 1    # nearest odd number, at least 1
                k = (u * passes * span / fit) % (2 * span)
                pos = s0 + (k if k <= span else 2 * span - k)
            else:
                pos = s1 + (u - fit)
                if pos > n - 1:
                    return None
    i = int(pos)
    return i, min(i + 1, n - 1), pos - i


def cat_frame(cat, age, seconds):
    """The frame of cat_pos (None once the cat has walked off)."""
    p = cat_pos(cat, age, seconds)
    return None if p is None else p[0]


PAPER_W, PAPER_H = 184, 130   # room for the name on the paper (its 200x140 box less a margin)
PAPER_MAX_PX = 40              # (user: smaller; was 54)
PAPER_TWO_LINE_MIN_PX = 22    # two lines as small as this still beat running off the paper


def paper_layout(name, measure):
    """How to write `name` on the cat's paper: (lines, text px in the 200x140
    box). measure(text): its width at 100 px. One line when that's big enough
    (CAT_PAPER_MIN_PX); else two lines when they fit (user: fit it on the paper
    where it can — broken at a space if there is one, else between any two
    characters, keeping the lines even); else one line at CAT_PAPER_MIN_PX that
    runs off the paper's sides."""
    one = min(PAPER_MAX_PX, PAPER_W * 100 / max(1.0, measure(name)))
    if one >= CAT_PAPER_MIN_PX:
        return [name], one
    spaces = [i for i, c in enumerate(name) if c == " "]
    best = None
    for i in spaces or range(1, len(name)):
        a, b = name[:i].rstrip(), name[i:].lstrip()
        if not a or not b:
            continue
        size = min(PAPER_MAX_PX, PAPER_H / 2.3, PAPER_W * 100 / max(1.0, measure(a), measure(b)))
        if best is None or size > best[1]:
            best = ([a, b], size)
    if best and best[1] >= PAPER_TWO_LINE_MIN_PX:
        return best
    return [name], CAT_PAPER_MIN_PX


def opener_offset(d, side):
    """Where a player's opener name is moved to: both players' offset plus
    that player's own ("both": the top-center box, the shared one only)."""
    x, y = d["opener_offset_x"], d["opener_offset_y"]
    if side in ("left", "right"):
        x, y = x + d[f"opener_{side}_offset_x"], y + d[f"opener_{side}_offset_y"]
    return x, y


class CatPopup(QtWidgets.QWidget):
    """One player's cat (see load_cat). Click-through like the rest of the HUD.
    Frames are scaled (and mirrored for 1P) once per size and kept, so each
    repaint only blends two ready images."""

    def __init__(self, parent, side):
        super().__init__(parent)
        self.side = side
        self.cat = None
        self.pos = None
        self.name = ""
        self.u = 1.0
        self._dirty = None        # the area painted last (show_frame repaints only that and the new one)
        self._todo = []           # frames still to scale (prepare)
        self._prep_timer = QtCore.QTimer(self)
        self._prep_timer.setInterval(15)
        self._prep_timer.timeout.connect(self._prepare_some)
        self.editing = False      # position-adjust mode: outlined, and dragged like the other parts
        self._paper, self._paper_for = None, None   # paper_layout of the name, kept
        self.drag_target = "opener"   # set_drag_targets: or just this player's
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def show_frame(self, cat, pos, name, u):
        self.cat, self.pos, self.name, self.u = cat, pos, name, u
        w, h = cat["size"]
        size = QtCore.QSize(int(w * u), int(h * u))
        if self.size() != size:
            self.setFixedSize(size)
            self._dirty = None
        # Only the cat and its paper are repainted, not the whole clip-sized
        # widget (mostly empty): on a big game window repainting all of it
        # every frame went past 16 ms (user: the popup got heavy on a big window)
        area = self._area(pos)
        if self.editing or area is None or self._dirty is None:
            self.update()
        else:
            self.update(area.united(self._dirty))
        self._dirty = area

    def _area(self, pos):
        """Where frames pos[0] / pos[1] and the name on the paper are drawn."""
        rect = QtCore.QRect()
        for index in (pos[0], pos[1]):
            f = self._frame(index)
            if f is not None:
                img, x, y = f
                rect = rect.united(QtCore.QRect(x, y, img.width(), img.height()))
            quad = self._quad(index)
            if quad:   # a long name runs off the paper's sides
                poly = QtGui.QPolygonF([QtCore.QPointF(q.x() * self.u, q.y() * self.u) for q in quad])
                b = poly.boundingRect().toAlignedRect()
                rect = rect.united(b.adjusted(-b.width(), -8, b.width(), 8))
        return None if rect.isNull() else rect.adjusted(-2, -2, 2, 2)

    def prepare(self, cat, u):
        """Scale every frame ahead of time, so none is scaled while the cat is
        walking (that made it hitch) — a few at a time in the order they're
        shown, between other work: all at once froze the app for about a
        second the first time the cat display was chosen (user: it flickered)."""
        self.cat, self.u = cat, u
        frames = cat_frames(cat)
        self._todo = [i for i in range(len(cat["frames"])) if not frames.has(cat, u, i)]
        if self._todo and not self._prep_timer.isActive():
            self._prep_timer.start()

    def _prepare_some(self):
        for _ in range(CAT_PREPARE_PER_TICK):
            if not self._todo or self.cat is None:
                self._prep_timer.stop()
                return
            self._frame(self._todo.pop(0))

    def _frame(self, index):
        """Frame `index` at self.u and its top-left in this widget, or None.
        For 1P the frame is mirrored as it's drawn (paintEvent)."""
        f = cat_frames(self.cat).get(self.cat, self.u, index)
        if f is None:
            return None
        img, x, y = f
        if self.side == "left":   # 1P: comes in from the left
            x = self.cat["size"][0] * self.u - x - img.width()
        return img, int(round(x)), int(round(y))

    def release(self):
        """The cat display isn't chosen any more: let go of the frames."""
        self._prep_timer.stop()
        self._todo, self.cat, self.pos, self._dirty = [], None, None, None
        for frames in CAT_FRAMES.values():
            frames.clear()

    def _draw(self, p, f):
        img, x, y = f
        if self.side == "left":
            p.save()
            p.translate(x + img.width(), y)
            p.scale(-1, 1)
            p.drawImage(0, 0, img)
            p.restore()
        else:
            p.drawImage(x, y, img)

    def _quad(self, index):
        f = self.cat["frames"][index]
        if not f.get("paper"):
            return None
        quad = [QtCore.QPointF(*pt) for pt in f["paper"]]
        if self.side == "left":
            w = self.cat["size"][0]
            quad = [QtCore.QPointF(w - q.x(), q.y()) for q in quad]
            quad = [quad[1], quad[0], quad[3], quad[2]]
        return quad

    def set_editing(self, on):
        self.editing = on
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, not on)
        self.setCursor(QtCore.Qt.CursorShape.SizeAllCursor if on else QtCore.Qt.CursorShape.ArrowCursor)
        self.update()

    def mousePressEvent(self, event):
        if self.editing and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.window().drag_start(event.globalPosition(), self.drag_target)

    def mouseMoveEvent(self, event):
        if self.editing:
            self.window().drag_move(event.globalPosition())

    def mouseReleaseEvent(self, event):
        if self.editing:
            self.window().drag_end()

    def wheelEvent(self, event):   # positioning: the wheel resizes the opener names
        if self.editing:
            self.window().wheel_resize(self.drag_target, event.angleDelta().y())
            event.accept()

    def paintEvent(self, event):
        if self.editing:   # something to grab everywhere (clear pixels let clicks through), and the outline
            p = QtGui.QPainter(self)
            p.fillRect(self.rect(), QtGui.QColor(*BAND_RGB, 60))
            p.setPen(QtGui.QPen(QtGui.QColor(edit_color(self)), 2, QtCore.Qt.PenStyle.DashLine))
            p.drawRect(self.rect().adjusted(1, 1, -1, -1))
            p.end()
        if not self.cat or self.pos is None:
            return
        i, j, frac = self.pos
        frac = min(max(frac, 0.0), 1.0)
        a, b = self._frame(i), self._frame(j) if j != i else None
        if a is None and b is None:
            return
        # Between two of the clip's frames (24 a second, shown at 60): the
        # first drawn solid, the next over it at the in-between opacity —
        # where both are solid it stays solid. Qt does this itself; a numpy
        # blend of every pixel each repaint was the heavy part on big windows.
        p = QtGui.QPainter(self)
        if a is not None:
            self._draw(p, a)
        if b is not None and frac > 0:
            p.setOpacity(frac)
            self._draw(p, b)
            p.setOpacity(1.0)
        qa, qb = self._quad(i), self._quad(j)
        quad = qa if qb is None else qb if qa is None else \
            [QtCore.QPointF(pa.x() + (pb.x() - pa.x()) * frac, pa.y() + (pb.y() - pa.y()) * frac) for pa, pb in zip(qa, qb)]
        if quad and self.name:
            # the name on the paper, following its corners (unmirrored text)
            p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing)
            r = QtCore.QRectF(0, 0, 200, 140)
            t = QtGui.QTransform()
            QtGui.QTransform.quadToQuad(QtGui.QPolygonF([r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]),
                                        QtGui.QPolygonF(quad), t)
            p.setTransform(t * QtGui.QTransform.fromScale(self.u, self.u))
            # one line, two lines, or running off the paper (paper_layout)
            font100 = _font(100, BOLD)
            key = (self.name, font100.family())   # again when the font setting changes
            if self._paper_for != key:
                fm = QtGui.QFontMetricsF(font100)
                self._paper, self._paper_for = paper_layout(self.name, fm.horizontalAdvance), key
            lines, size = self._paper
            p.setFont(_font(int(size), BOLD))
            p.setPen(QtGui.QColor(25, 25, 30))
            step = size * 1.1
            for k, line in enumerate(lines):
                cy = r.height() / 2 + (k - (len(lines) - 1) / 2) * step
                p.drawText(QtCore.QRectF(-2000, cy - size, 4200, 2 * size), QtCore.Qt.AlignmentFlag.AlignCenter, line)


class HudWindow(QtWidgets.QWidget):
    # New offset_x, offset_y (reference px) while the user drags the stats;
    # finished=True on release (the settings window saves then).
    offset_dragged = QtCore.pyqtSignal(str, int, int, bool)
    part_resized = QtCore.pyqtSignal(str, float)   # the wheel resized a part while positioning (part, size)
    match_screen_changed = QtCore.pyqtSignal(bool)  # the game went to / left the match screen
    opener_recorded = QtCore.pyqtSignal()           # a finished match was added to opener_stats
    session_changed = QtCore.pyqtSignal(object)     # 今日の成績 from the server changed (state["session"])
    # (the HUD shows in screen captures, the parts kept off the game screen for it)
    reading_overlap = QtCore.pyqtSignal(bool, list)
    language_changed = QtCore.pyqtSignal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.edit_mode = False
        self._last_match_screen = None   # see match_screen_changed
        self._drag = None
        # Never takes the keyboard focus, not even when shown: the game pauses
        # itself when it loses focus (user report: a window flashed, the game
        # stopped taking input and paused — that was the HUD / settings
        # window appearing on start-up and taking the focus).
        self.setWindowFlags(
            QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
            | QtCore.Qt.WindowType.Tool
            | QtCore.Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self.read_zones_layer = ReadZonesLayer(self)   # (first: under every part)
        self.challenge = ChallengeLayer(self)          # 縛りプレイ: over the boards, under the parts
        self.stats = {"left": StatBlock(self, "left"), "right": StatBlock(self, "right")}
        self.versus = VersusBlock(self)
        self.summary = SummaryBlock(self)
        self.badges = {sd: OpenerBadge(self, sd) for sd in ("left", "right", "both")}
        self.cats = {sd: CatPopup(self, sd) for sd in ("left", "right")}
        for c in self.cats.values():
            c.setVisible(False)
        self._cat = None   # the clip, loaded the first time it's shown
        self._cat2 = None  # the second clip (one popup in CAT2_EVERY), loaded when first picked
        self._cat_clip = {"left": None, "right": None}   # the clip each side's popup plays
        # each cat runs on this PC's clock from when it started: the age the
        # server sends 10 times a second jitters by a few hundredths of a
        # second, and following it made the cat stutter (user: not smooth)
        self._cat_start = {"left": None, "right": None}
        self._cat_name = {"left": None, "right": None}
        self.events = {"left": EventBlock(self, "left"), "right": EventBlock(self, "right")}
        self.clock = ClockBlock(self)
        self.session = SessionBlock(self)
        self.edit_hint = QtWidgets.QLabel(
            "位置調整中：黄色い枠をドラッグして動かせます（設定画面の「完了」で終了）", self)
        self.edit_hint.setStyleSheet(
            "color:#111; background:#fde047; padding:4px 10px; border-radius:4px; font-weight:700;")
        self.edit_hint.setVisible(False)
        # the summary over every other part where they overlap (user's request;
        # only a cat popup, raised when it shows, goes over it)
        self.summary.raise_()
        self.edit_hint.raise_()
        self._hwnd = None
        self._last_geom = None
        # following the game's window: nothing is shown until it has been
        # found and the HUD put over it (a report: just after start the HUD
        # showed over a Discord window, until the app was restarted)
        self._follows = bool(settings["hud"]["follow_game"]) and HAS_WIN32
        self._size = (REFERENCE_W, REFERENCE_H)
        self._scale = 1.0
        self._last_state = {}
        self._last_raw_state = None   # the last state as the server sent it (on_state)
        self._was_frozen = None       # frozen in the last state (a match ending: _record_finished_match)
        self._state_t = time.monotonic()   # when _last_state arrived (opener fade timing)
        self._fade = QtCore.QTimer(self)   # repaints the opener names while they're up
        self._fade.setInterval(16)
        self._fade.setTimerType(QtCore.Qt.TimerType.PreciseTimer)   # an even 60 a second (the cat's walk)
        self._fade.timeout.connect(self._place_openers)
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

        # The HUD's own health, once a second (user: sometimes only OBS shows
        # it and the HUD doesn't): puts the HUD back in front of the game if
        # the game ended up over it, and writes what it sees to
        # logs/hud_status.txt (and each change to logs/hud.log).
        self._health_sig = None
        self._recv_t = time.monotonic()
        self._health_written = 0.0
        self._health = QtCore.QTimer(self)
        self._health.timeout.connect(self._check_health)
        self._health.start(1000)

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
        set_text_style(d["text_weight"], d["text_outline"], d["text_outline_width"])
        set_colors(d["bg_color"], d["text_color"], d["line_color"])
        set_font(d["font_family"], d["font_file"])
        set_labels(d["labels"], d["language"])
        self.set_drag_targets()
        set_player_colors(d["player_color_left"], d["player_color_right"])

        def pu(part):   # this part's size (its own, or the overall one)
            return s * part_value(d, part, "scale")

        def look(widget, part):   # this part's background strength and colors
            widget.opacity = part_value(d, part, "background_opacity")
            widget.colors = (part_value(d, part, "bg_color"), part_value(d, part, "text_color"),
                             part_value(d, part, "line_color"))

        mode = d["stats_position"]
        shown = list(d["stat_items"])
        self.resize(int(w), int(h))
        for side in ("left", "right"):
            stat, ev = self.stats[side], self.events[side]
            look(stat, "stats")
            look(ev, "events")
            if shown and d["style"] != "versus":
                stat.configure(d["style"], mode, shown, pu("stats"))
            ev.language = d["language"]
            ev.opener_language = opener_language(d)
            ev.configure(d["style"], mode, d["event_log_count"], pu("events"))
        look(self.versus, "stats")
        if shown and d["style"] == "versus":
            self.versus.configure(shown, pu("stats"))
        look(self.clock, "clock")
        self.clock.configure(d["style"], pu("clock"))
        look(self.session, "clock")   # (drawn like the match time, its size and colors too)
        self.session.configure(d["style"], pu("clock"))
        look(self.summary, "summary")
        self.summary.opener_language = opener_language(d)
        self.summary.configure(d["style"], d["language"], pu("summary"), d["summary_items"])
        for badge in self.badges.values():
            look(badge, "opener")
            # (with the cat the boxes aren't used: kept set up as the big one)
            badge.configure("board" if d["opener_display"] == "cat" else d["opener_display"], d["style"],
                            d["language"], pu("opener"))
        if d["opener_display"] == "cat" and d["show_opener"]:
            # ready the cat's frames at this size now, not while it's walking
            QtCore.QTimer.singleShot(0, self._prepare_cats)
        elif self._cat is not None:   # not shown: let go of the clip and its frames
            for c in self.cats.values():
                c.release()
            self._cat = None
        self._place()

    def _prepare_cats(self):
        if not (self.display["opener_display"] == "cat" and self.display["show_opener"]):
            return   # switched away again before this ran
        if self._cat is None:
            self._cat = load_cat() or False
        if self._cat:
            u = self._scale * CAT_SCALE * part_value(self.display, "opener", "scale")
            for c in self.cats.values():
                c.prepare(self._cat, u)

    def _away_from_match(self):
        """Nothing is shown off the match screen (home, menus, character
        select) unless display.always_show — or while positioning parts.
        With no word from the server yet, it shows as before."""
        if not self.display["enabled"]:   # switched off (settings window / tray)
            return True
        if not self.display["show_on_hud"] and not self.edit_mode:   # shown in OBS only
            return True
        if self._follows and self._last_geom is None:   # not over the game (yet)
            return True
        return (not self.display["always_show"] and not self.display["force_show"] and not self.edit_mode
                and self._last_state.get("match_screen") is False)

    def _away_reason(self):
        """Why nothing is shown right now, in words ("" = it should show)."""
        if not self.display["enabled"]:
            return "switched off"
        if not self.display["show_on_hud"] and not self.edit_mode:
            return "OBS only (show_on_hud off)"
        if self._follows and self._last_geom is None:
            return "not over the game window (not found / minimized)"
        if self._away_from_match():
            return "not the match screen"
        return ""

    def _game_below_hud(self):
        """True when the game's window is under the HUD's (None: can't tell)."""
        if not HAS_WIN32 or self._hwnd is None:
            return None
        try:
            hud = int(self.winId())
            w, n = win32gui.GetWindow(hud, win32con.GW_HWNDNEXT), 0
            while w and n < 5000:
                if w == self._hwnd:
                    return True
                w, n = win32gui.GetWindow(w, win32con.GW_HWNDNEXT), n + 1
            return False
        except Exception:
            return None

    def _check_health(self):
        try:
            self._check_health_inner()
        except Exception as e:   # never let the check itself break the HUD
            _hud_note(f"health check failed: {e!r}")

    def _check_health_inner(self):
        now = time.monotonic()
        game_ok = (HAS_WIN32 and self._hwnd is not None and win32gui.IsWindow(self._hwnd)
                   and win32gui.IsWindowVisible(self._hwnd) and not win32gui.IsIconic(self._hwnd))
        below = self._game_below_hud() if game_ok else None
        raised = False
        if below is False and self.isVisible():
            # the game is over the HUD: back on top (without taking the focus)
            win32gui.SetWindowPos(int(self.winId()), win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
            raised = True
        if not self.isVisible():
            self.show()
            raised = True
        game_rect = None
        if game_ok:
            _, _, cw, ch = win32gui.GetClientRect(self._hwnd)
            gx, gy = win32gui.ClientToScreen(self._hwnd, (0, 0))
            game_rect = self._on_picture(gx, gy, cw, ch)
        g = self.geometry()
        dpr = self.screen().devicePixelRatio() if self.screen() else 1.0
        sg = self.screen().geometry() if self.screen() else QtCore.QRect()
        hud_rect = (round(sg.x() + (g.x() - sg.x()) * dpr), round(sg.y() + (g.y() - sg.y()) * dpr),
                    round(g.width() * dpr), round(g.height() * dpr))
        if (self._follows and game_rect is not None and self._last_geom is not None
                and any(abs(a - b) > 2 for a, b in zip(game_rect, hud_rect))):
            # not over the game (moved by Windows, a monitor change...): placed again
            _hud_note(f"HUD at {hud_rect} but the game at {game_rect}: placing it again")
            self._last_geom = None
            self._follow_game_window()
            raised = True
        parts = [name for name, w in (("stats_left", self.stats["left"]), ("stats_right", self.stats["right"]),
                                      ("clock", self.clock), ("summary", self.summary),
                                      ("events_left", self.events["left"]), ("events_right", self.events["right"]),
                                      ("versus", self.versus)) if w.isVisible()]
        connected = self.ws_client._ws is not None
        if getattr(self, "_want_excluded", False) and not getattr(self, "capture_excluded", False):
            self.hide_from_capture()   # once more (the window may have been made again)
            if not self.capture_excluded:
                self._place()
        age = now - self._recv_t
        reason = self._away_reason()
        st = self._last_state or {}
        sig = (connected, age > 5, game_ok, below, game_rect == hud_rect, self.isVisible(), reason, bool(parts),
               st.get("match_screen"))
        lines = [
            time.strftime("%Y-%m-%d %H:%M:%S") + "  HUD",
            f"server: {'connected' if connected else 'NOT connected'}, last state {age:.1f}s ago",
            f"game window: {game_rect if game_ok else 'not found / minimized / hidden'}",
            f"HUD window: {hud_rect} visible={self.isVisible()} over the game={below}"
            + ("  (raised just now)" if raised else ""),
            f"match_screen={st.get('match_screen')} frozen={st.get('frozen')} capture_ok={st.get('capture', {}).get('ok')}",
            f"hidden because: {reason or '-'}",
            f"parts shown: {', '.join(parts) or 'none'}",
            f"kept out of screen captures: {getattr(self, 'capture_excluded', None)}",
        ]
        if sig != self._health_sig or raised:
            self._health_sig = sig
            _hud_note(" | ".join(lines[1:]))
        if raised or now - self._health_written >= 5.0:
            self._health_written = now
            try:
                (ROOT_DIR / "logs" / "hud_status.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
            except OSError:
                pass

    def off_match_screen(self):
        """The server says the match screen isn't showing (home, menus)."""
        return self._last_state.get("match_screen") is False

    def _place(self):
        self._place_parts()
        self._keep_out_of_reading(openers=False)
        self._place_challenge()

    def challenge_blocked(self):
        """縛りプレイ is set, but this PC shows the HUD in screen captures:
        the recognition would read the covers and cats, so they stay off."""
        d = self.display
        return (d.get("challenge_next", "off") != "off" or d.get("challenge_cats")) and self.reading_unsafe()

    def _place_challenge(self):
        """縛りプレイ (hud/challenge.py): only while a match is being played —
        not when switched off, positioning, at the result (frozen), or where
        the HUD shows in screen captures. It doesn't follow show_on_hud: it's
        for the player, not the numbers."""
        st = getattr(self, "_last_state", None) or {}
        active = (self.display["enabled"] and not self.edit_mode and not self.reading_unsafe()
                  and not (getattr(self, "_follows", False) and getattr(self, "_last_geom", None) is None)
                  and st.get("match_screen") is True and not st.get("frozen"))
        layer = self.challenge
        if layer.geometry() != self.rect():
            layer.setGeometry(self.rect())
        layer.update_state(st, self.display, self._scale or 1.0, active)

    def reading_unsafe(self):
        """The HUD is over the game in screen captures too (Windows didn't
        keep it out: hide_from_capture), so the recognition reads it."""
        return bool(getattr(self, "_want_excluded", False)) and getattr(self, "capture_excluded", True) is False

    def _keep_out_of_reading(self, openers):
        """Where the HUD shows in screen captures, no part of it sits on what
        the recognition reads (read_zones): two users' numbers and event
        history covered the T-SPIN banners at the lower left of the board, and
        none of their T-SPINs counted. Those parts stay off the game screen
        (OBS still shows them; the settings window says why)."""
        hidden = []
        if openers:
            parts = [*(("opener", b) for b in self.badges.values()), *(("opener", c) for c in self.cats.values())]
        else:
            parts = [("stats", self.stats["left"]), ("stats", self.stats["right"]),
                     ("events", self.events["left"]), ("events", self.events["right"]),
                     ("versus", self.versus), ("clock", self.clock), ("session", self.session),
                     ("summary", self.summary)]
        unsafe = self.reading_unsafe()
        s = self._scale or 1.0
        zones = read_zones() if unsafe else []
        for name, w in parts:
            over = False
            if unsafe and w.isVisibleTo(self):
                g = w.geometry()
                x1, y1, x2, y2 = g.left() / s, g.top() / s, (g.left() + g.width()) / s, (g.top() + g.height()) / s
                over = any(x1 < zx2 and zx1 < x2 and y1 < zy2 and zy1 < y2 for zx1, zy1, zx2, zy2 in zones)
            if over != getattr(w, "blocked", False):
                w.blocked = over
                w.update()
            if over and not self.edit_mode:   # (while positioning: shown, outlined red)
                w.setVisible(False)
                if name not in hidden:
                    hidden.append(name)
        if not openers:
            layer = self.read_zones_layer
            layer.scale = s
            layer.setGeometry(0, 0, self.width(), self.height())
            layer.setVisible(unsafe and self.edit_mode)
            layer.lower()
        kept = getattr(self, "_kept_out", {})
        kept["openers" if openers else "parts"] = hidden
        self._kept_out = kept
        names = kept.get("parts", []) + [n for n in kept.get("openers", []) if n not in kept.get("parts", [])]
        state = (self.reading_unsafe(), names)
        if state != getattr(self, "_kept_out_said", None):
            self._kept_out_said = state
            self.reading_overlap.emit(*state)

    def _place_parts(self):
        """Positions everything whose size depends on content: the stat blocks
        (bottom-anchored beside the score), the events stacked above them, and
        the clock (bottom-anchored above the マッチポイント banner)."""
        s, d = self._scale, self.display
        away = self._away_from_match()
        for w in (*self.stats.values(), *self.events.values(), self.versus, self.clock, self.session, self.summary,
                  *self.badges.values(), *self.cats.values()):
            if away:
                w.setVisible(False)
        if away:
            self._fade.stop()
            return
        u = s * part_value(d, "stats", "scale")   # the gaps next to the stat block go with its size
        mode = d["stats_position"]
        any_stat = bool(d["stat_items"])
        versus = d["style"] == "versus"
        shown = any_stat and not versus
        for side in ("left", "right"):
            stat, ev = self.stats[side], self.events[side]
            other = self._last_state.get("right" if side == "left" else "left") or {}
            vs_puyo = VS_PUYO_SHIFT_X[mode] if other.get("puyo") else 0   # (really Puyo, not just hidden)
            anchor_x = (STAT_ANCHOR_X[mode][side] + vs_puyo + d["offset_x"] + d[f"stats_{side}_offset_x"]) * s
            if d["style"] in NEW_STYLES:   # a little room from the board (see NEW_STYLE_GAP)
                anchor_x += NEW_STYLE_GAP * u * (-1 if mode == "left" else 1)
            bottom = (STAT_BOTTOM_Y + d["offset_y"] + d[f"stats_{side}_offset_y"]) * s
            # a side playing Puyo shows nothing (still shown while positioning)
            puyo = is_puyo(self._last_state.get(side)) and not self.edit_mode
            stat.setVisible(shown and not puyo)
            if shown and not puyo:
                x = anchor_x - stat.width() if mode == "left" else anchor_x
                stat.move(int(x), int(bottom - stat.height()))
                bottom -= stat.height() + EVENT_GAP * u
            # (Not ev.isVisible(): that is also False whenever the window
            # itself isn't shown, which would skip placing it.)
            show_events = d["show_event_log"] and not puyo and ev.update_side(self._last_state.get(side))
            ev.setVisible(show_events)
            if show_events:
                # stacked above the stats by default; its own offsets move it from there
                ev.adjustSize()
                ex = anchor_x + d["event_offset_x"] * s
                x = ex - ev.width() if mode == "left" else ex
                ev.move(int(x), int(bottom + d["event_offset_y"] * s - ev.height()))
        # Against a Puyo player the match time is never shown: it tells how
        # far into margin time the match is, which helps one side (user's
        # request, for fairness). The state / capture lines still show.
        # 今日の成績: the server's lines (a sample while positioning, to drag)
        lang = d["language"] if d["language"] in ("ja", "en") else "ja"
        rows = ((self._last_state.get("session") or {}).get("lines") or {}).get(lang) or []
        self.session.set_rows(rows or (SessionBlock.SAMPLE[lang] if self.edit_mode else []))
        show_session = d["show_session"] and bool(self.session.rows)
        self.session.setVisible(show_session)
        if show_session:
            self.session.adjustSize()
            self.session.move(int((CLOCK_CENTER_X + d["session_offset_x"]) * s - self.session.width() / 2),
                              int((SESSION_TOP_Y + d["session_offset_y"]) * s))
        self.clock.set_hide_time(puyo_in_match(self._last_state) and not self.edit_mode)
        self.clock.setVisible(d["show_clock"] and bool(self.clock._lines()))
        self.clock.adjustSize()
        clock_top = CLOCK_BOTTOM_Y * s - self.clock.height()   # default spot (the versus block uses it)
        self.clock.move(int((CLOCK_CENTER_X + d["clock_offset_x"]) * s - self.clock.width() / 2),
                        int(clock_top + d["clock_offset_y"] * s))
        self._place_openers()
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
                self._lost_game()
                return
            _, _, cw, ch = win32gui.GetClientRect(self._hwnd)
            left, top = win32gui.ClientToScreen(self._hwnd, (0, 0))
        except Exception:
            self._hwnd = None
            self._lost_game()
            return
        if cw <= 0 or ch <= 0:
            self._lost_game()
            return
        left, top, cw, ch = self._on_picture(left, top, cw, ch)
        x, y, dpr = native_to_logical(left, top, cw, ch)
        geom = (left, top, cw, ch, dpr)
        if geom == self._last_geom:
            return
        self._last_geom = geom
        self.move(x, y)
        self._size = (cw / dpr, ch / dpr)
        self._scale = cw / (REFERENCE_W * dpr)
        self._layout()

    def _on_picture(self, left, top, cw, ch):
        """The game's picture inside its window: the server cuts off black bars
        around it (live_capture.find_picture) and says where it is, and the
        HUD sits on the picture, not on the bars (a user's HUD sat a little to
        the left of the game)."""
        pic = ((self._last_state or {}).get("capture") or {}).get("picture") or []
        if len(pic) == 4 and all(isinstance(v, int) for v in pic):
            x, y, w, h = pic
            if w > 0 and h > 0 and x + w <= cw and y + h <= ch:
                return left + x, top + y, w, h
        return left, top, cw, ch

    def _lost_game(self):
        """No game window to sit on: show nothing until it's back."""
        if self._last_geom is not None:
            self._last_geom = None
            self._place()

    # --- data ---
    def on_state(self, state):
        self._recv_t = time.monotonic()   # anything from the server, same or not (_check_health)
        # The server sends 10 a second even when nothing changes (menus, the
        # result screen): an identical one is skipped instead of laying out
        # and repainting everything again (user: make the app lighter).
        if state == self._last_raw_state:
            return
        self._last_raw_state = state
        self._record_finished_match(state)
        if state.get("session") != getattr(self, "_last_session", None):
            self._last_session = state.get("session")
            self.session_changed.emit(self._last_session)
        self._last_state = state
        self._state_t = time.monotonic()
        # Follow the server's copy only when IT changes (someone edited the
        # file): a change made in the settings window is applied here at once,
        # and the server's copy lags it by up to ~1s — applying that stale copy
        # would flick the display back for a moment.
        server_display = state.get("display")
        if server_display and server_display != self._last_server_display:
            self._last_server_display = server_display
            if time.monotonic() >= self._local_until:
                self.apply_display(display_settings({"display": server_display}))
        # 1P / 2P only (display.players): the other side shows nothing
        self._last_state = state = mark_hidden_sides(state, self.display["players"])
        screen = state.get("match_screen")
        if screen != self._last_match_screen:
            self._last_match_screen = screen
            self.match_screen_changed.emit(screen is not False)
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
            self.stats[side].update_side(state.get(side), state.get("match_elapsed_s"))
        self.versus.update_sides(state.get("left"), state.get("right"))
        self.summary.update_match(state)
        # Dim rather than hide when capture is down: the numbers shown are the
        # last real measurement, not a fabricated live one.
        for band in (*self.stats.values(), *self.events.values(), self.versus, self.clock, self.session, self.summary,
                     *self.badges.values()):
            band.dim = stale
            band.update()
        self._place()

    def _record_finished_match(self, state):
        """A match just ended (frozen, with a winner): its openers and the
        winner go to opener_stats, for the settings window's opener stats.
        (Before display.players hides a side: both are kept.)"""
        frozen = bool(state.get("frozen"))
        was, self._was_frozen = self._was_frozen, frozen
        if not frozen or was is not False:
            return
        try:
            record = opener_stats.match_record(state)
            if record and opener_stats.add(record):
                self.opener_recorded.emit()
        except Exception:
            log_hud.exception("couldn't keep the finished match for the opener stats")

    def _place_openers(self):
        self._place_opener_parts()
        if self.reading_unsafe():
            self._keep_out_of_reading(openers=True)

    def _place_opener_parts(self):
        """The opener (開幕テンプレ) names, where display.opener_display says (see
        OpenerBadge), at their popup opacity. Ages come from the server only
        ~10 times a second, so the time since the last state is added here and
        the fade timer re-runs this every frame while a name is up — the fade
        used to step visibly (user report)."""
        s, d, st = self._scale, self.display, self._last_state
        since = time.monotonic() - self._state_t
        omode = d["opener_display"]
        key = "opener_en" if opener_language(d) == "en" else "opener"   # display.opener_language
        names = {sd: None if is_puyo(st.get(sd)) else ((st.get(sd) or {}).get(key) or (st.get(sd) or {}).get("opener"))
                 for sd in ("left", "right")}
        alphas = {sd: popup_alpha(st.get(sd), st.get("frozen"), since, d["opener_seconds"]) if names[sd] else 0.0
                  for sd in ("left", "right")}
        if self.edit_mode and d["show_opener"]:   # positioning: a sample name on both sides, to drag
            sample = UI_TEXT[d["language"]]["opener_sample"]
            names = {sd: names[sd] or sample for sd in names}
            alphas = {sd: 1.0 for sd in alphas}
        shown = {}
        if d["show_opener"] and omode == "cat":
            self._place_cats(names, st, since)
            for badge in self.badges.values():
                badge.setVisible(False)
            return
        for c in self.cats.values():
            c.setVisible(False)
        if d["show_opener"] and omode == "top":
            # one box for both: up while either name is still within its few seconds
            if max(alphas.values()) > 0:
                shown["both"] = max(alphas.values())
        elif d["show_opener"]:
            shown = {sd: a for sd, a in alphas.items() if a > 0}
        for key, badge in self.badges.items():
            if key not in shown:
                badge.setVisible(False)
                continue
            badge.set_names(names, shown[key])
            badge.setVisible(True)
            if key == "both":
                x, y = OPENER_TOP_CENTER_X * s - badge.width() / 2, OPENER_TOP_Y * s
            elif omode == "board":
                x, y = BOARD_CENTER_X[key] * s - badge.width() / 2, OPENER_BOARD_TOP_Y * s
            elif omode == "hold":     # right edge under the HOLD box, growing away from the board
                x, y = HOLD_RIGHT_X[key] * s - badge.width(), OPENER_HOLD_TOP_Y * s
            else:                     # namebar: at the end of the bar away from the avatar
                x = (NAMEBAR_RIGHT_X * s - badge.width()) if key == "left" else NAMEBAR_LEFT_X * s
                y = NAMEBAR_TOP_Y * s
            dx, dy = opener_offset(d, key)
            badge.move(int(x + dx * s), int(y + dy * s))
        if shown and not self._fade.isActive():
            self._fade.start()
        elif not shown:
            self._fade.stop()

    def _place_cats(self, names, st, since):
        """display.opener_display = "cat": each player's cat, at its frame."""
        if self._cat is None:
            self._cat = load_cat() or False
        any_up = False
        now = time.monotonic()
        for sd, cat_w in self.cats.items():
            age = (st.get(sd) or {}).get("opener_age_s")
            pos = None
            if self._cat and self.edit_mode:   # positioning: the cat holding the paper up, to drag
                mid = (self._cat.get("still_start", self._cat["hold_start"]) + self._cat.get("still_end", self._cat["hold_end"])) // 2
                pos = (mid, mid, 0.0)
            elif self._cat and names[sd] and age is not None and not st.get("frozen"):
                server_age = age + since
                start = self._cat_start[sd]
                u = self._scale * CAT_SCALE * part_value(self.display, "opener", "scale")
                if start is None or self._cat_name[sd] != names[sd]:   # a new popup: which cat
                    self._cat_clip[sd] = self._pick_clip(st, sd, names[sd], cat_w, u)
                # a new opener, or this PC's clock and the server's drifted apart: start over from the server's age
                if start is None or self._cat_name[sd] != names[sd] or abs((now - start) - server_age) > 0.35:
                    self._cat_start[sd], self._cat_name[sd] = now - server_age, names[sd]
                pos = cat_pos(self._clip(sd), now - self._cat_start[sd], self.display["opener_seconds"])
            if pos is None:
                cat_w.setVisible(False)
                self._cat_start[sd] = None
                self._done_with_clip(sd)
                continue
            clip = self._clip(sd) if not self.edit_mode else self._cat
            u = self._scale * CAT_SCALE * part_value(self.display, "opener", "scale")
            cat_w.show_frame(clip, pos, names[sd], u)
            w, h = clip["size"][0] * u, clip["size"][1] * u
            x = CAT_CENTER_X[sd] * self._scale - w / 2   # its middle over the board (see CAT_CENTER_X)
            dx, dy = opener_offset(self.display, sd)
            s = self._scale
            cat_w.move(int(x + dx * s), int(CAT_BOTTOM_Y * s - h + dy * s))
            cat_w.setVisible(True)
            cat_w.raise_()
            any_up = True
        if any_up and not self._fade.isActive():
            self._fade.start()
        elif not any_up:
            self._fade.stop()

    def _clip(self, sd):
        return self._cat2 if self._cat_clip[sd] == "cat2" and self._cat2 else self._cat

    def _pick_clip(self, st, sd, name, cat_w, u):
        """The clip for a new popup; the second one's frames start being
        prepared now, ahead of where it's shown (CatPopup.prepare)."""
        if pick_cat_clip(st, sd, name) != "cat2":
            if self._cat:
                cat_w.prepare(self._cat, u)
            return "cat"
        if self._cat2 is None:
            self._cat2 = load_cat("cat2") or False
        if not self._cat2:
            return "cat"
        cat_w.prepare(self._cat2, u)
        return "cat2"

    def _done_with_clip(self, sd):
        """A popup ended: the second clip's frames are let go once no side
        plays it (it's one in CAT2_EVERY: not kept in memory between)."""
        if self._cat_clip[sd] == "cat2":
            self._cat_clip[sd] = None
            if "cat2" not in self._cat_clip.values() and "cat2" in CAT_FRAMES:
                CAT_FRAMES["cat2"].clear()
                if self._cat:   # its popup prepares the usual clip again (already kept: no work)
                    self.cats[sd].prepare(self._cat, self._scale * CAT_SCALE * part_value(self.display, "opener", "scale"))

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
        for c in self.cats.values():
            c.set_editing(on)
        for band in (*self.stats.values(), *self.events.values(), self.versus, self.clock, self.session, self.summary,
                     *self.badges.values()):
            band.editing = on
            band.setCursor(QtCore.Qt.CursorShape.SizeAllCursor if on else QtCore.Qt.CursorShape.ArrowCursor)
            band.update()
        self.edit_hint.setVisible(on)
        if on:
            self.edit_hint.setText(UI_TEXT[self.display["language"]][
                "edit_hint_zones" if self.reading_unsafe() else "edit_hint"])
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

    def wheel_resize(self, target, delta):
        """The wheel over a part while positioning: that part's size, a step a
        notch (user: change the size easily on the game screen too)."""
        if not delta:
            return
        part = TARGET_PART[target]
        lo, hi = DISPLAY_RANGES["scale"]
        size = part_value(self.display, part, "scale") + WHEEL_SCALE_STEP * (1 if delta > 0 else -1)
        size = round(min(max(size, lo), hi), 2)
        parts = {p: dict(v) for p, v in self.display["parts"].items()}
        parts.setdefault(part, {})["scale"] = size
        self.apply_display(display_settings({"display": {**self.display, "parts": parts}}), local=True)
        self.part_resized.emit(part, size)

    def set_drag_targets(self):
        """display.drag_each_side: dragging moves just that player's numbers /
        opener name, else both players' together."""
        each = self.display["drag_each_side"]
        for side, stat in self.stats.items():
            stat.drag_target = f"stats_{side}" if each else "stats"
        for side, w in (*self.badges.items(), *self.cats.items()):
            w.drag_target = f"opener_{side}" if each and side in ("left", "right") else "opener"

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
        ex_style |= WS_EX_NOACTIVATE   # clicking it (while dragging parts) never takes the game's focus
        if enabled:
            ex_style |= win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT
        else:
            ex_style &= ~win32con.WS_EX_TRANSPARENT
            ex_style |= win32con.WS_EX_LAYERED
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)

    def hide_from_capture(self):
        """Keeps the HUD out of screen captures (the recognition's included),
        and notes whether Windows really did (self.capture_excluded): an old
        Windows 10 can't, and then the recognition saw the HUD over the game —
        the numbers over where T-SPIN banners show (a user's T-SPINs all went
        uncounted). The server then reads the game's own window instead."""
        self._want_excluded = True
        hwnd = int(self.winId())
        ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        got = ctypes.c_uint32(0)
        ok = ctypes.windll.user32.GetWindowDisplayAffinity(hwnd, ctypes.byref(got))
        self.capture_excluded = bool(ok) and got.value == WDA_EXCLUDEFROMCAPTURE


# The app's icon (user's pick from the drafts): a T piece at the lower left
# and a bar chart (1P blue / white / 2P red) at the upper right, on a dark
# rounded tile. Sizes are shares of the icon's side. Also written to
# assets/app.ico by tools/make_icon.py (the desktop shortcut's icon).
ICON_TILE = "#151a2e"
ICON_BARS = (("#ffffff", 0.324), ("#3b8eea", 0.567), ("#e5484d", 0.4455))   # color, height (white, blue, red: user's pick)
ICON_BAR_W, ICON_BAR_GAP, ICON_BAR_RIGHT, ICON_BAR_BOTTOM = 0.162, 0.04725, 0.92, 0.647
ICON_T = "#a855f7"
ICON_T_CELL, ICON_T_GAP, ICON_T_X, ICON_T_Y = 0.18, 0.015, 0.08, 0.545
ICON_OFF = {"#3b8eea": "#52525b", "#ffffff": "#71717a", "#e5484d": "#52525b", "#a855f7": "#71717a"}   # switched off


def draw_app_icon(p, size, enabled=True):
    """Paints the icon into a size x size square (greyed out while off)."""
    col = (lambda c: QtGui.QColor(c)) if enabled else (lambda c: QtGui.QColor(ICON_OFF.get(c, c)))
    s = float(size)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.setBrush(QtGui.QColor(ICON_TILE))
    p.drawRoundedRect(QtCore.QRectF(0, 0, s, s), s * 0.22, s * 0.22)
    x = ICON_BAR_RIGHT - 3 * ICON_BAR_W - 2 * ICON_BAR_GAP
    for color, h in ICON_BARS:
        p.setBrush(col(color))
        p.drawRoundedRect(QtCore.QRectF(s * x, s * (ICON_BAR_BOTTOM - h), s * ICON_BAR_W, s * h), s * 0.035, s * 0.035)
        x += ICON_BAR_W + ICON_BAR_GAP
    u, g = ICON_T_CELL, ICON_T_GAP
    cells = [(0, 0), (1, 0), (2, 0), (1, 1)]
    for rim, grow, r in ((True, 0.02, 0.25), (False, 0.0, 0.18)):   # a dark rim, then the cells
        p.setBrush(QtGui.QColor(ICON_TILE) if rim else col(ICON_T))
        for cx, cy in cells:
            rect = QtCore.QRectF(s * (ICON_T_X + cx * (u + g) - grow), s * (ICON_T_Y + cy * (u + g) - grow),
                                 s * (u + 2 * grow), s * (u + 2 * grow))
            p.drawRoundedRect(rect, s * u * r, s * u * r)


def icon_image(size, enabled=True):
    img = QtGui.QImage(size, size, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QtGui.QPainter(img)
    draw_app_icon(p, size, enabled)
    p.end()
    return img


def make_tray_icon(enabled=True):
    """The app icon at the sizes Windows asks for (tray, title bars, taskbar),
    each drawn at its own size so the small ones stay sharp."""
    icon = QtGui.QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(QtGui.QPixmap.fromImage(icon_image(size, enabled)))
    return icon


# One copy at a time: starting it again (the desktop shortcut while it's
# already running) just opens the running copy's settings window, instead of
# a second HUD on top of the first.
INSTANCE_KEY = "PPTetrics-hud"


def already_running():
    """True if another copy is running (and has been asked to show its settings)."""
    sock = QtNetwork.QLocalSocket()
    sock.connectToServer(INSTANCE_KEY)
    if sock.waitForConnected(300):
        sock.write(b"show")
        sock.waitForBytesWritten(300)
        sock.disconnectFromServer()
        return True
    return False


_READ_ZONES = None
EDIT_YELLOW, EDIT_RED = "#fde047", "#ef4444"


def edit_color(widget):
    """A part's outline while positioning: red when it sits over what the
    recognition reads on a PC where the HUD shows in captures (it then stays
    off the game screen), else yellow."""
    return EDIT_RED if getattr(widget, "blocked", False) else EDIT_YELLOW


class ReadZonesLayer(QtWidgets.QWidget):
    """While positioning, on a PC where the HUD shows in screen captures:
    what the recognition reads (read_zones), shaded red under the parts, so
    it's clear where a part can go and still show on the game screen."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.scale = 1.0
        self.setVisible(False)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        fill = QtGui.QColor(EDIT_RED)
        fill.setAlpha(60)
        edge = QtGui.QColor(EDIT_RED)
        edge.setAlpha(170)
        p.setPen(QtGui.QPen(edge, 1))
        p.setBrush(fill)
        s = self.scale
        for x1, y1, x2, y2 in read_zones():
            p.drawRect(QtCore.QRectF(x1 * s, y1 * s, (x2 - x1) * s, (y2 - y1) * s))
        p.end()


def read_zones():
    """Where the recognition reads the game screen (reference 1232x692
    coordinates, both players): the boards, the T-SPIN / TETRIS / PERFECT
    CLEAR banners, NEXT and HOLD, GO! and the victory
    banner. Taken from the recognition's own constants."""
    global _READ_ZONES
    if _READ_ZONES is None:
        import banner_detect
        import board_read
        import gameplay_gate
        import hold_tracker
        import match_boundary
        zones = [board_read.LEFT_BOX, board_read.RIGHT_BOX, match_boundary.GO_REGION,
                 match_boundary.YATTA_WINDOW_LEFT, match_boundary.YATTA_WINDOW_RIGHT,
                 *hold_tracker.HOLD_ICON_BOXES.values()]
        for x1, y1, x2, _ in gameplay_gate.NEXT_WINDOWS.values():   # the label and the 5 pieces under it
            zones.append((x1, y1, x2, y1 + 330))
        # (not BACK to BACK's or the REN digits': they're only noted, nothing
        # is counted from them, and their wide windows reach the middle)
        for label, cfg in banner_detect.TEMPLATES.items():
            if label == "back_to_back" or label in banner_detect.REN_LABELS:
                continue
            for side in ("left", "right"):
                zones.append(banner_detect.window_for_side(label, cfg["window"], side))
        _READ_ZONES = [tuple(z) for z in zones]
    return _READ_ZONES


def native_to_logical(left, top, width, height, screens=None):
    """Where a window at these screen pixels goes in Qt's coordinates, and the
    scaling of the monitor it's on. Qt keeps each monitor's top-left in screen
    pixels and scales only within it, so the monitor under the game decides
    (it used the HUD's own monitor and divided the whole position by its
    scaling: on a second monitor, or after the game moved to one with other
    scaling, the HUD went somewhere else, even off screen)."""
    cx, cy = left + width / 2, top + height / 2
    screens = QtGui.QGuiApplication.screens() if screens is None else screens
    for sc in screens:
        g, r = sc.geometry(), sc.devicePixelRatio()
        if g.x() <= cx < g.x() + g.width() * r and g.y() <= cy < g.y() + g.height() * r:
            return int(g.x() + (left - g.x()) / r), int(g.y() + (top - g.y()) / r), r
    r = screens[0].devicePixelRatio() if screens else 1.0
    return int(left / r), int(top / r), r


def _hud_note(text):
    """One line in logs/hud.log (the HUD's own record; see _check_health)."""
    try:
        logs = ROOT_DIR / "logs"
        logs.mkdir(exist_ok=True)
        path = logs / "hud.log"
        if path.exists() and path.stat().st_size > 2 * 1024 * 1024:   # keep it small
            path.replace(logs / "hud.log.1")
        with open(path, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n")
    except OSError:
        pass


def log_errors():
    """An unhandled Python exception in a paint, timer or signal handler makes
    PyQt6 end the whole app (user: it closed as an opener name came up; Windows
    logged a fail-fast in Qt6Core). With our own hook PyQt only reports it:
    it's written to logs/hud.log with the time and the app keeps running.
    Native crashes go to logs/hud_crash.log (faulthandler)."""
    import faulthandler
    import traceback
    logs = ROOT_DIR / "logs"
    logs.mkdir(exist_ok=True)
    try:
        faulthandler.enable(open(logs / "hud_crash.log", "a", encoding="utf-8"))
    except OSError:
        pass

    def hook(kind, value, tb):
        try:
            with open(logs / "hud.log", "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + "".join(traceback.format_exception(kind, value, tb)) + "\n")
        except OSError:
            pass
    sys.excepthook = hook


def main():
    from settings_window import SettingsWindow

    log_errors()
    settings = load_settings()
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(make_tray_icon())   # the settings window's title bar and taskbar button
    if already_running():
        sys.exit(0)
    QtNetwork.QLocalServer.removeServer(INSTANCE_KEY)   # left over from a copy that didn't close cleanly
    instance = QtNetwork.QLocalServer(app)
    instance.listen(INSTANCE_KEY)
    app.setQuitOnLastWindowClosed(False)  # closing the settings window keeps the HUD
    win = HudWindow(settings)
    app.aboutToQuit.connect(win.ws_client.stop)
    if settings["hud"]["visible"]:
        win.show()
        # These need the native window handle, which exists only after show().
        # Click-through matters even more now: the window covers the whole game.
        win.apply_click_through(settings["hud"]["click_through"])
        if settings["hud"]["hide_from_capture"]:
            win.hide_from_capture()

    settings_win = SettingsWindow(drag_available=True)
    settings_win.display_changed.connect(lambda d: win.apply_display(d, local=True))
    settings_win.edit_mode_changed.connect(win.set_edit_mode)
    win.offset_dragged.connect(settings_win.set_offset_from_hud)
    win.part_resized.connect(settings_win.set_part_scale_from_hud)
    win.match_screen_changed.connect(settings_win.set_match_screen)
    win.opener_recorded.connect(settings_win.refresh_opener_stats)   # the opener stats follow each match
    win.session_changed.connect(settings_win.set_today)              # 今日の成績 on the stats page
    win.reading_overlap.connect(settings_win.set_reading_overlap)    # why some parts aren't on the game screen

    tray = QtWidgets.QSystemTrayIcon(make_tray_icon(), app)
    tray.setToolTip("PPTetrics")
    menu = QtWidgets.QMenu()
    # the on/off switch, first in the menu (also at the top of the settings window)
    act_enabled = menu.addAction("")
    act_enabled.setCheckable(True)
    act_enabled.setChecked(win.display["enabled"])
    act_enabled.toggled.connect(settings_win.set_enabled)
    # where it shows: over the game / in OBS, each on its own
    act_hud = menu.addAction("")
    act_hud.setCheckable(True)
    act_hud.toggled.connect(lambda on: settings_win.set_shown_on("show_on_hud", on))
    act_obs = menu.addAction("")
    act_obs.setCheckable(True)
    act_obs.toggled.connect(lambda on: settings_win.set_shown_on("show_on_obs", on))
    menu.addSeparator()
    act_settings = menu.addAction("", settings_win.open)
    # for "the numbers don't move" reports: logs/ has what the recognition saw
    # (last_seen.jpg, last_status.txt) and server.log (scripts/diagnostic.py)
    act_logs = menu.addAction("", lambda: QtGui.QDesktopServices.openUrl(
        QtCore.QUrl.fromLocalFile(str(ROOT_DIR / "logs"))))
    menu.addSeparator()
    act_quit = menu.addAction("", app.quit)
    tray.setContextMenu(menu)

    def show_enabled(d):
        on = d["enabled"]
        for act, value in ((act_enabled, on), (act_hud, d["show_on_hud"]), (act_obs, d["show_on_obs"])):
            if act.isChecked() != value:
                act.blockSignals(True)
                act.setChecked(value)
                act.blockSignals(False)
            if act is not act_enabled:
                act.setEnabled(on)
        tray.setIcon(make_tray_icon(on))
        tray.setToolTip("PPTetrics" + ("" if on else ("（オフ）" if d["language"] != "en" else " (off)")))
    settings_win.display_changed.connect(show_enabled)
    show_enabled(win.display)

    def tray_language(lang):
        act_enabled.setText("Show the overlay" if lang == "en" else "表示する（オン／オフ）")
        act_hud.setText("    On the game screen" if lang == "en" else "    ゲーム画面に表示")
        act_obs.setText("    In OBS" if lang == "en" else "    OBS に表示")
        act_settings.setText("Display settings…" if lang == "en" else "表示設定…")
        act_logs.setText("Open the troubleshooting files…" if lang == "en" else "うまく認識しないとき：診断ファイルを開く…")
        act_quit.setText("Quit" if lang == "en" else "終了")
    tray_language(win.display["language"])
    win.language_changed.connect(tray_language)
    tray.activated.connect(lambda reason: settings_win.open()
                           if reason == QtWidgets.QSystemTrayIcon.ActivationReason.DoubleClick else None)
    tray.show()
    # A newer version (scripts/updater.py): said by a notification, which
    # doesn't take the focus; clicking it opens the settings on the update tab.
    def update_found(info):
        ja = win.display["language"] != "en"
        tray.showMessage("PPTetrics",
                         f"新しい版 v{info['version']} があります。ここをクリックして更新できます。" if ja else
                         f"Version v{info['version']} is available. Click here to update.",
                         QtWidgets.QSystemTrayIcon.MessageIcon.Information, 10000)
    settings_win.update_available.connect(update_found)
    # started again while running: open the settings (the person clicked the shortcut)
    instance.newConnection.connect(lambda: (instance.nextPendingConnection(), settings_win.open()))
    tray.messageClicked.connect(lambda: settings_win.show_update_tab() if settings_win._update_info else None)
    if settings.get("update", {}).get("check_on_start", True):
        settings_win.check_for_update(silent=True)
    # Open the settings right away, so someone launching the tool sees where to
    # change things (closing it keeps the HUD) — but not while the game is
    # running: a new window takes the keyboard focus, and the game pauses
    # itself when it loses focus (user report: a window flashed, the game
    # stopped taking input and paused). Then a notification (which doesn't
    # take the focus) says where the settings are.
    game_running = HAS_WIN32 and find_game_hwnd() is not None
    if game_running:
        ja = win.display["language"] != "en"
        tray.showMessage("PPTetrics",
                         "起動しました。設定はタスクバー右下のアイコンから開けます。" if ja else
                         "Running. Open the settings from the tray icon (bottom right of the taskbar).",
                         QtWidgets.QSystemTrayIcon.MessageIcon.Information, 5000)
    else:
        settings_win.open()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
