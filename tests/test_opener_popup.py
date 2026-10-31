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


def test_cat_timing():
    """「猫」: walks in, holds the paper up for opener_seconds (going gently back
    and forth when that's longer than the clip), walks off, then is gone."""
    cat = overlay.load_cat()
    assert cat and cat["hold_start"] < cat["hold_end"] < len(cat["frames"])
    fps = cat["fps"]
    assert overlay.cat_frame(cat, 0.0, 4) == 0
    held = overlay.cat_frame(cat, (cat["hold_start"] + 2) / fps, 4)
    assert cat["hold_start"] <= held <= cat["hold_end"] and cat["frames"][held]["paper"]
    later = overlay.cat_frame(cat, cat["hold_start"] / fps + 4 + 0.5, 4)
    assert later > cat["hold_end"]                                    # walking off
    assert overlay.cat_frame(cat, 60.0, 4) is None                    # gone
    for age in (5, 20, 60):                                           # 0 = until the match ends
        i = overlay.cat_frame(cat, age, 0)
        assert cat["hold_start"] <= i <= cat["hold_end"]
    assert all((overlay.CAT_DIR / f["file"]).exists() for f in cat["frames"] if f["file"])


def test_cat_leaves_without_skipping():
    """User: frames were skipped as the cat left. However long the paper is
    up, the walk off follows on from where the cat stood, frame by frame."""
    cat = overlay.load_cat()
    fps = cat["fps"]
    assert cat["hold_start"] <= cat["still_start"] < cat["still_end"] <= cat["hold_end"]
    for seconds in (2, 3, 4, 6, 8, 10):
        prev, t = None, 0.0
        while (p := overlay.cat_pos(cat, t, seconds)) is not None:
            x = p[0] + p[2]
            if prev is not None and (x <= cat["still_start"] or prev >= cat["still_end"]):
                assert 0 <= x - prev <= 1.01 * fps / 60 + 1e-6, (seconds, prev, x)   # as filmed
            prev, t = x, t + 1 / 60
        assert prev > len(cat["frames"]) - 3                    # played to the end


def test_cat_is_a_choice():
    d = overlay.display_settings({"display": {"opener_display": "cat"}})
    assert d["opener_display"] == "cat"
    win = window("cat", 2.0)
    assert all(b.isHidden() for b in win.badges.values())


def test_opener_name_language_is_its_own_setting():
    """display.opener_language: "auto" follows the overlay's language; "ja" / "en"
    pick the name language on its own (user's request)."""
    from config_store import opener_language
    assert opener_language(overlay.display_settings({"display": {"language": "en"}})) == "en"   # default: auto
    assert opener_language(overlay.display_settings({"display": {"language": "ja"}})) == "ja"
    assert opener_language(overlay.display_settings({"display": {"language": "en", "opener_language": "ja"}})) == "ja"
    assert overlay.display_settings({"display": {"opener_language": "fr"}})["opener_language"] == "auto"
    win = window("board", 2.0)
    side = {"opener": "迷走砲", "opener_en": "Stray Cannon", "opener_age_s": 2.0,
            "event_log": [{"t": 1.0, "ren_source": "opener", "opener": "迷走砲", "opener_en": "Stray Cannon",
                           "text": "開幕：迷走砲", "text_en": "Opener: Stray Cannon"}]}
    for lang, olang, name, line in (("ja", "auto", "迷走砲", "開幕：迷走砲"), ("en", "auto", "Stray Cannon", "Opener: Stray Cannon"),
                                    ("ja", "en", "Stray Cannon", "開幕：Stray Cannon"), ("en", "ja", "迷走砲", "Opener: 迷走砲")):
        disp = overlay.display_settings({"display": {"opener_display": "board", "show_opener": True, "language": lang,
                                                     "opener_language": olang, "show_event_log": True}})
        win.apply_display(disp, local=True)
        win.on_state({"match_elapsed_s": 10.0, "frozen": False, "display": disp,
                      "left": side, "right": {}, "capture": {"ok": True}})
        assert win.badges["left"].names["left"] == name, (lang, olang)
        win.events["left"].update_side(side)
        assert win.events["left"].texts == [line], (lang, olang)


def test_each_players_opener_name_moves_on_its_own():
    """display.opener_left/right_offset: 1P and 2P are placed separately."""
    win = window("board", 2.0)
    before = win.badges["left"].pos()
    disp = overlay.display_settings({"display": {"opener_display": "board", "show_opener": True,
                                                 "opener_left_offset_x": 40, "opener_left_offset_y": -20}})
    win.apply_display(disp, local=True)
    win._place_openers()
    after = win.badges["left"].pos()
    s = win._scale
    assert after.x() - before.x() == pytest.approx(40 * s, abs=1)
    assert after.y() - before.y() == pytest.approx(-20 * s, abs=1)
    # dragging moves both by default; display.drag_each_side: each player's own
    assert win.badges["left"].drag_target == "opener" and win.cats["right"].drag_target == "opener"
    win.apply_display(overlay.display_settings({"display": {**disp, "drag_each_side": True}}), local=True)
    assert win.badges["left"].drag_target == "opener_left" and win.badges["right"].drag_target == "opener_right"
    assert win.cats["right"].drag_target == "opener_right" and win.stats["left"].drag_target == "stats_left"
    # both players' shared offset adds to each one's own
    assert overlay.opener_offset({**disp, "opener_offset_x": 10}, "left") == (50, -20)
    assert overlay.opener_offset({**disp, "opener_offset_x": 10}, "both") == (10, 0)


def test_each_players_numbers_move_on_their_own():
    win = window("board", 2.0)
    win.on_state({"match_elapsed_s": 10.0, "frozen": False, "display": win.display,
                  "left": {"apm": {"apm": 50.0}, "pps": 1.5}, "right": {"apm": {"apm": 40.0}, "pps": 1.2},
                  "capture": {"ok": True}})
    l0, r0 = win.stats["left"].pos(), win.stats["right"].pos()
    win.apply_display(overlay.display_settings({"display": {**win.display, "stats_right_offset_x": 30}}), local=True)
    win._place()
    assert win.stats["left"].pos() == l0                                       # 1P stays
    assert win.stats["right"].pos().x() - r0.x() == pytest.approx(30 * win._scale, abs=1)


def test_the_wheel_resizes_a_part_while_positioning():
    win = window("board", 2.0)
    sizes = []
    win.part_resized.connect(lambda part, size: sizes.append((part, size)))
    before = overlay.part_value(win.display, "stats", "scale")
    win.wheel_resize("stats_left", 120)
    assert sizes == [("stats", round(before + overlay.WHEEL_SCALE_STEP, 2))]
    assert overlay.part_value(win.display, "stats", "scale") == sizes[0][1]
    win.wheel_resize("opener", -120)
    assert sizes[-1][0] == "opener"


def test_names_fit_on_the_paper_where_they_can():
    """User: a long name may run off the paper, but fit it on where possible."""
    measure = lambda t: 60.0 * len(t)          # every character 0.6 em wide
    lines, size = overlay.paper_layout("迷走砲", measure)
    assert lines == ["迷走砲"] and size == overlay.PAPER_MAX_PX
    lines, size = overlay.paper_layout("Mini Triple Double", measure)   # too long for one line: two
    assert lines == ["Mini Triple", "Double"] and size >= overlay.PAPER_TWO_LINE_MIN_PX
    lines, size = overlay.paper_layout("パフェ積みからのTSDとTST", measure)   # no space: split anywhere, evenly
    assert len(lines) == 2 and abs(len(lines[0]) - len(lines[1])) <= 1
    long = "A" * 40
    lines, size = overlay.paper_layout(long, measure)                # can't fit: one line off the sides
    assert lines == [long] and size == overlay.CAT_PAPER_MIN_PX


def test_numbers_follow_the_wider_frame_against_puyo():
    """Against a Puyo player the Tetris frame's edge is 12 px further out:
    the numbers move in with it (user: they looked shifted right)."""
    win = window("board", 2.0)
    me = {"apm": {"apm": 50.0}, "pps": 1.5}
    for other, shift in (({"apm": {"apm": 40.0}}, 0), ({"puyo": True}, overlay.VS_PUYO_SHIFT_X["left"])):
        win.on_state({"match_elapsed_s": 10.0, "frozen": False, "display": win.display, "match_screen": True,
                      "left": me, "right": other, "capture": {"ok": True}})
        win._place()
        right_edge = win.stats["left"].geometry().right() + 1
        if shift == 0:
            base = right_edge
        else:
            assert right_edge - base == pytest.approx(shift * win._scale, abs=1)


def test_app_icon():
    """The icon the app draws (tray, title bars) and assets/app.ico (the
    desktop shortcut's) come from the same drawing, at every size."""
    icon = overlay.make_tray_icon()
    assert {s.width() for s in icon.availableSizes()} >= {16, 32, 48, 256}
    img = overlay.icon_image(64)
    assert img.pixelColor(32, 2).alpha() == 255 and img.pixelColor(0, 0).alpha() < 255   # rounded tile
    off = overlay.icon_image(64, enabled=False)
    assert img != off                                                                    # greyed when off
    data = (overlay.ROOT_DIR / "assets" / "app.ico").read_bytes()
    assert data[:4] == b"\x00\x00\x01\x00" and int.from_bytes(data[4:6], "little") >= 5
