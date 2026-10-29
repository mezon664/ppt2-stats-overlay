"""Opener (開幕テンプレ) detection: wiki shape data, matching rules, and real
frames where the left player had just built パフェ積み / 合掌TSD."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import cv2
import pytest
from capture_profile import compute_profile
from opener_detect import OpenerDetector, load_openers, match_openers

FIXTURES = Path(__file__).resolve().parent / "fixtures"
OPENERS = load_openers()


def board(shape, extra=()):
    rows = [list(r) for r in shape] + [[False] * 10 for _ in range(20 - len(shape))]
    for r, c in extra:
        rows[r][c] = not rows[r][c]
    return rows


def test_every_shape_matches_only_its_own_opener():
    for name, shape in OPENERS:
        assert match_openers(board(shape), OPENERS) == [name]


def test_one_cell_off_is_not_called_anything():
    for name, shape in OPENERS:
        for r in range(len(shape)):
            for c in range(10):
                names = match_openers(board(shape, [(r, c)]), OPENERS)
                assert name not in names


def test_blocks_right_above_the_shape_spoil_it_but_higher_ones_do_not():
    from opener_detect import CLEAR_ROWS_ABOVE
    name, shape = OPENERS[0]
    h = len(shape)
    assert match_openers(board(shape, [(h, 4)]), OPENERS) == []                      # touching the shape
    assert match_openers(board(shape, [(h + CLEAR_ROWS_ABOVE, 4), (18, 4)]), OPENERS) == [name]  # falling piece / sparkles


def detect(fixture, side="left"):
    frame = cv2.imread(str(FIXTURES / fixture))
    det = OpenerDetector(side, compute_profile(frame.shape[1], frame.shape[0]))
    return det.on_placements(frame, 1)


@pytest.mark.parametrize("fixture,name", [
    ("opener_pco_left.jpg", "パフェ積み(中あけ)"),
    ("opener_gassho_left.jpg", "合掌TSD"),
    ("opener_meisou_left.jpg", "迷走砲"),        # live, mirrored, hard-drop sparkles above
    ("opener_gassho_live_left.jpg", "合掌TSD"),  # live, missed when only checked on placements
])
def test_real_frames(fixture, name):
    assert detect(fixture) == name


@pytest.mark.parametrize("fixture,side", [
    ("tsd_left.jpg", "left"), ("play_ice_stage.jpg", "left"), ("play_ice_stage.jpg", "right"),
    ("opener_pco_left.jpg", "right"), ("setend_menu.jpg", "left"),
])
def test_no_opener_on_other_boards(fixture, side):
    assert detect(fixture, side) is None


def test_only_the_first_placements_are_checked():
    from opener_detect import MAX_PLACEMENTS
    frame = cv2.imread(str(FIXTURES / "opener_pco_left.jpg"))
    det = OpenerDetector("left", compute_profile(frame.shape[1], frame.shape[0]))
    det.placements = MAX_PLACEMENTS        # first bag long over (e.g. a mid-match board)
    assert det.on_placements(frame, 1) is None
    assert det.name is None
