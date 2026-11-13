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
    monkeypatch.setattr(challenge, "CATS_ENABLED", True)   # (the cats: off in the release, tested here)
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


def test_no_cats_in_the_release_and_next_counts():
    """v0.2.14 ships the NEXT cover only (user); how many NEXT show is chosen 5..0"""
    layer = challenge.ChallengeLayer(None)
    d = {"challenge_next": "off", "challenge_cats": True, "challenge_side": "auto"}
    layer.update_state(match(tetris=0), d, 1.0, True)
    layer.update_state(match(tetris=3), d, 1.0, True)
    assert layer.cats == []
    tops = [challenge.next_cover(m, "left") for m in ("from5", "from4", "from3", "from2", "all")]
    assert [t[1] for t in tops] == [294, 244, 194, 144, 100]
    assert challenge.next_cover("off", "left") is None
