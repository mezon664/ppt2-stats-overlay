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
