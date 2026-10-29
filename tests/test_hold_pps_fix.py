"""First-time HOLD use shifts the NEXT queue exactly like a lock does, but
nothing was placed — see scripts/hold_tracker.py and
PlayerPipeline._discard_hold_advance. These drive PlayerPipeline with stubbed
queue_tracker/hold_tracker updates (same technique as test_ren_break.py) to
check the one spurious advance is dropped from both the piece count and the
REN-break logic, without touching any other placement."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import numpy as np
from live_pipeline import PlayerPipeline
from banner_detect import load_templates
from capture_profile import REFERENCE_W, REFERENCE_H

FRAME = np.zeros((REFERENCE_H, REFERENCE_W, 3), dtype=np.uint8)


def scripted(hold_first_use_t, placements, flashes=None, until=3.0, dt=0.05):
    pp = PlayerPipeline(side="left", templates=load_templates())
    flashes = flashes or {}

    def fake_flash(frame, t):
        for ft, rows in flashes.items():
            if abs(ft - t) < dt / 2:
                pp.flash_detector.last_edge_row_count = rows
                return True
        return False

    def fake_queue(frame, t):
        # matches the real NextQueueTracker.update: pieces_placed goes up by
        # the number of advances returned, same call that returns them.
        hits = [p for p in placements if abs(p - t) < dt / 2]
        pp.queue_tracker.pieces_placed += len(hits)
        return hits

    fired = {"done": False}

    def fake_hold(frame, t):
        if not fired["done"] and hold_first_use_t is not None and t >= hold_first_use_t - dt / 2:
            fired["done"] = True
            return hold_first_use_t
        return None

    pp.flash_detector.update = fake_flash
    pp.queue_tracker.update = fake_queue
    pp.hold_tracker.update = fake_hold
    t = 0.0
    while t <= until:
        pp.process_frame(FRAME, round(t, 2))
        t += dt
    return pp


def test_first_hold_advance_is_not_counted_as_a_piece():
    # HOLD confirmed used at t=1.0; the matching queue advance lands at t=1.0 too.
    pp = scripted(hold_first_use_t=1.0, placements=[1.0])
    assert pp.queue_tracker.pieces_placed == 0


def test_first_hold_advance_matched_on_a_later_frame():
    # HoldTracker confirms before queue_tracker reports the matching advance
    # (debounced separately — see the real recording in hold_tracker.py).
    pp = scripted(hold_first_use_t=1.0, placements=[1.2])
    assert pp.queue_tracker.pieces_placed == 0


def test_other_placements_still_count_normally():
    pp = scripted(hold_first_use_t=1.0, placements=[0.5, 1.0, 1.5, 2.0])
    assert pp.queue_tracker.pieces_placed == 3


def test_hold_advance_does_not_break_a_real_ren():
    # Real clear -> placement 0.65s later (per queue_tracker.py's measured
    # delay), a HOLD-caused advance with no flash near it in between, then
    # another real clear -> placement. Without the fix, the un-flashed
    # mid-chain advance (no clear since the previous placement) would wrongly
    # end the REN right there.
    pp = scripted(
        hold_first_use_t=2.3,
        placements=[1.65, 2.3, 3.65],
        flashes={1.0: 1, 3.0: 1},
        until=6.0,
    )
    assert pp.tracker.streak.consecutive_clears == 2
    assert not any(e["label"] == "REN途切れ" for e in pp.event_log)


def test_no_hold_event_leaves_placements_untouched():
    pp = scripted(hold_first_use_t=None, placements=[0.5, 1.0])
    assert pp.queue_tracker.pieces_placed == 2
