"""Garbage rows cleared (VS SCORE), read off versus recordings (scripts/mosaic.py DigCounter)."""
import glob
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import mosaic  # noqa: E402
from flash_clear_detector import FlashClearDetector, MAX_LINES_PER_EVENT  # noqa: E402
from image_io import read_image  # noqa: E402


def dug(name, side):
    frames = sorted(glob.glob(str(ROOT / "debug_frames" / name / "*.jpg")) +
                    glob.glob(str(ROOT / "debug_frames" / name / "*.png")))
    if not frames:
        pytest.skip("recording not here")
    det, counter = FlashClearDetector(side), None
    for k, f in enumerate(frames):
        im = read_image(f)
        if counter is None:
            s = im.shape[1] / mosaic.REFERENCE_W
            counter = mosaic.DigCounter(tuple(int(round(v * s)) for v in mosaic.GRID[side]))
        m = re.search(r"_t(\d+\.\d+)", f)
        edge = det.update(im, float(m.group(1)) if m else k / 20)
        real = edge and 1 <= det.last_edge_row_count <= MAX_LINES_PER_EVENT
        counter.update(im, det.last_edge_rows if real else None, det._active)
    return counter.cleared


def test_each_clear_on_the_garbage_counts_what_it_took():
    # 1 (TETRIS over 8 garbage rows, the top one), 2, 4 (TETRIS into 5), 1:
    # every clear looked at frame by frame
    assert dug("burst2", "left") == 8


def test_clears_above_the_garbage_dig_nothing():
    assert dug("burst_ren", "left") == 0        # a REN on top of 4 garbage rows
    assert dug("burst", "left") == 0


def test_counting_starts_from_nothing():
    c = mosaic.DigCounter((0, 0, 10, 20))
    import numpy as np
    assert c.update(np.zeros((40, 40, 3), np.uint8), [0, 1, 2, 3]) == 0
