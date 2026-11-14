"""縛りプレイ: the mosaic over your board, coarser as a number goes up (scripts/mosaic.py)."""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import mosaic
from config_store import display_settings


def you(apm, lines, you="left"):
    return {"you": you, you: {"stats": {"apm": apm, "pps": 1.5, "lines_sent": lines}}}


def test_strongest_at_your_usual_or_a_set_value():
    usual = mosaic.usual([you(40, 30)] * 3 + [you(60, 50)] * 3 + [{"left": {}, "right": {}}])
    assert usual["matches"] == 6 and usual["apm"] == 50 and usual["attack"] == 40
    st = {"left": {"apm": {"apm": 25}, "b2b": 4, "ren": 0}}
    d = display_settings({"display": {"challenge_mosaic": "apm"}})
    assert round(mosaic.strength(d, st, "left", usual), 3) == round(0.5 ** mosaic.CURVE, 3)   # half your usual APM: weak still
    assert mosaic.strength(d, st, "left", {"matches": 2, "apm": 10}) == (25 / 60) ** mosaic.CURVE   # too few matches: the default
    assert mosaic.strength({**d, "challenge_mosaic_max": 25.0}, st, "left", usual) == 1.0
    assert mosaic.strength({**d, "challenge_mosaic": "b2b"}, st, "left", usual) == 0.5 ** mosaic.CURVE   # B2B 4 of 8
    assert mosaic.strength({**d, "challenge_mosaic": "ren"}, st, "left", usual) == 0.0
    assert mosaic.strength({**d, "challenge_mosaic": "off"}, st, "left", usual) == 0.0
    assert mosaic.block_px(0) == 0 and mosaic.block_px(1) == mosaic.MAX_BLOCK


def test_the_state_for_obs_has_the_coarse_board():
    d = display_settings({"display": {"challenge_mosaic": "apm", "challenge_mosaic_max": 60}})
    st = {"match_screen": True, "you_side": "right", "right": {"apm": {"apm": 60}}}
    frame = np.zeros((692, 1232, 3), np.uint8)
    out = mosaic.state_for(d, st, frame)
    assert out["side"] == "right" and out["strength"] == 1.0
    assert (out["w"], out["h"]) == (8, 17)          # a little over a cell a block at the strongest
    assert mosaic.state_for(d, {**st, "frozen": True}, frame) is None        # the result screen
    assert mosaic.state_for({**d, "show_on_obs": False}, st, frame) == {"side": "right", "strength": 1.0}
    assert mosaic.state_for(display_settings({}), st, frame) is None          # off



def test_the_obs_page_declares_each_name_once():
    """A name declared twice at the top of obs/overlay.html's script stops the
    whole page (it happened with CH_BOARD while adding the mosaic)."""
    import re
    from collections import Counter
    page = (ROOT / "obs" / "overlay.html").read_text(encoding="utf-8")
    names = re.findall(r"^(?:const|let|function|class)\s+([A-Za-z_$][\w$]*)", page, re.MULTILINE)
    twice = [n for n, k in Counter(names).items() if k > 1]
    assert twice == []


def test_a_picture_instead_of_the_mosaic():
    """challenge_mosaic_style "image": a picture over the board, its opacity the
    strength; the cat unless the user picked one (assets/user_images/)."""
    d = display_settings({"display": {"challenge_mosaic": "apm", "challenge_mosaic_max": 60,
                                      "challenge_mosaic_style": "image"}})
    st = {"match_screen": True, "you_side": "left", "left": {"apm": {"apm": 60}}}
    frame = np.zeros((692, 1232, 3), np.uint8)
    out = mosaic.state_for(d, st, frame)
    assert out == {"side": "left", "strength": 1.0, "image": "challenge_image/cat.jpg"}
    assert (ROOT / "assets" / out["image"]).exists()
    mine = mosaic.state_for({**d, "challenge_image": "user_images/mine.png"}, st, frame)
    assert mine["image"] == "user_images/mine.png"
    assert display_settings({"display": {"challenge_image": "../../secret.png"}})["challenge_image"] == ""
    # cover: a tall picture fills the board, cut top and bottom
    sx, sy, sw, sh = mosaic.cover_rect(100, 400, 0, 0, 100, 200)
    assert (sx, sw) == (0, 100) and sh == 200 and sy == 100


def test_tied_to_tetris_and_t_spin():
    """"events": each TETRIS / T-SPIN / PC a step stronger, fading when none come."""
    lv = mosaic.EventLevel()
    st = lambda n, start=1.0: {"match_start_t": start, "left": {"match_stats": {"tetris": n}}}
    assert lv.update(st(3), "left", 0.0) == 0.0                 # already 3 when first seen: from none
    assert lv.update(st(4), "left", 1.0) == mosaic.EVENT_STEP    # one TETRIS
    lv.update({"match_start_t": 1.0, "left": {"match_stats": {"tetris": 5, "tspin": 2}}}, "left", 1.0)
    assert lv.level == 1.0                                       # four steps: the strongest (and no more)
    half = lv.update({"match_start_t": 1.0, "left": {"match_stats": {"tetris": 5, "tspin": 2}}}, "left",
                     1.0 + mosaic.EVENT_FADE_S / 2)
    assert abs(half - 0.5) < 1e-9                                # fading while none come
    assert lv.update(st(0, start=2.0), "left", 100.0) == 0.0     # a new match: from none
    d = display_settings({"display": {"challenge_mosaic": "events"}})
    s2 = {"match_screen": True, "you_side": "left", "match_start_t": 5.0, "left": {"match_stats": {"tetris": 0}}}
    ev = mosaic.EventLevel()
    assert mosaic.state_for(d, s2, None, events=ev, now=0.0)["strength"] == 0.0
    s2["left"]["match_stats"]["tetris"] = 2
    assert mosaic.state_for(d, s2, None, events=ev, now=0.5)["strength"] == 0.5


def test_the_garbage_rows_to_cover():
    """challenge_garbage: the server's count of garbage rows on the board the
    challenge is on (none when off, on the result screen, or against Puyo)."""
    d = display_settings({"display": {"challenge_garbage": True, "challenge_side": "right"}})
    st = {"match_screen": True, "you_side": "left", "right": {}}
    frame = np.zeros((692, 1232, 3), np.uint8)
    count = lambda f, side, prev=0: {"left": 3, "right": 7}[side]
    assert mosaic.garbage_state(d, st, frame, count) == {"side": "right", "rows": 7}
    assert mosaic.garbage_state({**d, "challenge_side": "auto"}, st, frame, count) == {"side": "left", "rows": 3}
    assert mosaic.garbage_state(display_settings({}), st, frame, count) is None
    assert mosaic.garbage_state(d, {**st, "frozen": True}, frame, count) is None
    assert mosaic.garbage_state(d, {**st, "right": {"puyo": True}}, frame, count) is None


def test_tied_to_the_match_time():
    """"time": evenly stronger as the match goes on, the strongest at the
    seconds entered (120 until set)."""
    d = display_settings({"display": {"challenge_mosaic": "time", "challenge_mosaic_max": 90}})
    assert mosaic.strength(d, {"match_elapsed_s": 45}, "left") == 0.5
    assert mosaic.strength(d, {"match_elapsed_s": 200}, "left") == 1.0
    assert mosaic.strength({**d, "challenge_mosaic_max": 0}, {"match_elapsed_s": 60}, "left") == 0.5


def test_counting_garbage_rows_on_a_board_picture():
    """count_garbage (the HUD, 60 a second): grey rows with one hole, from the bottom up."""
    import cv2
    h, w = 460, 231
    img = np.zeros((h, w, 3), np.uint8)
    cw, ch = w / 10, h / 20
    def cell(row, col, bgr):   # row 0 = the bottom
        y = int(h - (row + 1) * ch); x = int(col * cw)
        img[y + 2:int(y + ch) - 2, x + 2:int(x + cw) - 2] = bgr
    for row, hole in enumerate((3, 7, 0)):
        for col in range(10):
            if col != hole:
                cell(row, col, (205, 205, 205))
    cell(3, 4, (40, 40, 220))        # a red block above: not garbage
    assert mosaic.count_garbage(img) == 3
    cell(1, 7, (205, 205, 205))      # a row with no hole isn't one
    assert mosaic.count_garbage(img) == 1


def test_garbage_count_holds_through_a_flash():
    """More rows at once; fewer only once they last GARBAGE_DROP_S (a line
    clear's flash read as no garbage for a moment: the holes showed)."""
    h = mosaic.GarbageHold()
    assert h.update(5, 0.0) == 5
    assert h.update(0, 0.1) == 5 and h.update(0, 0.2) == 5      # the flash
    assert h.update(5, 0.25) == 5
    assert h.update(7, 0.3) == 7                                  # more: at once
    assert h.update(4, 0.4) == 7 and h.update(4, 0.41 + mosaic.GARBAGE_DROP_S) == 4   # dug: after a while


def test_a_flash_over_the_garbage_keeps_it_counted():
    """An attack's flash lights the hole too: below the rows counted before,
    a row that looks full is still garbage (not past them)."""
    h, w = 460, 231
    img = np.zeros((h, w, 3), np.uint8)
    cw, ch = w / 10, h / 20
    def cell(row, col, bgr):
        y = int(h - (row + 1) * ch); x = int(col * cw)
        img[y + 2:int(y + ch) - 2, x + 2:int(x + cw) - 2] = bgr
    for row in range(3):
        for col in range(10):
            cell(row, col, (230, 235, 240) if row == 1 else (205, 205, 205) if col != 4 else (0, 0, 0))
    assert mosaic.count_garbage(img, prev=3) == 3       # row 1 flashed: still garbage
    assert mosaic.count_garbage(img, prev=0) == 1       # nothing counted before: not taken as garbage
