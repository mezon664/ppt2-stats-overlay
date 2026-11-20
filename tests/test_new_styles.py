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
from PyQt6 import QtGui, QtWidgets

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


@pytest.mark.parametrize("style", sorted(overlay.DESIGN_FONTS))
def test_design_fonts_ship_and_load(style):
    """broadcast / sport bring their own font: the files are in assets/fonts/
    (with the license), and Qt finds the family once a block has drawn."""
    family, files, _ = overlay.DESIGN_FONTS[style]
    for name in files:
        assert (overlay.FONTS_DIR / name).is_file()
    assert list(overlay.FONTS_DIR.glob("OFL-*.txt"))
    overlay.set_font("", "")   # no font chosen: the design's own (another test may have set one)
    w = overlay.StatBlock(None, "left")
    w.update_side(SIDE, 3.0)
    w.configure(style, "left", ["apm", "pps"], 1.0)
    assert family in QtGui.QFontDatabase.families()
    assert overlay.DESIGN_FONT is None   # only while that block measures / draws


def test_the_overview_draws_the_whole_screen():
    """見本 shows the whole game screen too (user's request), drawn by a HUD
    copy that never connects or records anything."""
    import settings_window as sw
    from config_store import display_settings
    d = display_settings({"display": {"style": "broadcast", "stat_items": ["apm", "pps", "app"]}})
    pm = sw.render_overview(d)
    assert pm is not None and pm.width() == sw.OVERVIEW_W and pm.height() > 250
    hud = sw._OVERVIEW["hud"]
    assert hud.preview
    assert not hud.stats["left"].isHidden()


def test_italic_and_the_default_font_per_design():
    """display.italic leans every text. font_family "" is each design's
    default (中継 / スポーツ斜体: their own font, the others メイリオ); a font
    chosen is used by every design (スポーツ斜体 still leans)."""
    import overlay
    from config_store import display_settings, default_font
    d = display_settings({})
    assert d["italic"] is False and d["font_family"] == "" and d["font_v"] == 2
    assert default_font("sport") == "Saira Condensed" and default_font("band") == "Meiryo"
    try:
        overlay.set_font("", ""); overlay.set_font_options(False)
        assert overlay._slant(10, 100) is None and overlay._font(10, 400).family() == "Meiryo"
        with overlay.design_font("sport"):
            assert overlay.DESIGN_FONT[0] == "Saira Condensed" and overlay._slant(10, 100) == (0.2, 100)
        overlay.set_font("Arial", ""); overlay.set_font_options(False)
        with overlay.design_font("sport"):
            assert overlay.DESIGN_FONT is None and overlay._slant(10, 100) == (0.2, 100)
            assert overlay._font(10, 400).family() == "Arial"
        with overlay.design_font("broadcast"):
            assert overlay.DESIGN_FONT is None and overlay._slant(10, 100) is None
        overlay.set_font_options(True)
        assert overlay._slant(10, 100) == (overlay.ITALIC_SLANT, 100 - 3.5)
    finally:
        overlay.set_font("", ""); overlay.set_font_options(False)
    assert overlay.DESIGN_SLANT == 0.0


def test_an_older_file_keeps_its_font():
    """Before font_v, "Meiryo" was the default (now "" = each design's own)
    and "" the system font."""
    from config_store import display_settings
    assert display_settings({"display": {"font_family": "Meiryo"}})["font_family"] == ""
    assert display_settings({"display": {"font_family": ""}})["font_family"] == "Yu Gothic UI"
    assert display_settings({"display": {"font_family": "Arial"}})["font_family"] == "Arial"
    assert display_settings({"display": {"font_family": "Meiryo", "font_v": 2}})["font_family"] == "Meiryo"


def test_the_font_list_names_the_designs_default():
    import settings_window as sw
    w = sw.SettingsWindow()
    w._style_picked(sw.STYLE_ORDER.index("broadcast"))
    assert w.font_box.itemText(0) == "Barlow Condensed（初期設定）"
    w._style_picked(sw.STYLE_ORDER.index("band"))
    assert w.font_box.itemText(0) == "Meiryo（初期設定）"
    assert w.values()["font_v"] == 2


def test_the_overview_names_match_its_stacks():
    """The overview's openers are the names the recognition gives its stacks
    (user: the names didn't match the stacks)."""
    import opener_detect as od
    import settings_window as sw
    index = od.openers()
    for name, name_en, stack in sw.OVERVIEW_STACKS:
        occ = [[c != "." for c in r] for r in stack] + [[False] * 10 for _ in range(od.ROWS - len(stack))]
        assert od.shown_name(index.match(occ)) == name
        assert index.english.get(name) == name_en
