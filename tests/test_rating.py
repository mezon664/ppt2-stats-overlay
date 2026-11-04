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
