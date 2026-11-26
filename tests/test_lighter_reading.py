"""The lighter ways of reading a frame give what the old ones did
(2026-11-27: every recording through the pipeline, frame by frame, came out the
same, at under half the time a frame during play)."""
import glob
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import board_read as br  # noqa: E402
import match_boundary as mb  # noqa: E402
from capture_profile import compute_profile, scale_box  # noqa: E402
from image_io import read_image  # noqa: E402

FRAMES = sorted(glob.glob(str(ROOT / "debug_frames" / "burst*" / "*.jpg")) +
                glob.glob(str(ROOT / "debug_frames" / "burst*" / "*.png")))


def old_bright_cells(img, box, v_min=br.CLEAR_V_MIN):
    v = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 2]
    n = 0
    for row in range(br.ROWS):
        for col in range(br.COLS):
            cx, cy = br.cell_center(box, col, row)
            if v[cy - 3:cy + 3, cx - 3:cx + 3].mean() >= v_min:
                n += 1
    return n


def test_bright_cells_count_as_before_on_made_up_boards():
    rng = np.random.default_rng(1)
    for _ in range(20):
        img = rng.integers(0, 256, (693, 1232, 3), dtype=np.uint8)
        for box in (br.LEFT_BOX, br.RIGHT_BOX):
            assert br.count_bright_cells(img, box) == old_bright_cells(img, box)


@pytest.mark.skipif(not FRAMES, reason="recordings not here")
def test_bright_cells_count_as_before_on_recordings():
    for f in FRAMES[::40]:
        img = read_image(f)
        prof = compute_profile(img.shape[1], img.shape[0])
        for b in (br.LEFT_BOX, br.RIGHT_BOX):
            box = scale_box(b, prof)
            assert br.count_bright_cells(img, box) == old_bright_cells(img, box), f


@pytest.mark.skipif(not FRAMES, reason="recordings not here")
def test_the_victory_banner_still_scores_in_full_where_it_shows():
    """Half size first: wherever the full-size score could matter (>= its exit
    level), the half-size one is over the precheck, so the full one is used."""
    for f in FRAMES[::7]:
        img = read_image(f)
        d = mb.MatchBoundaryDetector(compute_profile(img.shape[1], img.shape[0]))
        for w in (d.yatta_window_left, d.yatta_window_right):
            full = max(mb._match(img, t, w) for t in (d.yatta_tmpl, d.yeah_tmpl))
            two = mb._match_two_step(img, (d.yatta_tmpl, d.yeah_tmpl), d._halves, w)
            if full >= mb.YATTA_EXIT:
                assert two == full, f
            else:
                assert two < mb.YATTA_EXIT
