import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import numpy as np
from live_pipeline import MatchPipeline, EMPTY_CHECK_INTERVAL_S, EMPTY_CONFIRM_COUNT, NONEMPTY_CONFIRM_COUNT
from board_read import LEFT_BOX, RIGHT_BOX
from capture_profile import REFERENCE_W, REFERENCE_H


class AlwaysOnScreen:
    """Synthetic frames have no NEXT labels, so the real gameplay gate would
    treat every one of them as a menu; these tests are about boundary logic."""
    def update(self, frame):
        return True


def blank_frame():
    # dark background everywhere -> every cell reads EMPTY
    return np.full((REFERENCE_H, REFERENCE_W, 3), 30, dtype=np.uint8)


def frame_with_pieces():
    f = blank_frame()
    # fill both playfields with a bright saturated color -> non-empty cells
    for box in (LEFT_BOX, RIGHT_BOX):
        x1, y1, x2, y2 = box
        f[y1:y2, x1:x2] = (0, 0, 255)  # saturated red (BGR)
    return f


def feed(pipeline, frame_fn, t0, n):
    """Feeds n board-boundary checks, each EMPTY_CHECK_INTERVAL_S apart."""
    t = t0
    for _ in range(n):
        pipeline._check_match_boundary(frame_fn(), t)
        t += EMPTY_CHECK_INTERVAL_S
    return t


def test_match_freezes_on_sustained_empty_boards_without_resetting_yet():
    mp = MatchPipeline(gate=AlwaysOnScreen())
    mp.left.apm.add_event(1.0, 4)  # simulate a concluded match's history

    feed(mp, blank_frame, t0=10.0, n=EMPTY_CONFIRM_COUNT)

    assert mp._frozen is True
    assert mp.match_reset_count == 0          # not reset yet — just frozen
    assert mp.left.apm.total_events == 1       # history preserved (frozen, not wiped)


def test_no_freeze_without_enough_consecutive_empty_confirmations():
    mp = MatchPipeline(gate=AlwaysOnScreen())
    feed(mp, blank_frame, t0=10.0, n=EMPTY_CONFIRM_COUNT - 1)
    assert mp._frozen is False


def test_pieces_reappearing_after_freeze_only_marks_a_possible_next_match():
    """Boards empty -> filled again looks like the next match's countdown, but
    the set-end cut-scene can look the same: nothing is reset until GO!."""
    mp = MatchPipeline(gate=AlwaysOnScreen())
    mp.left.apm.add_event(1.0, 4)

    t = feed(mp, blank_frame, t0=10.0, n=EMPTY_CONFIRM_COUNT)
    assert mp._frozen is True

    feed(mp, frame_with_pieces, t0=t, n=NONEMPTY_CONFIRM_COUNT)

    assert mp._frozen is True
    assert mp.match_reset_count == 0
    assert mp._awaiting_go_since is not None
    assert mp.left.apm.total_events == 1       # last match's numbers still shown


def test_process_frame_does_not_advance_last_t_while_frozen():
    mp = MatchPipeline(gate=AlwaysOnScreen())
    mp.process_frame(frame_with_pieces(), 1.0)
    mp.left.apm.add_event(1.0, 4)

    # feed enough empty frames through process_frame (not just the raw boundary
    # check) to confirm freezing, each spaced out so the throttle doesn't skip them.
    # last_t keeps advancing during the EMPTY_CONFIRM_COUNT-frame debounce window
    # itself (by design — a ~1-1.5s grace period before freezing fully engages,
    # so a single-frame flash doesn't falsely freeze mid-match); what must NOT
    # happen is it continuing to advance once frozen is actually confirmed.
    t = 10.0
    for _ in range(EMPTY_CONFIRM_COUNT):
        mp.process_frame(blank_frame(), t)
        t += EMPTY_CHECK_INTERVAL_S
    assert mp._frozen is True
    frozen_last_t = mp._last_t

    for _ in range(5):
        mp.process_frame(blank_frame(), t)
        t += EMPTY_CHECK_INTERVAL_S

    # last_t must NOT keep advancing once frozen — that's what keeps APM/elapsed
    # time from decaying while the result screen sits idle.
    assert mp._last_t == frozen_last_t


def test_process_frame_resumes_advancing_last_t_only_once_go_disappears(monkeypatch):
    mp = MatchPipeline(gate=AlwaysOnScreen())
    mp.process_frame(frame_with_pieces(), 1.0)
    mp.left.apm.add_event(1.0, 4)

    t = 10.0
    mp.process_frame(blank_frame(), t)
    assert mp._frozen is True

    # countdown: still frozen on the old numbers, nothing reset yet
    for _ in range(10):
        t += 0.1
        mp.process_frame(frame_with_pieces(), t)
    snap = mp.snapshot()
    assert snap["frozen"] is True
    assert snap["waiting_start"] is True
    assert mp.match_reset_count == 0

    # GO! disappears (boards were empty ~1s earlier): reset and play start here
    go_t = t + 0.1
    monkeypatch.setattr(mp.boundary_detector, "update", lambda frame, tt: (False, tt == go_t))
    mp.process_frame(frame_with_pieces(), go_t)
    assert mp.match_reset_count == 1
    assert mp.start_t == go_t
    assert mp.left.apm.match_start_t == go_t
    assert mp.left.apm.total_events == 0
    mp.process_frame(frame_with_pieces(), go_t + 2.0)
    snap = mp.snapshot()
    assert snap["frozen"] is False
    assert snap["waiting_start"] is False
    assert snap["match_elapsed_s"] == 2.0


def test_go_like_edge_without_empty_boards_before_it_is_ignored(monkeypatch):
    """Live bug (2026-10-29): the set-end "WINNER!" cut-scene's orange
    artwork faded out like GO! and started a phantom match."""
    mp = MatchPipeline(gate=AlwaysOnScreen())
    mp.left.apm.add_event(1.0, 4)
    mp._frozen = True
    monkeypatch.setattr(mp.boundary_detector, "update", lambda frame, tt: (False, tt == 20.0))
    t = 10.0
    while t < 20.05:
        mp.process_frame(frame_with_pieces(), t)
        t = round(t + 0.1, 2)
    assert mp._frozen is True
    assert mp.match_reset_count == 0
    assert mp.left.apm.total_events == 1


def test_go_edge_long_after_the_boards_were_empty_is_ignored(monkeypatch):
    from live_pipeline import GO_EMPTY_LOOKBACK_S
    mp = MatchPipeline(gate=AlwaysOnScreen())
    mp._frozen = True
    mp.process_frame(blank_frame(), 10.0)
    go_t = 10.0 + GO_EMPTY_LOOKBACK_S + 1.0
    monkeypatch.setattr(mp.boundary_detector, "update", lambda frame, tt: (False, tt == go_t))
    mp.process_frame(frame_with_pieces(), 10.5)
    mp.process_frame(frame_with_pieces(), go_t)
    assert mp._frozen is True
    assert mp.match_reset_count == 0


def test_no_freeze_when_only_one_side_is_empty():
    mp = MatchPipeline(gate=AlwaysOnScreen())

    def half_empty():
        f = blank_frame()
        x1, y1, x2, y2 = RIGHT_BOX
        f[y1:y2, x1:x2] = (0, 0, 255)  # right side still has pieces
        return f

    feed(mp, half_empty, t0=10.0, n=EMPTY_CONFIRM_COUNT + 2)
    assert mp._frozen is False


def test_freeze_while_board_still_nonempty_does_not_immediately_unfreeze():
    """Regression test for a confirmed live bug: freezing via the victory banner
    happens while the loser's board is STILL showing its final (non-empty) state
    — the board doesn't clear to empty until later, during the celebration. The
    fallback's "frozen + board non-empty -> a new match must have started, reset"
    check doesn't know WHY we're frozen, so without a guard it fired on the very
    next check and undid the freeze within milliseconds of setting it. Simulates
    the banner-triggered freeze directly (board_boundary's template matching
    isn't exercised here — see test_match_boundary.py for that), then checks the
    fallback alone doesn't unfreeze while the board is simply still showing
    pre-clear content."""
    mp = MatchPipeline(gate=AlwaysOnScreen())
    mp.left.apm.add_event(1.0, 4)

    # simulate what MatchBoundaryDetector's victory_edge does: freeze immediately,
    # with the board NOT empty yet (the loser's final state is still on screen).
    mp._frozen = True
    mp._fallback_saw_empty_since_freeze = False

    # the fallback's board-empty check now runs against a still-non-empty board —
    # must NOT interpret this as "a new match started".
    feed(mp, frame_with_pieces, t0=10.0, n=NONEMPTY_CONFIRM_COUNT + 2)

    assert mp._frozen is True
    assert mp.match_reset_count == 0
    assert mp.left.apm.total_events == 1  # history still preserved, not wiped


def test_freeze_then_board_clears_then_pieces_reappear_waits_for_go():
    """Once the board has gone empty during this freeze, pieces reappearing
    marks a possible next match (and only then)."""
    mp = MatchPipeline(gate=AlwaysOnScreen())
    mp.left.apm.add_event(1.0, 4)
    mp._frozen = True
    mp._fallback_saw_empty_since_freeze = False

    t = feed(mp, frame_with_pieces, t0=10.0, n=2)
    assert mp._awaiting_go_since is None

    t = feed(mp, blank_frame, t0=t, n=EMPTY_CONFIRM_COUNT)
    assert mp._fallback_saw_empty_since_freeze is True

    feed(mp, frame_with_pieces, t0=t, n=NONEMPTY_CONFIRM_COUNT)
    assert mp._awaiting_go_since is not None
    assert mp._frozen is True
    assert mp.match_reset_count == 0


def test_reset_via_go_disappeared_anchors_clock_precisely(monkeypatch):
    """User's explicit concern: regardless of when the on-screen reset/zeroing
    happens (even if it visually lines up with "レディー"), the APM calculation's
    OWN elapsed-time clock must start counting from the precise instant "ゴー!"
    disappears — not from whenever the next frame happens to land, and not from
    whenever the first attack of the new match happens to occur (which would
    quietly exclude the dead time between GO! and that first attack)."""
    mp = MatchPipeline(gate=AlwaysOnScreen())
    mp._frozen = True

    # simulate boundary_detector reporting a go_disappeared_edge at a known t
    def fake_update(frame, t):
        return False, True

    monkeypatch.setattr(mp.boundary_detector, "update", fake_update)

    go_disappear_t = 42.37
    mp._check_match_boundary(blank_frame(), go_disappear_t)

    assert mp.start_t == go_disappear_t
    assert mp.left.apm.match_start_t == go_disappear_t
    assert mp.right.apm.match_start_t == go_disappear_t

    # a later attack must NOT shift the clock to itself
    later_t = go_disappear_t + 5.0
    mp.left.apm.add_event(later_t, 4)
    assert mp.left.apm.match_start_t == go_disappear_t
    assert mp.left.apm.overall_apm(later_t) == 4 / (5.0 / 60.0)


def test_nothing_is_counted_during_the_countdown(monkeypatch):
    """User's request: the match starts when GO! disappears. A flash during
    the countdown must not reach the trackers."""
    mp = MatchPipeline(gate=AlwaysOnScreen())
    mp._frozen = True
    mp._fallback_saw_empty_since_freeze = True
    mp.process_frame(frame_with_pieces(), 10.0)
    assert mp._awaiting_go_since == 10.0

    fed = []
    monkeypatch.setattr(mp.left, "process_frame", lambda f, t: fed.append(t))
    for i in range(20):
        mp.process_frame(frame_with_pieces(), 10.1 + i * 0.1)
    assert fed == []


def run_waiting(mp, seconds, advances_per_frame=0, frame_fn=frame_with_pieces):
    mp._frozen = True
    mp._fallback_saw_empty_since_freeze = True
    mp.process_frame(frame_fn(), 10.0)
    assert mp._awaiting_go_since == 10.0
    mp._count_queue_advances = lambda frame, t: advances_per_frame
    t = 10.0
    while t < 10.0 + seconds:
        t += 0.1
        mp.process_frame(frame_fn(), t)


def test_match_starts_without_go_once_queues_move_after_the_timeout():
    from live_pipeline import GO_WAIT_TIMEOUT_S
    mp = MatchPipeline(gate=AlwaysOnScreen())
    run_waiting(mp, GO_WAIT_TIMEOUT_S + 0.5, advances_per_frame=1)
    snap = mp.snapshot()
    assert snap["frozen"] is False
    assert snap["waiting_start"] is False
    assert mp.match_reset_count == 1
    assert snap["match_elapsed_s"] > 0


def test_no_match_starts_on_a_static_screen_even_after_the_timeout():
    """The set-end menu keeps full, static NEXT queues on screen: waiting
    must not turn into a phantom match there."""
    from live_pipeline import GO_WAIT_TIMEOUT_S
    mp = MatchPipeline(gate=AlwaysOnScreen())
    mp.left.apm.add_event(1.0, 4)
    run_waiting(mp, GO_WAIT_TIMEOUT_S * 3, advances_per_frame=0)
    assert mp._frozen is True
    assert mp.match_reset_count == 0
    assert mp.left.apm.total_events == 1


def test_snapshot_reports_frozen_state():
    mp = MatchPipeline(gate=AlwaysOnScreen())
    mp.process_frame(frame_with_pieces(), 1.0)
    assert mp.snapshot()["frozen"] is False

    t = 10.0
    for _ in range(EMPTY_CONFIRM_COUNT):
        mp.process_frame(blank_frame(), t)
        t += EMPTY_CHECK_INTERVAL_S
    assert mp.snapshot()["frozen"] is True


class ScriptedGate:
    """On screen except between the given capture times (a pause menu and
    the countdown, where the queues are empty)."""
    def __init__(self, closed_from, closed_to):
        self.closed = (closed_from, closed_to)
        self.t = 0.0
        self.last_reason = None

    def update(self, frame):
        off = self.closed[0] <= self.t < self.closed[1]
        self.last_reason = "pause" if off else None
        return not off


def run_with_gate(mp, gate, go_t, t_end, monkeypatch):
    # (the detector is given game time, which leaves the pause out: go by capture time here)
    monkeypatch.setattr(mp.boundary_detector, "update", lambda frame, tt: (False, abs(gate.t - go_t) < 1e-6))
    t = 10.0
    while t < t_end:
        gate.t = t
        mp.process_frame(frame_with_pieces(), t)
        t = round(t + 0.1, 2)


def test_start_over_from_the_pause_menu_starts_a_new_match(monkeypatch):
    """User: opener names stopped showing — "Start Over" mid-match shows a
    countdown and GO!, but the GO! was ignored (not frozen, no empty boards
    seen), so the old match went on and the opening wasn't looked at."""
    gate = ScriptedGate(15.0, 22.0)            # pause menu, then the countdown
    mp = MatchPipeline(gate=gate)
    mp.left.apm.add_event(11.0, 4)
    run_with_gate(mp, gate, 24.4, 25.0, monkeypatch)   # GO! gone ~2.4 s after the countdown
    assert mp.match_reset_count == 1
    assert mp.left.apm.total_events == 0


def test_a_short_flicker_then_a_go_like_edge_mid_match_is_not_a_restart(monkeypatch):
    gate = ScriptedGate(15.0, 15.3)            # the gate blinks for a moment
    mp = MatchPipeline(gate=gate)
    mp.left.apm.add_event(11.0, 4)
    run_with_gate(mp, gate, 16.0, 17.0, monkeypatch)
    assert mp.match_reset_count == 0
    assert mp.left.apm.total_events == 1


def test_resuming_from_pause_without_go_keeps_the_match(monkeypatch):
    gate = ScriptedGate(15.0, 22.0)
    mp = MatchPipeline(gate=gate)
    mp.left.apm.add_event(11.0, 4)
    run_with_gate(mp, gate, -1.0, 26.0, monkeypatch)   # no GO! at all
    assert mp.match_reset_count == 0
    assert mp.left.apm.total_events == 1
