"""Settings window: building it must not count as an edit (it would save the
defaults over the user's file), and what it shows comes back out unchanged."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hud"))

import pytest
from PyQt6 import QtWidgets

import config_store
from config_store import display_settings

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def window(tmp_path, monkeypatch):
    monkeypatch.setattr(config_store, "CONFIG_PATH", tmp_path / "overlay_settings.json")
    import settings_window
    return settings_window.SettingsWindow()


def test_building_the_window_saves_nothing(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    assert not w._save_timer.isActive()
    assert not (tmp_path / "overlay_settings.json").exists()


def test_values_round_trip(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    d = display_settings({"display": {
        "style": "simple", "stat_items": ["ren", "apm", "attack"], "labels": {"apm": "火力/分"},
        "player_color_left": "#22c55e", "parts": {"clock": {"scale": 1.5, "bg_color": "#7f1d1d"}},
        "bg_color": "#112233", "scale": 1.2}})
    w._show_values(d)
    assert w.values() == d


def test_a_part_edit_stays_on_that_part(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    w._show_values(display_settings({}))
    w.look_target.setCurrentIndex(w.look_target.findData("clock"))
    w._look_edited("scale", 1.6)
    v = w.values()
    assert v["parts"]["clock"] == {"scale": 1.6} and v["scale"] == 1.0


def test_color_reset_buttons(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    w._show_values(display_settings({"display": {"bg_color": "#112233", "text_color": "#ffee00",
                                                 "parts": {"clock": {"bg_color": "#7f1d1d"}}}}))
    w._reset_look_color("bg_color")      # overall: back to the default
    assert w.values()["bg_color"] == config_store.DISPLAY_DEFAULTS["bg_color"]
    w.look_target.setCurrentIndex(w.look_target.findData("clock"))
    w._reset_look_color("bg_color")      # a part: back to following the overall color
    assert w.values()["parts"]["clock"] == {}
    assert w.values()["text_color"] == "#ffee00"


def test_give_everything_this_parts_look(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    w._show_values(display_settings({"display": {"parts": {"events": {"scale": 0.8, "text_color": "#ffee00"}}}}))
    w.look_target.setCurrentIndex(w.look_target.findData("clock"))
    assert w.part_reset.text() == "全体をこの色に合わせる" and w.part_reset.isEnabled()
    w._look_edited("scale", 1.5)
    w._look_edited("bg_color", "#7f1d1d")
    w._part_to_all()
    v = w.values()
    assert v["bg_color"] == "#7f1d1d" and v["text_color"] == "#ffffff"   # the clock's colors, everywhere
    assert v["scale"] == 1.0                                             # sizes stay as they were
    assert v["parts"]["clock"] == {"scale": 1.5} and v["parts"]["events"] == {"scale": 0.8}
    w.look_target.setCurrentIndex(w.look_target.findData("all"))
    assert not w.part_reset.isEnabled()                # nothing to copy from 全体 itself


def test_minimal_background_row_is_the_line_color(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    w._show_values(display_settings({"display": {"style": "minimal"}}))
    assert w.values()["line_color"] == "#ffffff"   # white to start
    assert w._color_key("bg_color") == "line_color"
    w._look_edited(w._color_key("bg_color"), "#22c55e")
    v = w.values()
    assert v["line_color"] == "#22c55e" and v["bg_color"] == config_store.DISPLAY_DEFAULTS["bg_color"]
    w._reset_look_color("bg_color")
    assert w.values()["line_color"] == "#ffffff"


def test_an_overall_edit_reaches_every_part(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    w._show_values(display_settings({"display": {"parts": {"stats": {"bg_color": "#000000", "scale": 1.4}}}}))
    w.look_target.setCurrentIndex(w.look_target.findData("all"))
    w._look_edited("bg_color", "#3225c1")
    v = w.values()
    assert v["bg_color"] == "#3225c1" and v["parts"]["stats"] == {"scale": 1.4}   # only that setting follows


def test_the_wheel_scrolls_instead_of_changing_values(tmp_path, monkeypatch):
    from PyQt6 import QtCore, QtGui
    w = window(tmp_path, monkeypatch)
    w.resize(500, 400)
    w.show()
    before = (w.look_target.currentIndex(), w.scale.value(), w.opacity.value())
    for target in (w.look_target, w.scale, w.opacity):
        ev = QtGui.QWheelEvent(QtCore.QPointF(5, 5), QtCore.QPointF(5, 5), QtCore.QPoint(0, 0), QtCore.QPoint(0, -120),
                               QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier,
                               QtCore.Qt.ScrollPhase.NoScrollPhase, False)
        QtCore.QCoreApplication.sendEvent(target, ev)
    assert (w.look_target.currentIndex(), w.scale.value(), w.opacity.value()) == before
    assert not w._save_timer.isActive()
    w.close()


def test_text_weight_slider(tmp_path, monkeypatch):
    import overlay
    w = window(tmp_path, monkeypatch)
    w._show_values(display_settings({}))
    assert w.text_weight.value() == 65 and w.values()["text_weight"] == 65
    w.text_weight.setValue(20)
    assert w.values()["text_weight"] == 20
    # 65 looks exactly like the old "bold": Bold, thickened by 0.05 of the font size
    assert overlay.weight_style(65)[2] == pytest.approx(0.05)
    assert overlay.weight_style(0)[2] == 0 and overlay.weight_style(100)[2] == pytest.approx(0.10)
