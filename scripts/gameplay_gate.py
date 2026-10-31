"""Tells whether the in-match screen is actually showing, so nothing is
counted on menus, dialogs, loading wipes or the pause screen.

Without this, frames kept flowing into recognition between matches and the
board-empty fallback read menu artwork as "pieces reappeared -> new match",
after which flash/row detection turned menu graphics into fake clears
(confirmed live: a fake right-side 3-line clear on the "プレイセレクト" dialog,
a fake left-side 3-line clear on the white loading wipe before a match).

Two checks, both on match UI chrome rather than stage artwork (the stage
background changes every match):

1. The "NEXT" label box above each player's next-piece queue is visible.
   In-match 0.93-0.94 on both sides across four different stages; every
   menu, dialog and wipe frame from a live session scored 0.42 or less.
   Either side counts: the HUD overlay sits top-left in the same screen
   capture and its log text can grow wide enough to approach the left label.

2. That side's NEXT queue actually holds pieces. The pause screen keeps both
   NEXT labels (greyed out) but empties every queue slot — confirmed on a
   live pause frame and on a 48s pause inside an earlier recording, two
   different stages. Colored-pixel ratio per slot: 0.25-0.42 during play on
   four stages, 0.00 in every slot while paused. The left queue is partly
   covered by the "ポーズ" text, so a pause is "every slot empty on EITHER
   side" (the right one is always clean). Without this the pause screen
   counted as gameplay: numbers kept running, and the TETRIS template
   matched the pause fade-in as a fake right-side TETRIS.
"""
from pathlib import Path

import cv2

from capture_profile import scale_box, scale_template, REFERENCE_PROFILE

SCRIPTS_DIR = Path(__file__).resolve().parent
NEXT_TEMPLATE_PATH = SCRIPTS_DIR / ".." / "assets" / "templates" / "t_next_label.png"

# Reference-resolution (1232x692) search windows, with margin around each label.
NEXT_WINDOWS = {"left": (430, 60, 545, 125), "right": (1035, 60, 1150, 125)}
ON_SCREEN_THRESHOLD = 0.7

# Queue slot interiors, relative to the matched NEXT label's top-left corner
# (reference px, x1/y1/x2/y2): the first slot shares the label's box, the
# other four are the smaller boxes stacked below it.
QUEUE_SLOTS = [(0, 22, 52, 50), (-2, 70, 50, 102), (-2, 120, 50, 152), (-2, 170, 50, 202), (-2, 220, 50, 252)]
SLOT_EMPTY_RATIO = 0.05  # colored-pixel ratio below which a slot holds no piece

# The English game's pause menu covers the left queue with its bright buttons,
# so with a Puyo opponent (no right queue to look at) the pause went unseen
# (user report). Its "Start Over" / "Quit Game" buttons (either: the cursor
# highlights one at a time) score 1.0 while paused (debug_frames/burst_english*)
# and <= 0.46 on every other frame of every recording.
PAUSE_TEMPLATE_PATHS = [SCRIPTS_DIR / ".." / "assets" / "templates" / n
                        for n in ("t_pause_en_start_over.png", "t_pause_en_quit_game.png")]
PAUSE_WINDOW = (470, 270, 770, 600)
PAUSE_THRESHOLD = 0.75


class GameplayGate:
    def __init__(self, profile=None):
        self.profile = profile or REFERENCE_PROFILE
        tmpl = cv2.imread(str(NEXT_TEMPLATE_PATH))
        if tmpl is None:
            raise FileNotFoundError(f"NEXT label template not found: {NEXT_TEMPLATE_PATH}")
        self.template = scale_template(tmpl, self.profile)
        self.windows = {side: scale_box(box, self.profile) for side, box in NEXT_WINDOWS.items()}
        self.slots = [tuple(int(round(v * self.profile.scale_x)) for v in s) for s in QUEUE_SLOTS]
        self._pause_raw = [cv2.imread(str(p)) for p in PAUSE_TEMPLATE_PATHS]   # kept: see scale_template
        self.pause_templates = [scale_template(t, self.profile) for t in self._pause_raw if t is not None]
        self.pause_window = scale_box(PAUSE_WINDOW, self.profile)
        self.last_scores = {}
        self.last_reason = None  # None (match screen), "no_match_ui" or "pause"

    def _queue_empty(self, hsv, lx, ly):
        h, w = hsv.shape[:2]
        for a, b, c, d in self.slots:
            x1, y1, x2, y2 = max(0, lx + a), max(0, ly + b), min(w, lx + c), min(h, ly + d)
            reg = hsv[y1:y2, x1:x2]
            if reg.size and ((reg[..., 1] > 120) & (reg[..., 2] > 120)).mean() >= SLOT_EMPTY_RATIO:
                return False
        return True

    def _pause_menu(self, frame):
        x1, y1, x2, y2 = self.pause_window
        region = frame[y1:y2, x1:x2]
        for t in self.pause_templates:
            if region.shape[0] >= t.shape[0] and region.shape[1] >= t.shape[1] and                     cv2.matchTemplate(region, t, cv2.TM_CCOEFF_NORMED).max() >= PAUSE_THRESHOLD:
                return True
        return False

    def update(self, frame):
        th, tw = self.template.shape[:2]
        found = {}
        for side, (x1, y1, x2, y2) in self.windows.items():
            region = frame[y1:y2, x1:x2]
            if region.shape[0] < th or region.shape[1] < tw:
                self.last_scores[side] = 0.0
                continue
            res = cv2.matchTemplate(region, self.template, cv2.TM_CCOEFF_NORMED)
            _, score, _, (mx, my) = cv2.minMaxLoc(res)
            self.last_scores[side] = float(score)
            if score >= ON_SCREEN_THRESHOLD:
                found[side] = (x1 + mx, y1 + my)
        if not found:
            self.last_reason = "no_match_ui"
            return False
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        # the pause menu is only looked for with one NEXT queue on screen (a Puyo
        # opponent): with two, the clean right queue already shows a pause, and
        # the menu check costs ~14 ms a frame
        if any(self._queue_empty(hsv, lx, ly) for lx, ly in found.values()) or                 (len(found) == 1 and self._pause_menu(frame)):
            self.last_reason = "pause"
            return False
        self.last_reason = None
        return True
