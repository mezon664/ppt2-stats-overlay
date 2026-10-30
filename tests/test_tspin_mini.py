"""T-SPIN Mini on real live frames: "Mini T-SPIN Single" (a line cleared) is a
tspin_mini clear on either side; "Mini T-SPIN" (no line) is not a clear, only
noted in mini_no_line_events; and the other T-SPIN banners aren't taken for a
Mini."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import cv2
import numpy as np
import pytest
from banner_detect import BannerTracker, load_templates
from capture_profile import compute_profile
from live_pipeline import PlayerPipeline

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def tracker_after(side, fixture):
    frame = cv2.imread(str(FIXTURES / fixture))
    h, w = frame.shape[:2]
    bt = BannerTracker(side, load_templates(), profile=compute_profile(w, h))
    bt.update(frame, 0.0)
    return bt


@pytest.mark.parametrize("side,fixture", [("left", "tsm_single_left.jpg"), ("right", "tsm_single_right.jpg")])
def test_mini_with_a_line_is_a_tspin_mini_clear(side, fixture):
    bt = tracker_after(side, fixture)
    assert [e["clear_type"] for e in bt.attack_events] == ["tspin_mini"]
    assert bt.mini_no_line_events == []


def test_mini_without_a_line_is_not_a_clear():
    bt = tracker_after("left", "tsm_zero_left.jpg")
    assert bt.attack_events == []
    assert bt.mini_no_line_events == [0.0]
    assert bt.streak.consecutive_clears == 0 and bt.streak.b2b_streak == 0


@pytest.mark.parametrize("side,fixture,expected", [
    ("left", "tsd_left.jpg", "tspin_double"), ("left", "tst_left.jpg", "tspin_triple"),
    ("right", "tst_right.jpg", "tspin_triple")])
def test_other_tspins_are_not_taken_for_a_mini(side, fixture, expected):
    bt = tracker_after(side, fixture)
    assert [e["clear_type"] for e in bt.attack_events] == [expected]
    assert bt.mini_no_line_events == []


def test_pipeline_logs_both_kinds():
    """Mini Single backed by a 1-row flash becomes "T-SPIN Mini Single" and
    keeps the Back-to-Back streak going; Mini with no line is logged as
    "T-SPIN Mini" with no attack."""
    def run(fixture, flash_rows):
        frame = cv2.imread(str(FIXTURES / fixture))
        h, w = frame.shape[:2]
        pp = PlayerPipeline(side="left", templates=load_templates(), profile=compute_profile(w, h))
        fired = {"done": False}

        def fake_flash(_frame, _t):
            if flash_rows and not fired["done"]:
                fired["done"] = True
                pp.flash_detector.last_edge_row_count = flash_rows
                return True
            return False
        pp.flash_detector.update = fake_flash
        pp.queue_tracker.update = lambda _f, _t: []
        blank = np.zeros((h, w, 3), dtype=np.uint8)
        pp.process_frame(blank, 0.0)          # the clear flash
        pp.process_frame(frame, 0.3)          # the banner shortly after
        for i in range(1, 30):                # let pending flashes resolve
            pp.process_frame(blank, 0.3 + i * 0.1)
        return pp

    single = run("tsm_single_left.jpg", 1)
    assert [e["label"] for e in single.event_log] == ["T-SPIN Mini Single"]
    assert single.apm.total_lines == 0       # a Mini Single sends nothing on its own
    assert single.tracker.streak.b2b_streak == 1

    none = run("tsm_zero_left.jpg", 0)
    assert [e["label"] for e in none.event_log] == ["T-SPIN Mini"]
    assert none.apm.total_lines == 0
    assert none.tracker.streak.consecutive_clears == 0


@pytest.mark.parametrize("fixture,zero", [("tspin_zero_left.jpg", True), ("tspin_triple_after_zero_left.jpg", False)])
def test_tspin_without_a_line(fixture, zero):
    """A T-SPIN that cleared no line ("T-SPIN" alone on the badge) is reported
    on its own, never as a clear; a line-clearing T-SPIN never as one of those."""
    frame = cv2.imread(str(FIXTURES / fixture))
    h, w = frame.shape[:2]
    bt = BannerTracker("left", load_templates(), profile=compute_profile(w, h))
    bt.update(frame, 1.0)
    bt.update(frame, 1.1)
    assert bool(bt.tspin_no_line_events) == zero
    if zero:
        assert bt.attack_events == []
