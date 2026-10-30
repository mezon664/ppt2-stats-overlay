"""The overlays show only while a match screen is up (from after character
select, hidden back at home / menus), unless display.always_show."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hud"))

import cv2
from PyQt6 import QtWidgets

import live_pipeline as lp
from capture_profile import compute_profile

FIXTURES = Path(__file__).resolve().parent / "fixtures"
APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def run(frames):
    """frames: (fixture, t) pairs through a real gate; returns match_screen after each."""
    first = cv2.imread(str(FIXTURES / frames[0][0]))
    h, w = first.shape[:2]
    mp = lp.MatchPipeline(profile=compute_profile(w, h), wait_for_start=True)
    out = []
    for name, t in frames:
        frame = cv2.imread(str(FIXTURES / name))
        mp.process_frame(frame, t)
        out.append(mp.snapshot()["match_screen"])
    return out


def test_hidden_until_a_match_screen_and_after_leaving_it():
    seq = [("menu_main.jpg", 0.0), ("play_sky_stage.jpg", 1.0),       # menu, then a match
           ("pause_candy_stage.jpg", 2.0),                              # paused: still the match
           ("menu_main.jpg", 3.0), ("menu_main.jpg", 4.0),              # a moment away (loading)
           ("play_sky_stage.jpg", 4.5),
           ("menu_main.jpg", 5.0), ("menu_main.jpg", 5.0 + lp.MATCH_SCREEN_HIDE_S)]   # back to the menus
    assert run(seq) == [False, True, True, True, True, True, True, False]


def hud_with(state, **display):
    import overlay
    settings = overlay.load_settings()
    settings["hud"]["follow_game"] = False
    overlay.WsClient.start = lambda self: None
    win = overlay.HudWindow(settings)
    # fixed values, not whatever the user's own file has
    d = overlay.display_settings({"display": {"style": "band", "stat_items": ["apm", "pps", "app"], **display}})
    win.apply_display(d, local=True)
    side = {"apm": {"apm": 50.0}, "pps": 1.5, "app": 0.4}
    win.on_state({"match_elapsed_s": 10.0, "frozen": False, "display": d, "capture": {"ok": True},
                  "left": side, "right": side, **state})
    return win


def test_hud_hides_away_from_the_match_unless_always_shown():
    away = hud_with({"match_screen": False})
    assert away.stats["left"].isHidden() and away.clock.isHidden()
    on = hud_with({"match_screen": True})
    assert not on.stats["left"].isHidden()
    always = hud_with({"match_screen": False}, always_show=True)
    assert not always.stats["left"].isHidden()
    unknown = hud_with({})   # no word from the server yet: as before
    assert not unknown.stats["left"].isHidden()


def test_one_player_only():
    only1 = hud_with({"match_screen": True}, players="left")
    assert not only1.stats["left"].isHidden() and only1.stats["right"].isHidden()
    only2 = hud_with({"match_screen": True}, players="right")
    assert only2.stats["left"].isHidden() and not only2.stats["right"].isHidden()
    assert only1.summary.sides["right"]["puyo"] is True   # its summary column stays empty too


def test_opener_name_time():
    from overlay import popup_alpha
    up = {"opener_age_s": 7.0}
    assert popup_alpha(up, False, seconds=4) == 0.0
    assert popup_alpha(up, False, seconds=10) == 1.0
    assert popup_alpha({"opener_age_s": 300.0}, False, seconds=0) == 1.0   # 0 = until the match ends
    assert popup_alpha({"opener_age_s": 300.0}, True, seconds=0) == 0.0
