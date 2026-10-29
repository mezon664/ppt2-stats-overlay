"""REN breaks from NEXT-queue placements (see queue_tracker.py), driven with
scripted flash/placement timelines shaped like the real recordings: a clearing
piece flashes, then its placement shows up ~0.67s later; a non-clearing piece
shows up as a placement with no flash in between."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import numpy as np
from live_pipeline import PlayerPipeline
from banner_detect import load_templates
from capture_profile import REFERENCE_W, REFERENCE_H

FRAME = np.zeros((REFERENCE_H, REFERENCE_W, 3), dtype=np.uint8)


def scripted(flashes, placements, until, dt=0.05):
    """flashes: {t: lit_rows}; placements: list of t. Returns the pipeline after
    running frames from 0 to `until`."""
    pp = PlayerPipeline(side="left", templates=load_templates())
    state = {"t": 0.0}

    def fake_flash(frame, t):
        for ft, rows in flashes.items():
            if abs(ft - t) < dt / 2:
                pp.flash_detector.last_edge_row_count = rows
                return True
        return False

    def fake_queue(frame, t):
        return [p for p in placements if abs(p - t) < dt / 2]

    pp.flash_detector.update = fake_flash
    pp.queue_tracker.update = fake_queue
    t = 0.0
    while t <= until:
        pp.process_frame(FRAME, round(t, 2))
        t += dt
    return pp


def test_consecutive_clears_build_ren():
    # three clearing pieces in a row: flash, then its placement 0.65s later
    pp = scripted({1.0: 1, 2.0: 1, 3.0: 1}, [1.65, 2.65, 3.65], until=6.0)
    assert pp.tracker.streak.ren_count == 2  # game numbering: 3 in a row = "2 REN"


def test_placement_without_clear_breaks_ren():
    # two clears, then a piece that locks without clearing, then one more clear
    pp = scripted({1.0: 1, 2.0: 1, 4.0: 1}, [1.65, 2.65, 3.2, 4.65], until=7.0)
    assert pp.tracker.streak.consecutive_clears == 1
    assert any(e["label"] == "REN途切れ" for e in pp.event_log)


def test_break_waits_for_the_clear_before_it():
    # The plain clear at t=2.0 only resolves after its 1.5s banner grace
    # (t=3.5), but the non-clearing placement right after it is seen at 3.0.
    # The break must not land before that clear is counted, or the clear
    # would start a new REN instead of ending the old one.
    pp = scripted({1.0: 1, 2.0: 1}, [1.65, 2.65, 3.0], until=5.0)
    assert pp.tracker.streak.consecutive_clears == 0
    labels = [e["label"] for e in reversed(pp.event_log)]
    assert labels == ["1ライン", "1ライン", "REN途切れ"]


def test_lone_clear_then_plain_placement_resets_quietly():
    # REN 0 ending isn't a REN the game ever showed; reset without logging it
    pp = scripted({1.0: 1}, [1.65, 2.0], until=4.0)
    assert pp.tracker.streak.consecutive_clears == 0
    assert [e["label"] for e in pp.event_log] == ["1ライン"]


def test_btb_survives_a_plain_placement():
    pp = scripted({}, [], until=0.1)
    s = pp.tracker.streak
    s.register_clear(pp.table, "clear_4")
    s.register_clear(pp.table, "clear_4")
    s.register_clear(pp.table, None)
    assert s.b2b_streak == 2
