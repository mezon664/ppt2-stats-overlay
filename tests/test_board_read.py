import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from board_read import board_is_empty, count_non_empty, EMPTY, GARBAGE, COLS, ROWS


def empty_board():
    return [[EMPTY for _ in range(COLS)] for _ in range(ROWS)]


def board_with_n_filled(n):
    b = empty_board()
    i = 0
    for r in range(ROWS):
        for c in range(COLS):
            if i >= n:
                return b
            b[r][c] = "I"
            i += 1
    return b


def test_fresh_board_is_empty():
    assert board_is_empty(empty_board()) is True


def test_board_within_default_tolerance_still_counts_as_empty():
    # a few misclassified cells (live-capture noise) shouldn't block match-reset
    # detection entirely — see board_is_empty's docstring for why this exists.
    assert board_is_empty(board_with_n_filled(3)) is True


def test_board_beyond_default_tolerance_is_not_empty():
    assert board_is_empty(board_with_n_filled(4)) is False


def test_custom_tolerance_is_honored():
    b = board_with_n_filled(5)
    assert board_is_empty(b, tolerance=5) is True
    assert board_is_empty(b, tolerance=4) is False


def test_board_with_many_pieces_is_not_empty():
    b = empty_board()
    for c in range(COLS):
        b[ROWS - 1][c] = "I"
    assert board_is_empty(b) is False


def test_board_with_garbage_is_not_empty():
    b = board_with_n_filled(0)
    b[ROWS - 1][0] = GARBAGE
    for c in range(1, 5):
        b[ROWS - 1][c] = GARBAGE
    assert board_is_empty(b) is False


def test_count_non_empty():
    assert count_non_empty(empty_board()) == 0
    assert count_non_empty(board_with_n_filled(7)) == 7
