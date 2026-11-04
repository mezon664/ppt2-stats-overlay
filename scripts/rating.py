"""Online rating (パズルリーグ レート) history (user's request: see how the
rating moves).

The rating is read off two screens (debug_frames/burst_rating):
  - まちうけ, before each match: both players' cards, "You" on yours (left
    when you're 1P, right when you're 2P), the rating in a box on each card
  - the パズルリーグ menu: your card, "レート" and the number beside it
The number is read with Windows' own text recognition (Windows.Media.Ocr):
the game's digits 3 and 9 never showed in the recordings, so templates
couldn't cover every digit. Read only off the match screen, about once a
second; a value counts once it was read the same twice in a row.

Each league has its own rating (user: see them per league). The まちうけ
screen doesn't say which league it is, so a rating counts for the league whose
menu was last on screen (its title, top left: LEAGUE_TITLES; all four from
debug_frames/burst_rating and burst_leagues — each scores 1.0 on its own menu,
0.56 at most on another's). A league whose title isn't known (a new one, a
changed screen): on its menu the league becomes unknown, and ratings read
while no league is known aren't kept (not put down as the league seen before).

A rating is kept when it differs from that league's last kept one: going to
the まちうけ screen, back and there again keeps it once, and the same number
in another league is that league's own point (user's request).

Each new value goes to config/rating_history.json (the newest KEEP per
league), shown by the settings window's レート page.
"""
import asyncio
import json
import logging
import time
from pathlib import Path

import cv2
import numpy as np

from image_io import read_image

log = logging.getLogger("rating")
ROOT = Path(__file__).resolve().parent.parent
# Windows text recognition's Python parts ship in vendor/ (tools/make_release.py);
# a development copy has them in its .venv. Added last: an installed one wins.
_VENDOR = ROOT / "vendor"
if _VENDOR.is_dir() and str(_VENDOR) not in __import__("sys").path:
    __import__("sys").path.append(str(_VENDOR))
HISTORY_PATH = ROOT / "config" / "rating_history.json"
TEMPLATES = ROOT / "assets" / "templates"
KEEP = 1000
READ_EVERY_S = 1.0
# One match moves the rating by about 40 at most (user). So while the app runs,
# a number this far from the one read before in this run, or with another
# count of digits (2633 -> 263: a window over its last digit, user report),
# counts only after UNLIKELY_READS reads in a row. Not against the history:
# opened again after matches played without it, the rating may have moved a
# lot, and that must show at once (user).
UNLIKELY_STEP = 60
UNLIKELY_READS = 10
DIGITS_CHANGE_READS = UNLIKELY_READS   # (the older name)

# Places on a 1320-wide game window (any 16:9 size is scaled from it)
BASE_W = 1320
YOU = {   # where "You" shows on your card, and your rating box then
    "left": {"tmpl": "rating_you_left.png", "near": (575, 160, 680, 225), "box": (420, 379, 505, 403)},
    "right": {"tmpl": "rating_you_right.png", "near": (620, 445, 725, 510), "box": (1140, 177, 1225, 201)},
}
MENU = {"tmpl": "rating_menu_label.png", "near": (1040, 268, 1145, 322), "box": (1140, 282, 1228, 310)}
# each league's menu title, top left (order = the settings window's)
LEAGUES = ("puzzle", "tetris", "puyo", "skill")
LEAGUE_TITLES = {league: f"rating_league_{league}.png" for league in LEAGUES}
TITLE_NEAR = (20, 40, 340, 150)
# A club room ("ルーム" top left, like the league menus' titles; also on
# ルームをつくる / ルームセレクト): no league is being played, so the league
# is forgotten — a club match's pre-match card shows the パズルリーグ rating
# (2633 in debug_frames/burst_club), which must not go down as the league
# whose menu was seen before (user: club matches shouldn't move the history).
# 0.998 on the club room, 0.33 at most on burst_rating / burst_leagues.
CLUB_TITLE = "rating_title_club.png"
MATCH_MIN = 0.80


def _scale(box, k):
    return tuple(int(round(v * k)) for v in box)


class RatingReader:
    def __init__(self):
        self._tmpl = {}
        for key, spec in (("left", YOU["left"]), ("right", YOU["right"]), ("menu", MENU)):
            img = read_image(TEMPLATES / spec["tmpl"])
            if img is not None:
                self._tmpl[key] = img
        self._titles = {}
        for league, name in LEAGUE_TITLES.items():
            img = read_image(TEMPLATES / name)
            if img is not None:
                self._titles[league] = img
        self._club = read_image(TEMPLATES / CLUB_TITLE)
        self._engine = None
        self._engine_tried = False
        self._last_t = 0.0
        self._pending = None   # (league, value) read before, waiting to be read again
        self._pending_n = 0    # how many times in a row
        self.league = None     # the league whose menu was last on screen
        self.last_value = {}   # league -> the last value kept (from the history too: not kept twice)
        self.session_value = {}   # league -> the last value read in this run (UNLIKELY_STEP)

    # --- where's my rating on this screen? ---
    def _found(self, frame, key, spec, k):
        tmpl = self._tmpl.get(key)
        if tmpl is None:
            return False
        if k != 1.0:
            tmpl = cv2.resize(tmpl, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
        x1, y1, x2, y2 = _scale(spec["near"], k)
        region = frame[max(0, y1):y2, max(0, x1):x2]
        if region.shape[0] < tmpl.shape[0] or region.shape[1] < tmpl.shape[1]:
            return False
        score = cv2.minMaxLoc(cv2.matchTemplate(region, tmpl, cv2.TM_CCOEFF_NORMED))[1]
        return score >= MATCH_MIN

    def league_on_screen(self, frame):
        """The league whose menu this is (its title top left), or None."""
        k = frame.shape[1] / BASE_W
        x1, y1, x2, y2 = _scale(TITLE_NEAR, k)
        region = frame[max(0, y1):y2, max(0, x1):x2]
        best, best_score = None, MATCH_MIN
        for league, tmpl in self._titles.items():
            if k != 1.0:
                tmpl = cv2.resize(tmpl, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)
            if region.shape[0] < tmpl.shape[0] or region.shape[1] < tmpl.shape[1]:
                continue
            score = cv2.minMaxLoc(cv2.matchTemplate(region, tmpl, cv2.TM_CCOEFF_NORMED))[1]
            if score >= best_score:
                best, best_score = league, score
        return best

    def in_club(self, frame):
        """A club room is on screen (CLUB_TITLE)."""
        if self._club is None:
            return False
        k = frame.shape[1] / BASE_W
        tmpl = cv2.resize(self._club, None, fx=k, fy=k, interpolation=cv2.INTER_AREA) if k != 1.0 else self._club
        x1, y1, x2, y2 = _scale(TITLE_NEAR, k)
        region = frame[max(0, y1):y2, max(0, x1):x2]
        if region.shape[0] < tmpl.shape[0] or region.shape[1] < tmpl.shape[1]:
            return False
        return cv2.minMaxLoc(cv2.matchTemplate(region, tmpl, cv2.TM_CCOEFF_NORMED))[1] >= MATCH_MIN

    def own_box(self, frame):
        """The box holding your rating on this frame, or None (another screen)."""
        found = self.find(frame)
        return found[1] if found else None

    def find(self, frame):
        """("wait", box) on the まちうけ screen, ("menu", box) on a league's
        menu, or None."""
        k = frame.shape[1] / BASE_W
        for side in ("left", "right"):
            if self._found(frame, side, YOU[side], k):
                return "wait", _scale(YOU[side]["box"], k)
        if self._found(frame, "menu", MENU, k):
            return "menu", _scale(MENU["box"], k)
        return None

    # --- reading the number ---
    def _ocr_engine(self):
        if not self._engine_tried:
            self._engine_tried = True
            try:
                from winrt.windows.media.ocr import OcrEngine
                self._engine = OcrEngine.try_create_from_user_profile_languages()
                if self._engine is None:
                    langs = list(OcrEngine.available_recognizer_languages)
                    if langs:
                        self._engine = OcrEngine.try_create_from_language(langs[0])
            except Exception:
                log.warning("Windows text recognition isn't available: the rating can't be read", exc_info=True)
                self._engine = None
        return self._engine

    @staticmethod
    def prepare(crop, scale=3):
        """Dark digits on white, stretched to full contrast and `scale` times
        the size, edges kept smooth: the digits are white on the まちうけ
        cards and dark on the menu's light box. (Cut to pure black and white
        first, the live menu's 2618 read as 266 every time; kept gray, every
        one of the 159 recorded boxes and the live one read right.)"""
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        g = gray.astype(np.float32)
        if (bw == 255).mean() < 0.5:     # mostly dark: the background is dark, the digits light
            g = 255 - g
        lo, hi = np.percentile(g, 2), np.percentile(g, 98)
        g = np.clip((g - lo) * 255 / max(1.0, hi - lo), 0, 255).astype(np.uint8)
        g = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        return cv2.copyMakeBorder(g, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=255)

    def read_number(self, crop):
        """The number in the box, or None. Read at up to three sizes and
        taken once two readings agree, so one odd reading never becomes a
        rating (the recognizer now and then reads nothing, or drops a digit,
        at one particular size)."""
        engine = self._ocr_engine()
        if engine is None:
            return None
        seen = []
        for scale in (3, 4, 2):
            try:
                text = asyncio.run(self._recognize(engine, self.prepare(crop, scale)))
            except Exception:
                log.debug("rating text recognition failed", exc_info=True)
                continue
            digits = "".join(c for c in text if c.isdigit())
            if 3 <= len(digits) <= 5:
                value = int(digits)
                if value in seen:
                    return value
                seen.append(value)
        return None

    @staticmethod
    async def _recognize(engine, gray):
        from winrt.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.storage.streams import DataWriter
        bgra = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGRA)
        h, w = bgra.shape[:2]
        bmp = SoftwareBitmap(BitmapPixelFormat.BGRA8, w, h, BitmapAlphaMode.PREMULTIPLIED)
        writer = DataWriter()
        writer.write_bytes(np.ascontiguousarray(bgra).tobytes())
        bmp.copy_from_buffer(writer.detach_buffer())
        result = await engine.recognize_async(bmp)
        return result.text

    def update(self, frame, now=None, is_covered=None):
        """Looks at the frame (at most once every READ_EVERY_S): returns
        (league, rating) once your rating is read the same twice in a row and
        differs from that league's last one, else None. is_covered(box):
        True when a window lies over that box on the screen (then not read)."""
        now = time.monotonic() if now is None else now
        if now - self._last_t < READ_EVERY_S:
            return None
        self._last_t = now
        if self.in_club(frame):
            if self.league is not None:
                log.info("club room: the league is forgotten until a league menu shows again")
            self.league, self._pending = None, None
            return None
        found = self.find(frame)
        if found is not None and found[0] == "menu":
            # a league's menu: this league from now on — None for one whose
            # title isn't known yet, so its rating isn't put down as the
            # league seen before (all four menus look alike but for the title)
            self.league = self.league_on_screen(frame)
        if found is None or self.league is None:
            self._pending = None
            return None
        box = found[1]
        if is_covered is not None and is_covered(box):
            self._pending = None
            return None
        x1, y1, x2, y2 = box
        value = self.read_number(frame[y1:y2, x1:x2])
        if value is None:
            return None
        read = (self.league, value)
        if read != self._pending:
            self._pending, self._pending_n = read, 1
            return None
        self._pending_n += 1
        before = self.session_value.get(self.league)
        unlikely = before is not None and (abs(value - before) >= UNLIKELY_STEP or len(str(before)) != len(str(value)))
        if unlikely and self._pending_n < UNLIKELY_READS:
            return None
        self.session_value[self.league] = value
        if self.last_value.get(self.league) == value:
            return None
        self.last_value[self.league] = value
        return read

    def set_last(self, league, value):
        """The league's last kept rating (from the history at start-up)."""
        self.last_value[league] = value


# --- a window over the box ---
def covered(hwnd, origin, client_size, frame_size, box):
    """True when some other window lies over `box` (frame coordinates) on the
    screen: the capture takes the screen as it is, so a window over the rating
    shows instead of it (user: hiding the last digit with another window got
    263 kept). Windows that don't show in captures (this app's own, made so
    with WDA_EXCLUDEFROMCAPTURE), click-through overlays, hidden, minimized or
    cloaked ones, and the game's own windows don't count."""
    try:
        import ctypes
        import win32con
        import win32gui
        import win32process
    except Exception:
        return False
    if not hwnd or origin is None or client_size is None:
        return False
    k = client_size[0] / frame_size[0]
    x1, y1, x2, y2 = box
    left, top = origin
    rect = (left + x1 * k, top + y1 * k, left + x2 * k, top + y2 * k)
    try:
        _, game_pid = win32process.GetWindowThreadProcessId(hwnd)
    except Exception:
        return False
    user32 = ctypes.windll.user32
    dwm = ctypes.windll.dwmapi
    w = win32gui.GetWindow(hwnd, win32con.GW_HWNDPREV)   # the windows above the game, nearest first
    seen = 0
    while w and seen < 2000:
        seen += 1
        try:
            if win32gui.IsWindowVisible(w) and not win32gui.IsIconic(w):
                ex = win32gui.GetWindowLong(w, win32con.GWL_EXSTYLE)
                affinity = ctypes.c_uint(0)
                user32.GetWindowDisplayAffinity(w, ctypes.byref(affinity))
                cloaked = ctypes.c_int(0)
                dwm.DwmGetWindowAttribute(w, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))   # DWMWA_CLOAKED
                _, pid = win32process.GetWindowThreadProcessId(w)
                if not (ex & win32con.WS_EX_TRANSPARENT) and affinity.value == 0 and not cloaked.value                         and pid != game_pid:
                    bounds = (ctypes.c_long * 4)()
                    if dwm.DwmGetWindowAttribute(w, 9, ctypes.byref(bounds), ctypes.sizeof(bounds)) == 0:
                        wl, wt, wr, wb = bounds   # DWMWA_EXTENDED_FRAME_BOUNDS: without the drop shadow
                    else:
                        wl, wt, wr, wb = win32gui.GetWindowRect(w)
                    if wl < rect[2] and wr > rect[0] and wt < rect[3] and wb > rect[1]:
                        return True
        except Exception:
            pass
        w = win32gui.GetWindow(w, win32con.GW_HWNDPREV)
    return False


# --- the history ---
def load(path=None, league=None):
    """Every kept rating ({"t", "league", "rating"}, oldest first), or one league's."""
    try:
        data = json.loads(Path(path or HISTORY_PATH).read_text(encoding="utf-8"))
        points = [p for p in data.get("ratings", []) if isinstance(p, dict) and isinstance(p.get("rating"), int)
                  and p.get("league") in LEAGUES]
    except (OSError, ValueError, AttributeError):
        return []
    return points if league is None else [p for p in points if p["league"] == league]


def add(league, value, path=None, now=None):
    """Keeps a newly read rating (not again when it's that league's last one)."""
    path = Path(path or HISTORY_PATH)
    points = load(path)
    mine = [p for p in points if p["league"] == league]
    if mine and mine[-1]["rating"] == value:
        return False
    points.append({"t": round(now if now is not None else time.time()), "league": league, "rating": int(value)})
    kept = []
    for lg in LEAGUES:   # the newest KEEP of each league
        kept += [p for p in points if p["league"] == lg][-KEEP:]
    kept.sort(key=lambda p: p["t"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"ratings": kept}, indent=0), encoding="utf-8")
    tmp.replace(path)
    return True


def clear(path=None):
    path = Path(path or HISTORY_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ratings": []}), encoding="utf-8")


def has_league_template(league):
    """This league's menu can be recognized (its title template is there)."""
    return (TEMPLATES / LEAGUE_TITLES[league]).exists()
