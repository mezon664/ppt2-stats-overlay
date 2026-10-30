"""Opener name popup: the same few seconds in every opener_display position,
eased in and out (hud/overlay.py popup_alpha)."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hud"))

import pytest
from PyQt6 import QtWidgets

import overlay
from overlay import POPUP_S, POPUP_FADE_S, popup_alpha

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_alpha_over_the_popup():
    assert popup_alpha(None, False) == 0.0
    assert popup_alpha({"opener_age_s": None}, False) == 0.0
    assert popup_alpha({"opener_age_s": 1.0}, True) == 0.0            # match over
    assert popup_alpha({"opener_age_s": 0.0}, False) == 0.0           # fades in from nothing
    assert popup_alpha({"opener_age_s": 2.0}, False) == 1.0
    assert popup_alpha({"opener_age_s": POPUP_S - POPUP_FADE_S / 2}, False) == pytest.approx(0.5)
    assert popup_alpha({"opener_age_s": POPUP_S}, False) == 0.0


def test_fade_out_only_goes_down():
    ages = [POPUP_S - POPUP_FADE_S + i * POPUP_FADE_S / 50 for i in range(51)]
    alphas = [popup_alpha({"opener_age_s": a}, False) for a in ages]
    assert all(b <= a for a, b in zip(alphas, alphas[1:]))


def test_time_since_the_state_is_added():
    assert popup_alpha({"opener_age_s": 3.9}, False, since_state_s=0.2) == 0.0


def test_text_outline_contrasts_with_the_text_color():
    overlay.set_colors("#0c163c", "#ffffff")
    assert overlay.TEXT_OUTLINE_RGB == (0, 0, 0)
    overlay.set_colors("#f5f0e1", "#3a2a1a")
    assert overlay.TEXT_OUTLINE_RGB == (255, 255, 255)
    assert overlay.BAND_RGB == (245, 240, 225) and overlay.WHITE == (58, 42, 26)
    overlay.set_colors("#0c163c", "#ffffff")


def window(mode, age):
    settings = overlay.load_settings()
    settings["hud"]["follow_game"] = False
    overlay.WsClient.start = lambda self: None
    win = overlay.HudWindow(settings)
    # fixed values, not the user's own file
    disp = overlay.display_settings({"display": {"opener_display": mode, "show_opener": True}})
    win.apply_display(disp, local=True)
    side = {"opener": "迷走砲", "opener_age_s": age, "apm": {"apm": 50.0}, "pps": 1.5, "app": 0.4}
    win.on_state({"match_elapsed_s": 10.0, "frozen": False, "display": disp,
                  "left": side, "right": {}, "capture": {"ok": True}})
    return win


@pytest.mark.parametrize("mode,key", [("board", "left"), ("hold", "left"), ("namebar", "left"), ("top", "both")])
def test_every_position_shows_the_name_only_for_a_few_seconds(mode, key):
    up = window(mode, 2.0)
    assert not up.badges[key].isHidden()
    gone = window(mode, POPUP_S + 1.0)
    assert gone.badges[key].isHidden()
