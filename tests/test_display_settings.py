import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest
from config_store import display_settings


def test_default_is_lower_left():
    assert display_settings({})["stats_position"] == "left"


def test_right_is_accepted():
    assert display_settings({"display": {"stats_position": "right"}})["stats_position"] == "right"


def test_unknown_value_falls_back_to_default():
    assert display_settings({"display": {"stats_position": "top"}})["stats_position"] == "left"


def test_colors_must_be_hex():
    d = display_settings({"display": {"bg_color": "#F5F0E1", "text_color": "red"}})
    assert d["bg_color"] == "#F5F0E1"
    assert d["text_color"] == "#ffffff"          # not #rrggbb: back to the default


def test_font_file_must_be_a_font_inside_user_fonts():
    ok = display_settings({"display": {"font_family": "BIZ UDGothic", "font_file": "user_fonts/BIZ-UDGothicB.ttc"}})
    assert ok["font_file"] == "user_fonts/BIZ-UDGothicB.ttc" and ok["font_family"] == "BIZ UDGothic"
    for bad in ("../../Windows/x.ttf", "user_fonts/../x.ttf", "C:/fonts/x.ttf", "user_fonts/x.exe"):
        assert display_settings({"display": {"font_file": bad}})["font_file"] == ""


def test_simple_style_is_accepted():
    assert display_settings({"display": {"style": "simple"}})["style"] == "simple"


def test_numbers_are_clamped_to_their_range():
    d = display_settings({"display": {"scale": 9, "event_log_count": 0, "background_opacity": -1, "offset_x": 5000}})
    assert d["scale"] == 2.0
    assert d["event_log_count"] == 1
    assert d["background_opacity"] == 0.0
    assert d["offset_x"] == 1232


def test_wrong_types_fall_back_to_defaults():
    d = display_settings({"display": {"stat_items": "apm", "scale": "big", "offset_y": True}})
    assert d["stat_items"] == ["apm", "pps", "app"]
    assert d["scale"] == 1.0
    assert d["offset_y"] == 0


def test_hand_edited_values_are_kept():
    d = display_settings({"display": {"stat_items": ["app", "apm"], "show_event_log": True,
                                      "event_log_count": 5, "scale": 1.25}})
    assert d["stat_items"] == ["app", "apm"] and d["show_event_log"] is True
    assert d["event_log_count"] == 5 and d["scale"] == 1.25


def test_old_show_switches_become_stat_items():
    # a settings file from before stat_items: its show_* switches are kept as the list
    d = display_settings({"display": {"show_apm": True, "show_pps": False, "show_app": True}})
    assert d["stat_items"] == ["apm", "app"]


def test_stat_items_keep_order_and_drop_unknown_or_repeated():
    d = display_settings({"display": {"stat_items": ["ren", "apm", "ren", "bogus", "b2b"]}})
    assert d["stat_items"] == ["ren", "apm", "b2b"]


def test_labels_and_parts_are_checked():
    d = display_settings({"display": {
        "labels": {"apm": "火力/分", "pps": "<b>", "nope": "x"},
        "parts": {"clock": {"scale": 3, "bg_color": "#112233", "text_color": "red"}, "junk": {"scale": 1}}}})
    assert d["labels"] == {"apm": "火力/分"}
    assert d["parts"]["clock"] == {"scale": 2.0, "bg_color": "#112233"}
    assert d["parts"]["stats"] == {} and "junk" not in d["parts"]


def test_part_value_falls_back_to_the_overall_one():
    from config_store import part_value
    d = display_settings({"display": {"scale": 1.2, "parts": {"clock": {"scale": 1.6}}}})
    assert part_value(d, "clock", "scale") == 1.6
    assert part_value(d, "stats", "scale") == 1.2


def test_preset_file_round_trip():
    from config_store import preset_file, read_preset_file
    d = display_settings({"display": {"style": "simple", "bg_color": "#112233", "language": "en"}})
    name, back = read_preset_file(preset_file("my look", d))
    assert name == "my look" and back["style"] == "simple" and back["bg_color"] == "#112233"
    assert "language" not in back                     # the viewer keeps their own language
    with pytest.raises(ValueError):
        read_preset_file({"format": "something else"})


def test_style_defaults_to_gauge_and_accepts_every_design():
    assert display_settings({})["style"] == "gauge"
    for st in ("band", "pop", "gauge", "text", "versus"):
        assert display_settings({"display": {"style": st}})["style"] == st
    assert display_settings({"display": {"style": "nope"}})["style"] == "gauge"


def test_clock_and_event_offsets_default_to_zero_and_are_clamped():
    d = display_settings({})
    assert all(d[k] == 0 for k in ("clock_offset_x", "clock_offset_y", "event_offset_x", "event_offset_y"))
    d = display_settings({"display": {"clock_offset_y": -9999, "event_offset_x": 42}})
    assert d["clock_offset_y"] == -692 and d["event_offset_x"] == 42


def test_language_defaults_to_japanese_and_accepts_english():
    assert display_settings({})["language"] == "ja"
    assert display_settings({"display": {"language": "en"}})["language"] == "en"
    assert display_settings({"display": {"language": "fr"}})["language"] == "ja"


def test_opener_display_choices():
    assert display_settings({})["opener_display"] == "board"
    for m in ("board", "hold", "namebar", "top"):
        assert display_settings({"display": {"opener_display": m}})["opener_display"] == m
    assert display_settings({"display": {"opener_display": "side"}})["opener_display"] == "board"


def test_text_weight_is_a_slider_value_and_old_choices_still_read():
    assert display_settings({})["text_weight"] == 65
    assert display_settings({"display": {"text_weight": "bold"}})["text_weight"] == 65
    assert display_settings({"display": {"text_weight": "normal"}})["text_weight"] == 30
    assert display_settings({"display": {"text_weight": 140}})["text_weight"] == 100
    assert display_settings({"display": {"text_weight": 12}})["text_weight"] == 12


def test_summary_items():
    from config_store import SUMMARY_ITEMS
    d = display_settings({})["summary_items"]
    assert "tspin" in d and "tspin_single" not in d          # as before: one T-SPIN row
    picked = display_settings({"display": {"summary_items": ["tspin_double", "apm", "nope", "tspin_single"]}})
    assert picked["summary_items"] == ["apm", "tspin_single", "tspin_double"]   # known ones, in the fixed order
    assert display_settings({"display": {"summary_items": "x"}})["summary_items"] == d
    assert set(SUMMARY_ITEMS) >= {"tspin_single", "tspin_double", "tspin_triple"}
