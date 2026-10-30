"""The designs added on 2026-10-30 (hud/overlay.py NEW_STYLES): accepted by
the settings, every part draws in each of them with any number of rows, and
the trend charts keep one value a second per match."""
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
from config_store import STAT_ITEMS, STYLES, display_settings

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
SIDE = {"apm": {"apm": 52.3}, "pps": 1.84, "app": 0.47, "attack": 31, "pieces": 66, "ren": 3, "b2b": 2,
        "event_log": [{"text": "TETRIS"}], "opener": "パフェ積み", "opener_age_s": 2.0}


def test_settings_accept_them():
    for st in overlay.NEW_STYLES:
        assert st in STYLES
        assert display_settings({"display": {"style": st}})["style"] == st
    assert set(overlay.FRAMES) == set(overlay.NEW_STYLES)
    assert display_settings({"display": {"style": "neon"}})["style"] == "frame"   # its old name


@pytest.mark.parametrize("style", overlay.NEW_STYLES)
@pytest.mark.parametrize("items", [["apm"], ["apm", "pps", "app"], list(STAT_ITEMS)])
@pytest.mark.parametrize("mode", ["left", "right"])
def test_stat_block_draws(style, items, mode):
    w = overlay.StatBlock(None, "left")
    w.update_side(SIDE, 3.0)
    w.configure(style, mode, items, 1.5)
    assert w.width() > 20 and w.height() > 20
    assert not w.grab().isNull()
    w.update_side(None)   # nothing measured yet: "--"
    assert not w.grab().isNull()


@pytest.mark.parametrize("style", overlay.NEW_STYLES)
def test_other_parts_draw(style):
    ev = overlay.EventBlock(None, "left")
    ev.configure(style, "left", 3, 1.2)
    ev.update_side(SIDE)
    ck = overlay.ClockBlock(None)
    ck.configure(style, 1.2)
    ck.set_texts("1:23", "試合終了", "")
    sm = overlay.SummaryBlock(None)
    sm.configure(style, "ja", 1.0)
    sm.update_match({"match_elapsed_s": 83, "left": SIDE, "right": SIDE})
    widgets = [ev, ck, sm]
    for mode, sides in (("board", ("left", "right")), ("hold", ("left",)), ("namebar", ("right",)), ("top", ("both",))):
        for sd in sides:   # "both" is only ever the top-center box
            ob = overlay.OpenerBadge(None, sd)
            ob.configure(mode, style, "ja", 1.0)
            ob.set_names({"left": "パフェ積み", "right": None}, 0.6)
            widgets.append(ob)
    for w in widgets:
        assert not w.grab().isNull()


def test_trend_history_one_a_second_and_per_match():
    w = overlay.StatBlock(None, "left")
    for i in range(10):
        w.update_side({**SIDE, "pps": 1.0 + i / 10}, i * 0.5)   # updates every half second
    assert list(w.history["pps"]) == pytest.approx([1.0, 1.2, 1.4, 1.6, 1.8])
    w.update_side(SIDE, 0.0)   # the clock went back: a new match
    assert list(w.history["pps"]) == [1.84]
    for i in range(1, 100):
        w.update_side(SIDE, float(i))
    assert len(w.history["apm"]) == overlay.TREND_SAMPLES


def test_summary_shows_the_chosen_rows():
    sm = overlay.SummaryBlock(None)
    sm.configure("gauge", "ja", 1.0, ["apm", "tspin_single", "tspin_double", "tspin_triple"])
    assert [r[0] for r in sm.rows] == ["apm", "tspin_single", "tspin_double", "tspin_triple"]
    short = sm.height()
    sm.configure("gauge", "ja", 1.0, ["apm"])
    assert sm.height() < short
    side = overlay.summary_side({"match_stats": {"tspin_double": 3, "tspin": 4}})
    assert side["tspin_double"] == 3 and side["tspin"] == 4
