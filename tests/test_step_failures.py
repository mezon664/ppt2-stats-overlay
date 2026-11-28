"""A user's stream: one step failing with an OpenCV error on every frame
stopped every number ("認識処理でエラーが発生しました: error", the match clock
back to 0:00). A failing step is now left out and the rest goes on."""
import sys
from pathlib import Path

import cv2
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import live_pipeline as lp  # noqa: E402

VIDEO = ROOT / "samples" / "PuyoPuyoTetris2 2026-06-07 00-26-52.mp4"


def test_guard_logs_and_goes_on(caplog):
    def boom():
        raise cv2.error("broken")
    lp.FAILURES.clear()
    assert lp._guard("x", boom, default=7) == 7
    assert lp._guard("x", boom) is None and lp.FAILURES["x"] == 2
    assert sum("x failed" in r.message for r in caplog.records) == 1    # (not every frame)
    assert lp._guard("y", lambda a: a + 1, 1) == 2


@pytest.mark.skipif(not VIDEO.exists(), reason="recording not here")
def test_a_side_and_the_opener_failing_leave_the_rest_going(monkeypatch):
    """The right side fails on every frame and the left's opener reading too:
    the left still sends what the game shows (87, test_attack_match) and the
    match clock runs."""
    cap = cv2.VideoCapture(str(VIDEO))
    fps, k = cap.get(cv2.CAP_PROP_FPS), 0
    pipe = lp.MatchPipeline()

    lp.FAILURES.clear()

    def broken():
        raise cv2.error("OpenCV(4.x) error: (-215:Assertion failed)")
    # (on the classes: the sides are built again when the picture's size is known)
    side_frame, on_frame = lp.PlayerPipeline.process_frame, lp.OpenerDetector.on_frame
    monkeypatch.setattr(lp.PlayerPipeline, "process_frame",
                        lambda self, *a: broken() if self.side == "right" else side_frame(self, *a))
    monkeypatch.setattr(lp.OpenerDetector, "on_frame", lambda self, *a, **kw: broken())
    attack, elapsed = None, 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if k % 2 == 0:
            pipe.process_frame(frame, k / fps)
            snap = pipe.snapshot()
            if snap.get("match_screen") and not snap.get("frozen"):
                attack, elapsed = snap["left"]["attack"], snap.get("match_elapsed_s") or 0
        k += 1
    assert attack == 87 and elapsed > 50       # (the match is 55 s)
    assert lp.FAILURES["[right] reading"] > 100 and lp.FAILURES["[left] opener"] > 100
