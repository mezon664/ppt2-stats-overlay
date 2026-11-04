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


def test_on_off_switch_from_the_tray_keeps_the_rest(tmp_path, monkeypatch):
    """The tray switch works even if the window was never opened: it reads
    the saved settings first and only changes on/off (it mustn't save the
    unopened window's defaults over the user's file)."""
    w = window(tmp_path, monkeypatch)
    saved = display_settings({"display": {"style": "hex", "bg_color": "#123456", "scale": 1.4}})
    config_store.save_settings({**config_store.DEFAULTS, "display": saved})
    w.set_enabled(False)
    w._save_timer.stop()
    w._save()
    d = display_settings(config_store.load_settings())
    assert d["enabled"] is False
    assert d["style"] == "hex" and d["bg_color"] == "#123456" and d["scale"] == 1.4
    assert w.enabled_button.text().startswith("○")
    w.set_enabled(True)
    assert w.values()["enabled"] is True and w.enabled_button.text().startswith("●")


def test_opener_language_and_each_players_opener_position(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    d = display_settings({"display": {"opener_language": "en", "opener_left_offset_x": 30,
                                      "opener_right_offset_y": -12}})
    w._show_values(d)
    assert w.values() == d
    import settings_window
    assert "opener_left" in settings_window.TARGET_ORDER and "opener_right" in settings_window.TARGET_ORDER
    w._set_offset("opener_right", 5, 6)
    assert w.values()["opener_right_offset_x"] == 5 and w.values()["opener_right_offset_y"] == 6
    assert w.values()["opener_left_offset_x"] == 30                  # 1P untouched


def test_combo_label_in_english(tmp_path, monkeypatch):
    w = window(tmp_path, monkeypatch)
    w.lang = "en"
    w.retranslate()
    assert w.label_names["ren"].text() == "COMBO"
    w.lang = "ja"
    w.retranslate()
    assert w.label_names["ren"].text() == "REN"


def test_on_button_shows_it_anyway_off_the_match_screen(tmp_path, monkeypatch):
    """User: when it's hidden on the home screen, the on button shows it anyway
    (display.force_show) — until a match screen comes up again."""
    w = window(tmp_path, monkeypatch)
    config_store.save_settings({**config_store.DEFAULTS, "display": display_settings({"display": {"style": "hex"}})})
    w._show_values(display_settings(config_store.load_settings()))   # as open() does
    w.set_match_screen(False)                        # home screen: on, but hidden
    assert w.enabled_button.text().startswith("◐")
    w._enabled_clicked()                             # -> shown anyway
    assert w.values()["force_show"] is True and w.values()["enabled"] is True
    w._save_timer.stop()
    w._save()
    w.set_match_screen(True)                         # a match: back to the usual hiding
    w._save_timer.stop()
    w._save()
    d = display_settings(config_store.load_settings())
    assert d["force_show"] is False and d["enabled"] is True and d["style"] == "hex"
    w._enabled_clicked()                             # on the match screen: on -> off
    assert w.values()["enabled"] is False
    w.set_match_screen(False)
    w._enabled_clicked()                             # off, at home: on and shown at once
    assert w.values()["enabled"] is True and w.values()["force_show"] is True


def test_game_screen_and_obs_switch_on_their_own(tmp_path, monkeypatch):
    """Where it shows while on: over the game (HUD) and in OBS, each its own
    switch (user's request). From the tray only that one changes."""
    w = window(tmp_path, monkeypatch)
    assert w.values()["show_on_hud"] is True and w.values()["show_on_obs"] is True
    saved = display_settings({"display": {"style": "hex", "scale": 1.4}})
    config_store.save_settings({**config_store.DEFAULTS, "display": saved})
    w.set_shown_on("show_on_hud", False)
    w._save_timer.stop()
    w._save()
    d = display_settings(config_store.load_settings())
    assert d["show_on_hud"] is False and d["show_on_obs"] is True and d["enabled"] is True
    assert d["style"] == "hex" and d["scale"] == 1.4
    assert not w.show_on_hud.isChecked() and w.show_on_obs.isChecked()
    w.set_enabled(False)
    assert not w.show_on_obs.isEnabled()      # greyed while everything is off
