import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import numpy as np
from live_pipeline import MatchPipeline
from board_read import LEFT_BOX, RIGHT_BOX
from capture_profile import REFERENCE_W, REFERENCE_H


class ScriptedGate:
    def __init__(self):
        self.on = True

    def update(self, frame):
        return self.on


def frame_with_pieces():
    f = np.full((REFERENCE_H, REFERENCE_W, 3), 30, dtype=np.uint8)
    for x1, y1, x2, y2 in (LEFT_BOX, RIGHT_BOX):
        f[y1:y2, x1:x2] = (0, 0, 255)
    return f


def blank_frame():
    return np.full((REFERENCE_H, REFERENCE_W, 3), 30, dtype=np.uint8)


def run(mp, gate, on, t0, t1, frame_fn, dt=0.1):
    gate.on = on
    t = t0
    while t < t1 - 1e-9:
        mp.process_frame(frame_fn(), t)
        t += dt
    return t


def test_numbers_hold_while_paused_and_pause_time_is_excluded():
    gate = ScriptedGate()
    mp = MatchPipeline(gate=gate)
    run(mp, gate, True, 0.0, 10.0, frame_with_pieces)
    elapsed_before = mp.snapshot()["match_elapsed_s"]

    run(mp, gate, False, 10.0, 40.0, frame_with_pieces)  # 30s paused
    snap = mp.snapshot()
    assert snap["paused"] is True
    assert snap["match_elapsed_s"] == elapsed_before  # frozen while paused

    run(mp, gate, True, 40.0, 45.0, frame_with_pieces)
    snap = mp.snapshot()
    assert snap["paused"] is False
    # ~10s before + ~5s after; the 30s pause must not be counted
    assert 14.0 <= snap["match_elapsed_s"] <= 15.0


def test_apm_is_not_diluted_by_a_pause():
    gate = ScriptedGate()
    mp = MatchPipeline(gate=gate)
    run(mp, gate, True, 0.0, 30.0, frame_with_pieces)
    mp.left.apm.add_event(mp._last_t, 10)
    apm_before = mp.snapshot()["left"]["apm"]["apm"]

    run(mp, gate, False, 30.0, 90.0, frame_with_pieces)  # a full minute paused
    run(mp, gate, True, 90.0, 90.2, frame_with_pieces)
    apm_after = mp.snapshot()["left"]["apm"]["apm"]
    assert abs(apm_after - apm_before) < 0.5


def test_off_screen_blank_frames_do_not_trigger_a_match_boundary():
    # menus read as "empty boards"; that must not freeze/reset the match
    gate = ScriptedGate()
    mp = MatchPipeline(gate=gate)
    run(mp, gate, True, 0.0, 5.0, frame_with_pieces)
    run(mp, gate, False, 5.0, 15.0, blank_frame)
    assert mp._frozen is False
    assert mp.match_reset_count == 0


def test_apm_uses_the_displayed_clock_without_a_go_anchor():
    # server started mid-match: no GO! to anchor to; ATTACK / TIME must equal APM
    gate = ScriptedGate()
    mp = MatchPipeline(gate=gate)
    run(mp, gate, True, 0.0, 30.0, frame_with_pieces)
    mp.left.apm.add_event(mp._last_t, 9)
    snap = mp.snapshot()
    expected = 9 / (snap["match_elapsed_s"] / 60.0)
    assert abs(snap["left"]["apm"]["apm"] - expected) < 0.5
