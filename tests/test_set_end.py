"""Live bug (2026-10-29): after the last match of a set, a phantom match
started by itself. Both real set-end frames keep the NEXT queues on screen,
so the gameplay gate is open there; the boundary logic must still not start
a match on them."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import cv2
from capture_profile import compute_profile
from live_pipeline import MatchPipeline, GO_WAIT_TIMEOUT_S

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def load(name):
    return cv2.imread(str(FIXTURES / name))


def frozen_pipeline(frame):
    h, w = frame.shape[:2]
    mp = MatchPipeline(profile=compute_profile(w, h))
    mp.left.apm.add_event(1.0, 4)  # the finished match's numbers
    mp._frozen = True
    return mp


def test_go_like_edge_during_winner_cutscene_does_not_start_a_match(monkeypatch):
    frame = load("setend_winner.jpg")
    mp = frozen_pipeline(frame)
    monkeypatch.setattr(mp.boundary_detector, "update", lambda f, t: (False, t >= 12.0))
    t = 10.0
    while t < 13.0:
        mp.process_frame(frame, t)
        t += 0.1
    assert mp._frozen is True
    assert mp.match_reset_count == 0
    assert mp.left.apm.total_events == 1


def test_waiting_on_the_set_end_menu_never_starts_a_match():
    frame = load("setend_menu.jpg")
    mp = frozen_pipeline(frame)
    # as if the fallback had seen a countdown-like empty -> filled sequence
    mp._fallback_saw_empty_since_freeze = True
    mp.process_frame(frame, 10.0)
    assert mp._awaiting_go_since == 10.0
    t = 10.0
    while t < 10.0 + GO_WAIT_TIMEOUT_S * 2:
        t += 0.1
        mp.process_frame(frame, t)
    assert mp._frozen is True
    assert mp.match_reset_count == 0
    assert mp.snapshot()["frozen"] is True


def test_server_started_on_the_set_end_menu_counts_nothing():
    """Live bug: the server started on this menu ran the match clock."""
    frame = load("setend_menu.jpg")
    h, w = frame.shape[:2]
    mp = MatchPipeline(profile=compute_profile(w, h), wait_for_start=True)
    t = 0.0
    while t < 30.0:
        mp.process_frame(frame, t)
        t += 0.1
    snap = mp.snapshot()
    assert snap["match_elapsed_s"] == 0
    assert snap["waiting_start"] is True
    assert snap["frozen"] is False


def test_server_started_mid_match_starts_once_the_queues_move():
    frame = load("setend_menu.jpg")
    h, w = frame.shape[:2]
    mp = MatchPipeline(profile=compute_profile(w, h), wait_for_start=True)
    mp._count_queue_advances = lambda f, t: 1  # as if pieces were being placed
    for i in range(5):
        mp.process_frame(frame, i * 0.1)
    assert mp.snapshot()["waiting_start"] is False
    assert mp.start_t is not None
