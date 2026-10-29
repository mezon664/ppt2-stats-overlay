import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from config_store import display_settings


def test_default_is_lower_left():
    assert display_settings({})["stats_position"] == "left"


def test_right_is_accepted():
    assert display_settings({"display": {"stats_position": "right"}})["stats_position"] == "right"


def test_unknown_value_falls_back_to_default():
    assert display_settings({"display": {"stats_position": "top"}})["stats_position"] == "left"


def test_numbers_are_clamped_to_their_range():
    d = display_settings({"display": {"scale": 9, "event_log_count": 0, "background_opacity": -1, "offset_x": 5000}})
    assert d["scale"] == 2.0
    assert d["event_log_count"] == 1
    assert d["background_opacity"] == 0.0
    assert d["offset_x"] == 1232


def test_wrong_types_fall_back_to_defaults():
    d = display_settings({"display": {"show_apm": "no", "scale": "big", "offset_y": True}})
    assert d["show_apm"] is True
    assert d["scale"] == 1.0
    assert d["offset_y"] == 0


def test_hand_edited_values_are_kept():
    d = display_settings({"display": {"show_pps": False, "show_event_log": True, "event_log_count": 5, "scale": 1.25}})
    assert d["show_pps"] is False and d["show_event_log"] is True
    assert d["event_log_count"] == 5 and d["scale"] == 1.25


def test_style_defaults_to_band_and_accepts_every_design():
    assert display_settings({})["style"] == "band"
    for st in ("band", "pop", "gauge", "text", "versus"):
        assert display_settings({"display": {"style": st}})["style"] == st
    assert display_settings({"display": {"style": "neon"}})["style"] == "band"


def test_clock_and_event_offsets_default_to_zero_and_are_clamped():
    d = display_settings({})
    assert all(d[k] == 0 for k in ("clock_offset_x", "clock_offset_y", "event_offset_x", "event_offset_y"))
    d = display_settings({"display": {"clock_offset_y": -9999, "event_offset_x": 42}})
    assert d["clock_offset_y"] == -692 and d["event_offset_x"] == 42


def test_language_defaults_to_japanese_and_accepts_english():
    assert display_settings({})["language"] == "ja"
    assert display_settings({"display": {"language": "en"}})["language"] == "en"
    assert display_settings({"display": {"language": "fr"}})["language"] == "ja"
