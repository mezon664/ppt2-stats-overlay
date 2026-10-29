"""T-SPIN Triple banner recognition on real live frames (both sides), and that a
real T-SPIN Double frame is not mistaken for a Triple (they share one exclusive
group, so only the best-scoring word wins)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import cv2
import pytest
from banner_detect import BannerTracker, load_templates
from capture_profile import compute_profile

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def first_clear(side, fixture):
    frame = cv2.imread(str(FIXTURES / fixture))
    h, w = frame.shape[:2]
    bt = BannerTracker(side, load_templates(), profile=compute_profile(w, h))
    bt.update(frame, 0.0)
    return [e["clear_type"] for e in bt.attack_events]


@pytest.mark.parametrize("side,fixture", [("left", "tst_left.jpg"), ("right", "tst_right.jpg")])
def test_tspin_triple_banner_is_recognized(side, fixture):
    assert first_clear(side, fixture) == ["tspin_triple"]


def test_tspin_double_frame_stays_double():
    assert first_clear("left", "tsd_left.jpg") == ["tspin_double"]
