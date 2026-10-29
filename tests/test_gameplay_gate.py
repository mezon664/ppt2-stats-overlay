import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import cv2
import numpy as np
import pytest
from gameplay_gate import GameplayGate, NEXT_TEMPLATE_PATH, NEXT_WINDOWS, QUEUE_SLOTS
from capture_profile import REFERENCE_W, REFERENCE_H, compute_profile

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def synthetic_frame(label_sides, queue_filled=True):
    f = np.full((REFERENCE_H, REFERENCE_W, 3), 120, dtype=np.uint8)
    tmpl = cv2.imread(str(NEXT_TEMPLATE_PATH))
    th, tw = tmpl.shape[:2]
    for side in label_sides:
        x1, y1, _, _ = NEXT_WINDOWS[side]
        lx, ly = x1 + 15, y1 + 10
        f[ly:ly + th, lx:lx + tw] = tmpl
        for a, b, c, d in QUEUE_SLOTS:
            f[ly + b:ly + d, lx + a:lx + c] = (0, 0, 220) if queue_filled else (10, 10, 10)
    return f


def test_menu_like_frame_is_not_on_screen():
    gate = GameplayGate()
    assert gate.update(synthetic_frame([])) is False
    assert gate.last_reason == "no_match_ui"


def test_both_labels_with_pieces_is_on_screen():
    assert GameplayGate().update(synthetic_frame(["left", "right"])) is True


def test_one_label_is_enough():
    # the HUD overlay can cover the left label in the capture; the right one
    # alone must still count as being in a match
    assert GameplayGate().update(synthetic_frame(["right"])) is True


def test_empty_queue_is_the_pause_screen():
    gate = GameplayGate()
    assert gate.update(synthetic_frame(["left", "right"], queue_filled=False)) is False
    assert gate.last_reason == "pause"


@pytest.mark.parametrize("name,expected,reason", [
    ("play_ice_stage.jpg", True, None),
    ("play_sky_stage.jpg", True, None),
    ("pause_candy_stage.jpg", False, "pause"),
    ("pause_school_stage.jpg", False, "pause"),
    ("menu_main.jpg", False, "no_match_ui"),
])
def test_real_frames(name, expected, reason):
    frame = cv2.imread(str(FIXTURES / name))
    gate = GameplayGate(compute_profile(frame.shape[1], frame.shape[0]))
    assert gate.update(frame) is expected
    assert gate.last_reason == reason
