import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import numpy as np
from flash_clear_detector import FlashClearDetector, ENTER_RATIO, EXIT_RATIO
from capture_profile import REFERENCE_W, REFERENCE_H
from board_read import LEFT_BOX


def frame_with_left_brightness(ratio):
    """A frame whose LEFT_BOX region has approximately `ratio` fraction of
    near-white pixels, everything else dark."""
    f = np.full((REFERENCE_H, REFERENCE_W, 3), 30, dtype=np.uint8)
    x1, y1, x2, y2 = LEFT_BOX
    w, h = x2 - x1, y2 - y1
    n_white = int(w * h * ratio)
    flat = f[y1:y2, x1:x2].reshape(-1, 3)
    flat[:n_white] = 255
    f[y1:y2, x1:x2] = flat.reshape(h, w, 3)
    return f


def test_no_edge_on_dark_frame():
    det = FlashClearDetector("left")
    assert det.update(frame_with_left_brightness(0.0), 0.0) is False


def test_edge_fires_once_when_crossing_enter_threshold():
    det = FlashClearDetector("left")
    assert det.update(frame_with_left_brightness(ENTER_RATIO / 2), 0.0) is False
    assert det.update(frame_with_left_brightness(ENTER_RATIO + 0.05), 1.0) is True
    # stays bright -> no repeated edge
    assert det.update(frame_with_left_brightness(ENTER_RATIO + 0.05), 2.0) is False


def test_edge_fires_again_after_dropping_below_exit_and_rising_again():
    det = FlashClearDetector("left")
    det.update(frame_with_left_brightness(ENTER_RATIO + 0.05), 0.0)
    det.update(frame_with_left_brightness(EXIT_RATIO / 2), 1.0)  # fades out
    assert det.update(frame_with_left_brightness(ENTER_RATIO + 0.05), 2.0) is True


def test_hysteresis_gap_does_not_reset_on_mid_level_dip():
    det = FlashClearDetector("left")
    det.update(frame_with_left_brightness(ENTER_RATIO + 0.05), 0.0)
    mid = (ENTER_RATIO + EXIT_RATIO) / 2
    assert det.update(frame_with_left_brightness(mid), 1.0) is False  # still "active", no new edge
    assert det.update(frame_with_left_brightness(ENTER_RATIO + 0.05), 2.0) is False  # no re-trigger


def _lit_rows_frame(rows, shift_px):
    """A black reference-size frame with these board rows (0 = top) lit white
    across the left board, the whole picture moved down by shift_px."""
    import numpy as np
    from flash_clear_detector import count_lit_rows  # noqa: F401
    from board_read import LEFT_BOX
    x1, y1, x2, y2 = LEFT_BOX
    frame = np.zeros((692, 1232, 3), np.uint8)
    for r in rows:
        top = int(round(y1 + 11 + r * 23.0 + shift_px))
        frame[top:top + 23, x1:x2] = 255
    return frame


def test_lit_rows_counted_when_the_picture_sits_off_the_bands():
    """A capture board's picture half a row off the bands (user report: a
    TETRIS read as 5 rows and dropped, a T-SPIN Double as 3, a single as 0)."""
    from flash_clear_detector import count_lit_rows
    from board_read import LEFT_BOX
    for shift in (-11.5, -6, 0, 6, 11.5):
        for rows in ([19], [18, 19], [17, 18, 19], [16, 17, 18, 19], [10, 11], [3, 4, 5, 6], [12, 15]):
            frame = _lit_rows_frame(rows, shift)
            assert count_lit_rows(frame, LEFT_BOX) == len(rows), (shift, rows)
