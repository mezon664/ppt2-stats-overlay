import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import numpy as np
from hold_tracker import HoldTracker, HOLD_ICON_BOXES
from capture_profile import REFERENCE_W, REFERENCE_H

PIECE_BGR = (200, 0, 200)  # any saturated color stands in for a piece icon


def frame(filled_side=None):
    f = np.full((REFERENCE_H, REFERENCE_W, 3), 40, dtype=np.uint8)  # dim, low-saturation background
    if filled_side is not None:
        x1, y1, x2, y2 = HOLD_ICON_BOXES[filled_side]
        f[y1:y2, x1:x2] = PIECE_BGR
    return f


def test_empty_hold_reports_nothing():
    tr = HoldTracker("left")
    for t in (0.0, 0.1, 0.2):
        assert tr.update(frame(None), t) is None
    assert not tr.used


def test_first_fill_confirmed_after_stable_reads():
    tr = HoldTracker("right")
    assert tr.update(frame(None), 0.0) is None
    assert tr.update(frame("right"), 0.1) is None  # first filled read, not yet stable
    assert tr.update(frame("right"), 0.2) == 0.1  # confirmed, stamped at first-seen time
    assert tr.used
    assert tr.first_use_t == 0.1


def test_fires_only_once_per_match():
    tr = HoldTracker("left")
    tr.update(frame(None), 0.0)
    tr.update(frame("left"), 0.1)
    assert tr.update(frame("left"), 0.2) == 0.1
    # stays filled (a swap) — no second event
    assert tr.update(frame("left"), 0.3) is None
    assert tr.update(frame("left"), 0.4) is None


def test_single_frame_flicker_does_not_confirm():
    tr = HoldTracker("left")
    tr.update(frame(None), 0.0)
    tr.update(frame("left"), 0.1)   # one filled read
    assert tr.update(frame(None), 0.2) is None  # drops back empty before stable
    assert not tr.used


def test_already_filled_at_start_is_not_a_first_use():
    # tracking began mid-match: HOLD was never seen empty, so no event
    tr = HoldTracker("left")
    for t in (0.0, 0.1, 0.2, 0.3):
        assert tr.update(frame("left"), t) is None
    assert not tr.used


def test_wrong_side_box_is_not_triggered():
    tr = HoldTracker("left")
    for t, s in enumerate(["right", "right", "right"]):
        assert tr.update(frame(s), t * 0.1) is None
    assert not tr.used
