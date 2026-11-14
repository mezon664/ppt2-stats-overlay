"""縛りプレイ (hud/challenge.py): NEXT covers and cats over your own board,
on the game screen only, and never where the HUD shows in screen captures."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hud"))
sys.path.insert(0, str(ROOT / "tests"))

from PyQt6 import QtWidgets

import challenge
from config_store import display_settings

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def match(tetris=0, tspin=0, pc=0, start=10.0, you="right", **extra):
    stats = {"tetris": tetris, "tspin": tspin, "perfect_clear": pc}
    return {"match_screen": True, "match_start_t": start, "you_side": you,
            "left": {"match_stats": {}}, "right": {"match_stats": stats}, **extra}


def test_settings_default_off_and_checked():
    d = display_settings({"display": {}})
    assert d["challenge_next"] == "off" and d["challenge_cats"] is False and d["challenge_side"] == "auto"
    d = display_settings({"display": {"challenge_next": "nope", "challenge_cats": "yes", "challenge_side": "x"}})
    assert d["challenge_next"] == "off" and d["challenge_cats"] is False and d["challenge_side"] == "auto"


def test_whose_board_and_how_many_cats():
    assert challenge.challenge_side({"challenge_side": "auto"}, match()) == "right"     # yours
    assert challenge.challenge_side({"challenge_side": "left"}, match()) == "left"
    assert challenge.challenge_side({"challenge_side": "auto"}, {}) == "left"
    assert challenge.cat_count(match(tetris=2, tspin=3, pc=1), "right") == 6
    assert challenge.next_cover("off", "left") is None
    assert challenge.next_cover("all", "left")[1] < challenge.next_cover("from2", "left")[1]


def test_layer_follows_the_match(monkeypatch):
    monkeypatch.setattr(challenge, "CATS_ENABLED", True)
    layer = challenge.ChallengeLayer(None)
    t = [0.0]
    layer.now = lambda: t[0]
    d = {"challenge_next": "from2", "challenge_cats": True, "challenge_side": "auto"}
    layer.update_state(match(tetris=3), d, 1.0, True)
    assert layer.cats == []                                         # already 3 when first seen: no flood
    layer.update_state(match(tetris=4, tspin=1), d, 1.0, True)
    assert not layer.isHidden() and len(layer.cats) == 2 and layer.cover[0] == challenge.NEXT_X["right"][0]
    assert layer.cats[0].clip is not layer.cats[1].clip             # the clips in turn
    first = layer.cats[0]
    t[0] = 1.0
    layer.update_state(match(tetris=4, tspin=1), d, 1.0, True)
    assert layer.cats[0] is first and len(layer.cats) == 2          # nothing new: no new cat
    t[0] = 30.0                                                     # their visits are over
    layer._tick()
    assert layer.cats == []
    layer.update_state(match(tetris=5, tspin=1), d, 1.0, True)
    assert len(layer.cats) == 1                                     # one more TETRIS: one cat
    layer.update_state(match(start=99.0), d, 1.0, True)
    assert layer.cats == []                                         # a new match: no cats
    layer.update_state(match(tetris=1), d, 1.0, False)              # not now (result, positioning...)
    assert layer.isHidden()
    for _ in range(40):
        layer._tick()
    layer.update_state(match(tetris=1), {**d, "challenge_next": "off", "challenge_cats": False}, 1.0, True)
    assert layer.isHidden()


def test_not_shown_where_the_hud_shows_in_captures(monkeypatch):
    monkeypatch.setattr(challenge, "CATS_ENABLED", True)
    from test_match_screen import hud_with
    st = match(tetris=0, you="left")
    st["left"], st["right"] = st["right"], st["left"]
    win = hud_with(st, challenge_next="all", challenge_cats=True)
    win._place()
    st["left"]["match_stats"]["tetris"] = 2
    win._place()
    assert not win.challenge.isHidden() and len(win.challenge.cats) == 2
    win._want_excluded, win.capture_excluded = True, False
    win._place()
    assert win.challenge.isHidden() and win.challenge_blocked()
    win._want_excluded, win.capture_excluded = False, None
    win.set_edit_mode(True)                                         # positioning: out of the way
    assert win.challenge.isHidden()


def test_obs_page_has_every_clip():
    """obs/overlay.html reads the clips from assets/challenge_cats/clips.js
    (tools/cat/make_challenge_cat.py writes it): the same clips, in the same order."""
    import json
    text = (challenge.CLIPS_DIR / "clips.js").read_text(encoding="utf-8")
    page = json.loads(text.split("window.CHALLENGE_CATS = ", 1)[1].rstrip().rstrip(";"))
    clips = challenge.load_clips()
    assert [c["name"] for c in page] == [c.folder.name for c in clips]
    for data, clip in zip(page, clips):
        assert data["frames"] == clip.frames and data["span"] == clip.span
        assert (data["start"], data["end"]) == (clip.start, clip.end)


def test_cat_draws_match_the_obs_page():
    """The OBS page draws the same cats (challengeMix in obs/overlay.html):
    these numbers came out of the page."""
    assert challenge._mix("a") == 0.10352621669881046
    assert challenge._mix("17300000001|left|0|1") == 0.4548068596050143
    assert challenge.cat_seed(1730000000.15, "left", 3) == "17300000002|left|3"
    r = challenge.Rand("x")
    assert (r.random(), r.uniform(0.9, 1.1)) == (0.6570503213442862, 0.9083663875702769)


def test_the_cats_in_turn_now_and_then_the_rare_one_and_next_counts():
    """The cats are back (v0.2.16): the glass-breaking one, one peeking up from
    the bottom, one hanging from a drone at the top, and now and then the
    opener display's cat holding がんばれ; how many NEXT show is chosen 5..0"""
    assert challenge.CATS_ENABLED
    clips = challenge.load_clips()
    assert [c.folder.name for c in clips] == ["cat1", "cat2", "cat4", "cat5", "cat6", "rare_ganbare", "rare_shiba"]
    assert [c.anchor for c in clips[2:4]] == ["bottom", "top"] and clips[-1].rare and clips[-2].rare
    picks = [challenge.pick_clip(clips, challenge.cat_seed(1.0, "left", n), n) for n in range(1000)]
    rare = sum(c.rare for c in picks)
    assert 60 < rare < 140                                          # about one in ten
    common = [c for c in clips if not c.rare]
    n = len(common)
    for r in range(5):   # each round: no cat twice (bar a rare one in its place), shuffled anew
        names = [c.folder.name for c in picks[r * n:(r + 1) * n] if not c.rare]
        assert len(names) == len(set(names))
    orders = {tuple(c.folder.name for c in (challenge.pick_clip(common, challenge.cat_seed(m, "left", n), n)
                                            for n in range(len(common)))) for m in (1.0, 2.0, 3.0, 4.0)}
    assert len(orders) > 1                                           # not the same order every match
    # kept to the screen's edge, over the board
    for clip, edge in ((clips[2], "bottom"), (clips[3], "top")):
        cat = challenge.Cat("x", "left", 0.0, clip)
        f = clip.frames[clip.start]
        top = cat.v.floor - (clip.span[3] - f["y"]) * cat.v.k
        if edge == "bottom":
            assert abs(top + f["h"] * cat.v.k - challenge.SCREEN_H) < 25 * cat.v.k
        else:
            assert top < 5
        mid = cat.v.x0 + (clip.width - (clip.span[0] + clip.span[2]) / 2 if cat.v.mirrored else (clip.span[0] + clip.span[2]) / 2) * cat.v.k
        assert 206 < mid < 421                                      # over the left board
    tops = [challenge.next_cover(m, "left") for m in ("from5", "from4", "from3", "from2", "all")]
    assert [t[1] for t in tops] == [294, 244, 194, 144, 100]
    assert challenge.next_cover("off", "left") is None


def test_cats_for_both_players_or_one():
    """Each player's TETRIS / T-SPIN / PC bring cats on that side (user: 2P too);
    challenge_cats_side picks one."""
    def st(left, right):
        return {"match_screen": True, "match_start_t": 10.0, "you_side": "left",
                "left": {"match_stats": {"tetris": left}}, "right": {"match_stats": {"tetris": right}}}
    for setting, want in (("both", ["left", "right", "right"]), ("left", ["left"]), ("right", ["right", "right"])):
        layer = challenge.ChallengeLayer(None)
        d = {"challenge_cats": True, "challenge_cats_side": setting}
        layer.update_state(st(0, 0), d, 1.0, True)
        layer.update_state(st(1, 2), d, 1.0, True)
        assert sorted(c.side for c in layer.cats) == want, setting
    assert display_settings({"display": {}})["challenge_cats_side"] == "both"


def test_cats_stay_after_the_match_till_the_black():
    """The result (frozen): the cats there stay, none new come; the black
    between matches (a new match_start_t) takes them away (user)."""
    layer = challenge.ChallengeLayer(None)
    t = [0.0]
    layer.now = lambda: t[0]
    d = {"challenge_cats": True}
    layer.update_state(match(tetris=0), d, 1.0, True)
    layer.update_state(match(tetris=1), d, 1.0, True)
    assert len(layer.cats) == 1
    layer.update_state(match(tetris=2, frozen=True), d, 1.0, True)
    assert len(layer.cats) == 1 and not layer.isHidden()           # stays, no new one
    layer.update_state(match(tetris=0, start=None, frozen=True), d, 1.0, True)
    assert layer.cats == []                                         # the black: gone


def test_the_bottom_rows_covered():
    layer = challenge.ChallengeLayer(None)
    layer.update_state(match(), {"challenge_bottom_rows": 6, "challenge_side": "left"}, 1.0, True)
    assert layer.bottom == ("left", 6) and not layer.isHidden()
    layer.update_state(match(frozen=True), {"challenge_bottom_rows": 6}, 1.0, True)
    assert layer.bottom is None                                     # the result: off
    assert display_settings({"display": {"challenge_bottom_rows": 40}})["challenge_bottom_rows"] == 19


def test_the_comments_go_over_the_huds_parts():
    """The flowing comments over the numbers and the result (user): their own view, raised over the summary."""
    import overlay
    settings = overlay.load_settings()
    settings["hud"]["follow_game"] = False
    overlay.WsClient.start = lambda self: None
    win = overlay.HudWindow(settings)
    kids = [w for w in win.children() if isinstance(w, QtWidgets.QWidget)]
    assert kids.index(win.comment_view) > kids.index(win.summary) > kids.index(win.challenge)
    assert win.challenge.view is win.comment_view


def test_challenge_mode_off_in_rated_matches_if_asked():
    """challenge_off_in_rated: a rated match turns all of 縛りプレイ off (the
    HUD, OBS and the server's comments / mosaic all go by challenge_display)."""
    from config_store import challenge_display, display_settings
    d = display_settings({"display": {"challenge_next": "all", "challenge_cats": True, "challenge_comments": "many",
                                      "challenge_dopamine": "max", "challenge_announcer": True,
                                      "challenge_bottom_rows": 5, "challenge_off_in_rated": True}})
    rated = {"match_screen": True, "rated_match": True}
    off = challenge_display(d, rated)
    assert (off["challenge_next"], off["challenge_cats"], off["challenge_comments"], off["challenge_dopamine"],
            off["challenge_announcer"], off["challenge_bottom_rows"]) == ("off", False, "off", "off", False, 0)
    assert challenge_display(d, {"match_screen": True, "rated_match": False}) is d        # not rated: as it is
    assert challenge_display({**d, "challenge_off_in_rated": False}, rated)["challenge_next"] == "all"   # not asked
    assert display_settings({"display": {}})["challenge_off_in_rated"] is False
    html = (Path(__file__).resolve().parent.parent / "obs" / "overlay.html").read_text(encoding="utf-8")
    assert "challenge_off_in_rated" in html and "challengeDisplay(display" in html
