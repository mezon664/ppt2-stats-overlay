"""Perfect Clear: the banner on real frames (left/right, two stages), and how
it turns the clear just before it into a fixed 10-line attack."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import cv2
import pytest
from banner_detect import BannerTracker, load_templates
from capture_profile import compute_profile
from live_pipeline import PlayerPipeline

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def pc_active(side, fixture):
    frame = cv2.imread(str(FIXTURES / fixture))
    h, w = frame.shape[:2]
    bt = BannerTracker(side, load_templates(), profile=compute_profile(w, h))
    bt.update(frame, 0.0)
    return bt.states["perfect_clear"].active, bt.attack_events


@pytest.mark.parametrize("side,fixture", [
    ("left", "pc_left.jpg"),          # 2-line PC (3rd clear of a REN chain)
    ("left", "pc_tetris_left.jpg"),   # TETRIS PC, another stage
    ("right", "pc_right.jpg"),        # opponent's PC, another stage
])
def test_perfect_clear_banner_is_recognized(side, fixture):
    active, events = pc_active(side, fixture)
    assert active is True
    # the PC banner marks a clear; it is not a clear event by itself
    assert all(e["raw_label"] != "perfect_clear" for e in events)


@pytest.mark.parametrize("side,fixture", [
    ("left", "tsd_left.jpg"), ("right", "pc_left.jpg"), ("left", "pc_right.jpg"),
    ("left", "setend_winner.jpg"), ("left", "play_sky_stage.jpg"),
])
def test_no_perfect_clear_banner_elsewhere(side, fixture):
    active, _ = pc_active(side, fixture)
    assert active is False


def player():
    return PlayerPipeline(side="left", templates=load_templates())


def test_pc_goes_to_the_latest_clear_before_the_banner():
    """In a REN chain several clears fall inside the time window; only the
    last one emptied the board."""
    p = player()
    p._pending_flashes = [{"flash_t": 20.0, "n_lines": 2}, {"flash_t": 21.0, "n_lines": 1}]
    p._on_pc_edge(21.3)
    assert not p._pending_flashes[0].get("perfect_clear")
    assert p._pending_flashes[1].get("perfect_clear") is True

    p._resolve_pending_flashes(30.0)
    lines = [e["lines"] for e in p.event_log]          # newest first
    assert lines[0] == 10                              # the PC clear
    assert p.event_log[0]["text"].startswith("PERFECT CLEAR（1ライン）")
    assert p.apm.total_lines == 10 + p.event_log[1]["lines"]
    assert p.perfect_clear_count == 1


def test_already_counted_banner_clear_is_upgraded_to_10():
    """A TETRIS banner can be confirmed before the PC banner shows."""
    p = player()
    ev = {"clear_type": "clear_4", "btb": True, "ren_count": 0, "ren_source": "estimated"}
    p._emit_attack_event(56.6, ev, 5, {"base": 4, "btb": 1, "ren": 0, "total": 5})
    assert p.apm.total_lines == 5
    p._on_pc_edge(56.9)
    assert p.apm.total_lines == 10
    assert p.event_log[0]["lines"] == 10
    assert p.event_log[0]["text"] == "PERFECT CLEAR（TETRIS） +10段"
    assert p.perfect_clear_count == 1


def test_pc_banner_without_a_clear_is_not_counted():
    p = player()
    p._on_pc_edge(10.0)
    p._resolve_pending_flashes(20.0)
    assert p.apm.total_lines == 0
    assert p.perfect_clear_count == 0
