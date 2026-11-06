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


def test_switched_off_hides_everything():
    off = hud_with({"match_screen": True}, enabled=False, always_show=True)
    assert off.stats["left"].isHidden() and off.clock.isHidden()
    on = hud_with({"match_screen": True}, enabled=True)
    assert not on.stats["left"].isHidden()


def test_shown_in_obs_only_hides_the_hud():
    """show_on_hud off (OBS only): nothing over the game — except while
    positioning, where the parts are needed to drag them."""
    import overlay
    settings = overlay.load_settings()
    settings["hud"]["follow_game"] = False
    overlay.WsClient.start = lambda self: None
    win = overlay.HudWindow(settings)
    d = overlay.display_settings({"display": {"show_on_hud": False, "show_clock": True}})
    win.apply_display(d, local=True)
    win.on_state({"match_elapsed_s": 10.0, "frozen": False, "display": d, "capture": {"ok": True},
                  "match_screen": True, "left": {"apm": {"apm": 50.0}}, "right": {"apm": {"apm": 40.0}}})
    assert win.clock.isHidden() and win.stats["left"].isHidden()
    win.set_edit_mode(True)
    assert not win.clock.isHidden()
    win.set_edit_mode(False)
    win.apply_display({**d, "show_on_hud": True}, local=True)
    assert not win.clock.isHidden() and not win.stats["left"].isHidden()


def test_the_summary_is_drawn_over_the_other_parts():
    """User: where the match summary and the numbers (or other parts) overlap,
    the summary is on top. Qt draws later siblings over earlier ones."""
    win = hud_with({})
    import overlay
    order = [c for c in win.children() if isinstance(c, overlay.QtWidgets.QWidget)]
    above = order[order.index(win.summary) + 1:]
    others = [*win.stats.values(), *win.events.values(), win.versus, win.clock, *win.badges.values()]
    assert not any(w in above for w in others)


class _Screen:
    def __init__(self, x, y, w, h, r):
        from PyQt6 import QtCore
        self._g, self._r = QtCore.QRect(x, y, w, h), r

    def geometry(self):
        return self._g

    def devicePixelRatio(self):
        return self._r


def test_the_hud_goes_to_the_game_on_any_monitor():
    """Qt keeps each monitor's top-left in screen pixels: a game on a second
    monitor with 150% scaling lands at that monitor's own origin plus the
    scaled-down offset, not at its whole position divided by the scaling."""
    import overlay
    screens = [_Screen(0, 0, 2560, 1440, 1.0), _Screen(2560, 0, 1280, 720, 1.5)]   # 1920x1080 at 150%
    assert overlay.native_to_logical(100, 50, 1320, 742, screens) == (100, 50, 1.0)
    assert overlay.native_to_logical(2560 + 300, 90, 1320, 742, screens) == (2560 + 200, 60, 1.5)


def test_nothing_shows_until_the_hud_is_over_the_game():
    """A report: just after start the HUD showed over a Discord window. While
    following the game, nothing shows before the HUD has been put over the
    game's window, nor after the window is gone."""
    import overlay
    if not overlay.HAS_WIN32:
        return
    settings = overlay.load_settings()
    settings["hud"]["follow_game"] = True
    overlay.WsClient.start = lambda self: None
    win = overlay.HudWindow(settings)
    win._follow.stop()                      # placed by hand below, not from a real window
    d = overlay.display_settings({"display": {"show_clock": True}})
    win.apply_display(d, local=True)
    win.on_state({"match_elapsed_s": 10.0, "frozen": False, "display": d, "capture": {"ok": True},
                  "match_screen": True, "left": {"apm": {"apm": 50.0}}, "right": {"apm": {"apm": 40.0}}})
    assert win.clock.isHidden()
    win._last_geom = (0, 0, 1232, 693, 1.0)  # over the game
    win._place()
    assert not win.clock.isHidden()
    win._lost_game()                         # the game's window went away
    assert win.clock.isHidden()


def test_parts_over_what_is_read_stay_off_where_the_hud_shows_in_captures():
    """Two users' HUDs showed in screen captures (Windows didn't keep them
    out) and their numbers covered the T-SPIN banners: not one T-SPIN
    counted. There, parts over what the recognition reads stay off the game
    screen; moved clear, they show again. Elsewhere nothing changes."""
    import overlay
    win = hud_with({}, show_clock=True)
    seen = []
    win.reading_overlap.connect(lambda unsafe, hidden: seen.append((unsafe, hidden)))
    win._place()
    assert not win.stats["left"].isHidden()                    # kept out of captures: as before
    win._want_excluded, win.capture_excluded = True, False      # this PC: shows in captures
    win._place()
    assert win.stats["left"].isHidden() and win.stats["right"].isHidden()   # by the boards, low down
    assert not win.clock.isHidden()                             # below the middle: clear of everything read
    assert seen[-1] == (True, ["stats"])
    d = dict(win.display, offset_y=120)                         # moved down, clear of the banners and boards
    win.apply_display(overlay.display_settings({"display": d}), local=True)
    assert not win.stats["left"].isHidden() and seen[-1] == (True, [])
    assert all(len(z) == 4 for z in overlay.read_zones())


def test_while_positioning_what_is_read_shows_red():
    """Where the HUD shows in captures, while positioning: what is read is
    shaded red, and a part over it stays (to drag it clear) outlined red."""
    win = hud_with({}, show_clock=True)
    win._want_excluded, win.capture_excluded = True, False
    win.set_edit_mode(True)
    assert not win.read_zones_layer.isHidden()
    assert not win.stats["left"].isHidden() and win.stats["left"].blocked
    assert not getattr(win.clock, "blocked", False)
    win.set_edit_mode(False)
    assert win.read_zones_layer.isHidden() and win.stats["left"].isHidden()


def test_no_red_where_the_hud_is_kept_out_of_captures():
    win = hud_with({}, show_clock=True)
    win.set_edit_mode(True)
    assert win.read_zones_layer.isHidden()
    assert not getattr(win.stats["left"], "blocked", False)


def test_long_opener_names_take_more_lines_in_the_summary():
    """User: opener names run long; in the summary they go over a few lines
    (at most SummaryBlock.TEXT_LINES) and the box grows to fit."""
    import overlay
    s = overlay.SummaryBlock(None)
    s.configure("band", "ja", 1.0, ["opener", "apm"])
    s.update_match({"left": {"opener": "TKI"}, "right": {}})
    short = s.height()
    s.update_match({"left": {"opener": "パフェクリ開幕（ハチミツ砲派生）" * 3}, "right": {}})
    lines = s._text_lines("left", "opener")
    assert len(lines) == s.TEXT_LINES and lines[-1].endswith("…")
    assert s.height() == short + (s.TEXT_LINES - 1) * s.TEXT_LINE_H
    assert overlay.wrap_lines("TKI", 12, overlay.BOLD, 100, 3) == ["TKI"]
