import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from line_clear_detector import LineClearDetector, CHECK_INTERVAL_S
from board_read import EMPTY, COLS, ROWS


def board_with_n_filled(n, label="I"):
    b = [[EMPTY for _ in range(COLS)] for _ in range(ROWS)]
    i = 0
    for r in range(ROWS):
        for c in range(COLS):
            if i >= n:
                return b
            b[r][c] = label
            i += 1
    return b


def feed_stable(det, board, t0, n=2):
    """Feeds the same board n times (>= stable_frames) at the check interval."""
    t = t0
    last = None
    for _ in range(n):
        last = det.update(board, t)
        t += CHECK_INTERVAL_S
    return last, t


def test_first_reading_establishes_baseline_no_event():
    det = LineClearDetector()
    ev, t = feed_stable(det, board_with_n_filled(20), t0=0.0)
    assert ev is None
    assert det._stable_count == 20


def test_piece_placement_detected():
    det = LineClearDetector()
    feed_stable(det, board_with_n_filled(20), t0=0.0)
    ev, t = feed_stable(det, board_with_n_filled(24), t0=1.0)
    assert ev is not None
    assert ev[1] == "place"


def test_single_line_clear_detected():
    det = LineClearDetector()
    feed_stable(det, board_with_n_filled(50), t0=0.0)
    ev, _ = feed_stable(det, board_with_n_filled(40), t0=1.0)
    assert ev == (ev[0], "clear", 1)


def test_tetris_four_line_clear_detected():
    det = LineClearDetector()
    feed_stable(det, board_with_n_filled(80), t0=0.0)
    ev, _ = feed_stable(det, board_with_n_filled(40), t0=1.0)
    assert ev[1] == "clear"
    assert ev[2] == 4


def test_garbage_addition_detected_not_a_placement():
    det = LineClearDetector()
    feed_stable(det, board_with_n_filled(20), t0=0.0)
    ev, _ = feed_stable(det, board_with_n_filled(50), t0=1.0)  # +30 = 3 garbage rows
    assert ev == (ev[0], "garbage", 3)


def test_ambiguous_delta_is_unclassified_not_guessed():
    det = LineClearDetector()
    feed_stable(det, board_with_n_filled(20), t0=0.0)
    ev, _ = feed_stable(det, board_with_n_filled(27), t0=1.0)  # +7: not ~4, not ~10n
    assert ev is None
    assert len(det.unclassified) == 1
    assert det.unclassified[0][1] == 7


def test_unstable_readings_do_not_trigger_events(monkeypatch):
    det = LineClearDetector()
    feed_stable(det, board_with_n_filled(20), t0=0.0)
    # alternate between two values every check — never stable for `stable_frames`
    t = 1.0
    boards = [board_with_n_filled(24), board_with_n_filled(20)]
    for i in range(6):
        ev = det.update(boards[i % 2], t)
        assert ev is None
        t += CHECK_INTERVAL_S


def test_throttled_checks_within_interval_are_skipped():
    det = LineClearDetector()
    feed_stable(det, board_with_n_filled(20), t0=0.0)
    ev1 = det.update(board_with_n_filled(24), 1.0)
    ev2 = det.update(board_with_n_filled(24), 1.0 + CHECK_INTERVAL_S / 2)  # too soon
    assert ev1 is None  # not stable yet (1st reading of the new value)
    assert ev2 is None  # throttled, didn't even sample


def test_multiple_events_accumulate_in_order():
    det = LineClearDetector()
    feed_stable(det, board_with_n_filled(20), t0=0.0)
    feed_stable(det, board_with_n_filled(24), t0=1.0)   # place
    feed_stable(det, board_with_n_filled(14), t0=2.0)   # clear 1
    feed_stable(det, board_with_n_filled(44), t0=3.0)   # garbage 3
    kinds = [e[1] for e in det.events]
    assert kinds == ["place", "clear", "garbage"]
