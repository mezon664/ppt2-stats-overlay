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
menu was last on screen (its title, top left: LEAGUE_TITLES). A league whose
title template isn't there yet (only パズルリーグ was recorded so far) can't
be told apart: on its menu the league becomes unknown, and ratings read while
no league is known aren't kept (not put down as the league seen before).

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
HISTORY_PATH = ROOT / "config" / "rating_history.json"
TEMPLATES = ROOT / "assets" / "templates"
KEEP = 1000
READ_EVERY_S = 1.0

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
        self._engine = None
        self._engine_tried = False
        self._last_t = 0.0
        self._pending = None   # (league, value) read once, waiting for a second read
        self.league = None     # the league whose menu was last on screen
        self.last_value = {}   # league -> the last value kept

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
    def prepare(crop):
        """Black digits on white, three times the size: the digits are white
        on the まちうけ cards and dark on the menu's light box."""
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if (bw == 255).mean() < 0.5:     # mostly dark: the background is dark, the digits light
            bw = 255 - bw
        bw = cv2.resize(bw, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        return cv2.copyMakeBorder(bw, 24, 24, 24, 24, cv2.BORDER_CONSTANT, value=255)

    def read_number(self, crop):
        engine = self._ocr_engine()
        if engine is None:
            return None
        try:
            text = asyncio.run(self._recognize(engine, self.prepare(crop)))
        except Exception:
            log.debug("rating text recognition failed", exc_info=True)
            return None
        digits = "".join(c for c in text if c.isdigit())
        if not 3 <= len(digits) <= 5:
            return None
        return int(digits)

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

    def update(self, frame, now=None):
        """Looks at the frame (at most once every READ_EVERY_S): returns
        (league, rating) once your rating is read the same twice in a row and
        differs from that league's last one, else None."""
        now = time.monotonic() if now is None else now
        if now - self._last_t < READ_EVERY_S:
            return None
        self._last_t = now
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
        x1, y1, x2, y2 = box
        value = self.read_number(frame[y1:y2, x1:x2])
        if value is None:
            return None
        read = (self.league, value)
        if read != self._pending:
            self._pending = read
            return None
        if self.last_value.get(self.league) == value:
            return None
        self.last_value[self.league] = value
        return read


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
