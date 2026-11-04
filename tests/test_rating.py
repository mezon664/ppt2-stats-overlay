"""Online rating history (scripts/rating.py): finding your rating box on the
まちうけ screen (you as 1P or 2P) and the league menu, reading it, and keeping
one history per league. Frames: debug_frames/burst_rating."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import cv2
import pytest

import rating
from live_capture import shrink_for_recognition

FIX = Path(__file__).resolve().parent / "fixtures"


def frame(name, shrink=False):
    img = cv2.imread(str(FIX / name))
    return shrink_for_recognition(img)[0] if shrink else img


@pytest.mark.parametrize("shrink", [False, True])
def test_your_box_on_each_screen(shrink):
    r = rating.RatingReader()
    k = frame("rating_wait_1p.jpg", shrink).shape[1] / rating.BASE_W
    assert r.own_box(frame("rating_wait_1p.jpg", shrink)) == rating._scale(rating.YOU["left"]["box"], k)
    assert r.own_box(frame("rating_wait_2p.jpg", shrink)) == rating._scale(rating.YOU["right"]["box"], k)
    assert r.own_box(frame("rating_menu.jpg", shrink)) == rating._scale(rating.MENU["box"], k)
    assert r.own_box(frame("rating_play.jpg", shrink)) is None
    assert r.league_on_screen(frame("rating_menu.jpg", shrink)) == "puzzle"
    for name in ("rating_wait_1p.jpg", "rating_wait_2p.jpg", "rating_play.jpg"):
        assert r.league_on_screen(frame(name, shrink)) is None


def test_reading_your_rating():
    r = rating.RatingReader()
    if r._ocr_engine() is None:
        pytest.skip("no Windows text recognition here")
    for name, want in (("rating_wait_1p.jpg", 2610), ("rating_wait_2p.jpg", 2615), ("rating_menu.jpg", 2610)):
        img = frame(name)
        x1, y1, x2, y2 = r.own_box(img)
        assert r.read_number(img[y1:y2, x1:x2]) == want, name


def test_kept_after_two_same_reads_with_its_league(monkeypatch):
    r = rating.RatingReader()
    monkeypatch.setattr(r, "read_number", lambda crop: 2615)
    wait = frame("rating_wait_2p.jpg")
    assert r.update(wait, now=0) is None           # no league known yet: not kept
    assert r.update(frame("rating_menu.jpg"), now=1) is None   # the menu: パズルリーグ (first read)
    assert r.update(wait, now=2) == ("puzzle", 2615)            # same again: kept
    assert r.update(wait, now=3) is None                         # unchanged: not again
    assert r.update(wait, now=3.5) is None                       # (at most once a second)


def test_history_per_league(tmp_path):
    path = tmp_path / "r.json"
    assert rating.add("puzzle", 2610, path, now=1)
    assert not rating.add("puzzle", 2610, path, now=2)   # the same as that league's last
    assert rating.add("tetris", 1800, path, now=3)
    assert rating.add("puzzle", 2615, path, now=4)
    assert [p["rating"] for p in rating.load(path, "puzzle")] == [2610, 2615]
    assert [p["rating"] for p in rating.load(path, "tetris")] == [1800]


def test_an_unknown_leagues_menu_is_not_put_down_as_the_last_league(monkeypatch):
    """Into another league whose menu title isn't known yet: its rating isn't
    kept as the league seen before (Puzzle)."""
    r = rating.RatingReader()
    monkeypatch.setattr(r, "read_number", lambda crop: 2615)
    menu, wait = frame("rating_menu.jpg"), frame("rating_wait_2p.jpg")
    other_menu = menu.copy()
    other_menu[40:150, 20:340] = (240, 240, 240)       # another league's title
    r.update(menu, now=10)
    assert r.league == "puzzle"
    r.update(other_menu, now=11)
    assert r.league is None
    assert r.update(wait, now=12) is None and r.update(wait, now=13) is None


def test_same_number_kept_once_per_league_but_again_for_another(tmp_path):
    """まちうけ → back → まちうけ: once. The same number in another league: its own."""
    path = tmp_path / "r.json"
    assert rating.add("puzzle", 2610, path, now=1)
    assert not rating.add("puzzle", 2610, path, now=2)
    assert rating.add("tetris", 2610, path, now=3)
    assert len(rating.load(path)) == 2


@pytest.mark.parametrize("name, league", [("rating_menu.jpg", "puzzle"), ("rating_menu_tetris.jpg", "tetris"),
                                          ("rating_menu_puyo.jpg", "puyo"), ("rating_menu_skill.jpg", "skill")])
def test_each_leagues_menu(name, league):
    """Every league's menu is told apart by its title (debug_frames/burst_leagues)."""
    r = rating.RatingReader()
    for shrink in (False, True):
        img = frame(name, shrink)
        assert r.league_on_screen(img) == league
        assert r.find(img)[0] == "menu"


def test_each_leagues_rating_is_read():
    r = rating.RatingReader()
    if r._ocr_engine() is None:
        pytest.skip("no Windows text recognition here")
    for name, want in (("rating_menu_tetris.jpg", 2504), ("rating_menu_puyo.jpg", 984), ("rating_menu_skill.jpg", 985)):
        img = frame(name)
        x1, y1, x2, y2 = r.own_box(img)
        assert r.read_number(img[y1:y2, x1:x2]) == want, name


def test_the_live_menu_that_read_wrong():
    """The live menu (as the server sees it, shrunk to 1232): its 2618 read
    as 266 every time when cut to pure black and white first."""
    r = rating.RatingReader()
    if r._ocr_engine() is None:
        pytest.skip("no Windows text recognition here")
    img = cv2.imread(str(FIX / "rating_menu_live.png"))
    x1, y1, x2, y2 = r.own_box(img)
    assert r.read_number(img[y1:y2, x1:x2]) == 2618


def test_a_shorter_number_needs_many_reads(monkeypatch):
    """2633 -> 263 (a window over the last digit, user report): not kept
    unless read that way UNLIKELY_READS times in a row."""
    r = rating.RatingReader()
    r.league = "puzzle"
    r.set_last("puzzle", 2633)
    r.session_value["puzzle"] = 2633
    monkeypatch.setattr(r, "read_number", lambda crop: 263)
    wait = frame("rating_wait_1p.jpg")
    got = [r.update(wait, now=10 + i) for i in range(rating.DIGITS_CHANGE_READS - 1)]
    assert got == [None] * (rating.DIGITS_CHANGE_READS - 1)
    monkeypatch.setattr(r, "read_number", lambda crop: 2640)   # a real change: kept on the second read
    assert r.update(wait, now=30) is None and r.update(wait, now=31) == ("puzzle", 2640)


def test_not_read_while_a_window_covers_the_box(monkeypatch):
    r = rating.RatingReader()
    r.league = "puzzle"
    calls = []
    monkeypatch.setattr(r, "read_number", lambda crop: calls.append(1) or 2618)
    wait = frame("rating_wait_1p.jpg")
    assert r.update(wait, now=10, is_covered=lambda box: True) is None
    assert r.update(wait, now=11, is_covered=lambda box: True) is None
    assert calls == []                                    # covered: not even read
    r.update(wait, now=12, is_covered=lambda box: False)
    assert r.update(wait, now=13, is_covered=lambda box: False) == ("puzzle", 2618)



def test_a_big_jump_in_this_run_needs_many_reads_but_not_after_a_restart(monkeypatch):
    """One match moves the rating ~40 at most: 2633 -> 2733 in one run needs
    10 reads. Opened again after matches without the app, the new rating
    shows at once even far from the history's last (user)."""
    wait = frame("rating_wait_1p.jpg")
    r = rating.RatingReader()
    r.league = "puzzle"
    r.session_value["puzzle"] = 2633
    monkeypatch.setattr(r, "read_number", lambda crop: 2733)
    got = [r.update(wait, now=10 + i) for i in range(rating.UNLIKELY_READS)]
    assert got[:-1] == [None] * (rating.UNLIKELY_READS - 1) and got[-1] == ("puzzle", 2733)
    fresh = rating.RatingReader()              # a new run: the history's last only stops a repeat
    fresh.league = "puzzle"
    fresh.set_last("puzzle", 2633)
    monkeypatch.setattr(fresh, "read_number", lambda crop: 2733)
    assert fresh.update(wait, now=10) is None and fresh.update(wait, now=11) == ("puzzle", 2733)
    monkeypatch.setattr(fresh, "read_number", lambda crop: 2760)   # +27 after a match: as usual
    assert fresh.update(wait, now=12) is None and fresh.update(wait, now=13) == ("puzzle", 2760)
