"""A side playing Puyo Puyo: found from its missing NEXT label (debounced),
not read at all, and hidden on the HUD (user's request)."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hud"))

import cv2
import pytest
from PyQt6 import QtWidgets

import live_pipeline as lp
from capture_profile import compute_profile
from gameplay_gate import GameplayGate, ON_SCREEN_THRESHOLD

FIXTURES = Path(__file__).resolve().parent / "fixtures"
APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.mark.parametrize("fixture,puyo,tetris", [("puyo_right.jpg", "right", "left"),
                                                 ("puyo_left.jpg", "left", "right")])
def test_puyo_side_has_no_next_label(fixture, puyo, tetris):
    frame = cv2.imread(str(FIXTURES / fixture))
    h, w = frame.shape[:2]
    gate = GameplayGate(profile=compute_profile(w, h))
    assert gate.update(frame)   # still the match screen (the Tetris side's label)
    assert gate.last_scores[puyo] < 0.5
    assert gate.last_scores[tetris] >= ON_SCREEN_THRESHOLD


class ScoreGate:
    """Always on the match screen, with NEXT label scores the test sets."""
    def __init__(self):
        self.last_scores = {"left": 0.95, "right": 0.95}
        self.last_reason = None
        self.open = True

    def update(self, frame):
        return self.open


def feed(mp, gate, times, right_score):
    for t in times:
        gate.last_scores["right"] = right_score
        mp._update_puyo(t)


def test_needs_half_a_second_without_the_label():
    gate = ScoreGate()
    mp = lp.MatchPipeline(gate=gate)
    feed(mp, gate, [0.0, 0.1, 0.2, 0.3], 0.19)          # a 0.3s dip (an effect passing over)
    assert mp.puyo == {"left": False, "right": False}
    feed(mp, gate, [0.4], 0.95)                          # label back: the dip is forgotten
    feed(mp, gate, [0.5, 0.7, 0.9], 0.3)
    assert not mp.puyo["right"]
    old = mp.right
    feed(mp, gate, [1.0], 0.3)                           # 0.5s without it
    assert mp.puyo == {"left": False, "right": True}
    assert mp.right is not old                           # starts over: nothing counted while unsure
    snap = mp.snapshot()
    assert snap["right"]["puyo"] is True and snap["left"]["puyo"] is False


def test_back_to_tetris_after_a_second_of_label():
    gate = ScoreGate()
    mp = lp.MatchPipeline(gate=gate)
    feed(mp, gate, [i * 0.2 for i in range(12)], 0.3)
    assert mp.puyo["right"]
    feed(mp, gate, [3.0, 3.5], 0.95)
    assert mp.puyo["right"]
    feed(mp, gate, [4.0], 0.95)
    assert not mp.puyo["right"]


def test_off_the_match_screen_restarts_the_wait():
    gate = ScoreGate()
    mp = lp.MatchPipeline(gate=gate)
    feed(mp, gate, [0.0, 0.3], 0.3)
    gate.open = False
    mp.process_frame(cv2.imread(str(FIXTURES / "puyo_right.jpg")), 0.4)   # a menu in between
    feed(mp, gate, [0.9], 0.3)
    assert not mp.puyo["right"]


def test_a_puyo_side_is_not_read():
    gate = ScoreGate()
    mp = lp.MatchPipeline(gate=gate)
    mp.puyo["right"] = True
    calls = []
    mp.left.process_frame = lambda f, t: calls.append("left")
    mp.right.process_frame = lambda f, t: calls.append("right")
    frame = cv2.imread(str(FIXTURES / "puyo_right.jpg"))
    h, w = frame.shape[:2]
    mp.profile = compute_profile(w, h)
    mp.process_frame(frame, 0.0)
    assert calls == ["left"]


def test_hud_hides_the_puyo_side():
    import overlay
    settings = overlay.load_settings()
    settings["hud"]["follow_game"] = False
    overlay.WsClient.start = lambda self: None
    win = overlay.HudWindow(settings)
    disp = overlay.display_settings({"display": {"stat_items": ["apm", "pps", "app"], "style": "band",
                                                 "show_event_log": True, "show_opener": True,
                                                 "opener_display": "board"}})
    win.apply_display(disp, local=True)
    side = {"apm": {"apm": 50.0}, "pps": 1.5, "app": 0.4, "opener": "迷走砲", "opener_age_s": 2.0,
            "event_log": [{"text": "TETRIS", "text_en": "TETRIS"}]}
    win.on_state({"match_elapsed_s": 10.0, "frozen": False, "display": disp, "capture": {"ok": True},
                  "left": side, "right": {**side, "puyo": True}})
    assert not win.stats["left"].isHidden() and win.stats["right"].isHidden()
    assert win.events["right"].isHidden()
    assert not win.badges["left"].isHidden() and win.badges["right"].isHidden()
    assert win.summary.sides["right"]["puyo"] is True

