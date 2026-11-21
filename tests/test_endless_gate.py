"""開幕テンプレ練習 runs only in マラソン with エンドレス ON (scripts/endless_gate.py)."""
import glob
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from endless_gate import EndlessGate  # noqa: E402
from image_io import read_image  # noqa: E402

FRAMES = sorted(glob.glob(str(ROOT / "debug_frames" / "burst_marathon_endless" / "*.jpg")))


def test_nothing_seen_is_not_allowed():
    assert EndlessGate().update(np.zeros((693, 1232, 3), np.uint8)) is False


def test_a_setting_is_forgotten_after_another_mode():
    gate = EndlessGate()
    gate.endless = True
    for _ in range(20):
        gate.update(np.zeros((693, 1232, 3), np.uint8), match_screen=True)
    assert gate.endless is None


@pytest.mark.skipif(not FRAMES, reason="recording not here")
def test_recording_endless_on():
    gate = EndlessGate()
    seen = [(gate.update(read_image(f)), gate.endless) for f in FRAMES[::3]]
    assert all(e is True for _, e in seen)
    assert any(a for a, _ in seen) and not seen[0][0]
