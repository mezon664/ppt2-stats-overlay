"""Lines sent over a whole recorded match, checked clear by clear against the
game's own banners and score (the user checked it too, 2026-11-27): left 87,
right 68. Before: two T-SPIN Doubles in a row (the banner shown again while
still up) and a T-SPIN Double whose flash read one row short at first (the
last TETRIS's letters over it) went uncounted — left 73."""
import sys
from pathlib import Path

import cv2
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import live_pipeline as lp  # noqa: E402

VIDEO = ROOT / "samples" / "PuyoPuyoTetris2 2026-06-07 00-26-52.mp4"


@pytest.mark.skipif(not VIDEO.exists(), reason="recording not here")
def test_the_whole_match_sends_what_the_game_shows():
    cap = cv2.VideoCapture(str(VIDEO))
    fps, k = cap.get(cv2.CAP_PROP_FPS), 0
    pipe = lp.MatchPipeline()
    attacks = {}
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if k % 2 == 0:      # (30 a second, about what's read live)
            pipe.process_frame(frame, k / fps)
            snap = pipe.snapshot()
            if snap.get("match_screen") and not snap.get("frozen"):
                attacks = {sd: snap[sd]["attack"] for sd in ("left", "right")}
        k += 1
    assert attacks == {"left": 87, "right": 68}
    left = [e for e in pipe.left.event_log if e.get("lines") is not None]
    assert sum(1 for e in left if "T-SPIN Double" in str(e)) >= 3      # (the three that were missed are among the last)
