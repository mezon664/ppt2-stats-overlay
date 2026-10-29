import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from apm_tracker import APMWindowTracker


def test_window_sum_basic():
    tr = APMWindowTracker(windows_s=(10, 30, 60))
    tr.add_event(0, 4)
    tr.add_event(5, 2)
    tr.add_event(12, 1)
    assert tr.window_sum(12, 10) == 3  # events at t=5(2) and t=12(1); t=0 is 12s ago, excluded
    assert tr.window_sum(12, 30) == 7  # all three


def test_window_apm_rate_normalization():
    tr = APMWindowTracker(windows_s=(10,))
    tr.add_event(0, 5)
    # 5 lines in a 10s window -> 30 lines/min equivalent
    assert tr.window_apm(0, 10) == 30.0


def test_old_events_evicted():
    tr = APMWindowTracker(windows_s=(10, 60))
    tr.add_event(0, 10)
    tr.add_event(100, 1)  # far later; eviction keeps buffer bounded
    assert tr.window_sum(100, 60) == 1
    assert len(tr.events) == 1


def test_peak_apm_tracks_maximum():
    tr = APMWindowTracker(windows_s=(10,))
    tr.add_event(0, 6)   # apm=36
    tr.add_event(1, 1)   # window now has both -> apm=42
    tr.add_event(20, 1)  # old ones evicted, apm=6
    assert tr.peak_apm[10] >= 42.0


def test_snapshot_shape():
    tr = APMWindowTracker(windows_s=(10, 30))
    tr.add_event(0, 4)
    snap = tr.snapshot(5)
    assert set(snap["windows"].keys()) == {"10", "30"}
    assert snap["total_lines"] == 4
    assert snap["total_events"] == 1
    assert snap["match_elapsed_s"] == 5


# --- overall_apm: user's own worked example (60 lines over a 2-minute match = 30 APM) ---
def test_overall_apm_matches_user_worked_example():
    tr = APMWindowTracker()
    tr.add_event(0, 60)
    assert tr.overall_apm(120) == 30.0


def test_overall_apm_accumulates_across_multiple_events():
    tr = APMWindowTracker()
    tr.add_event(0, 20)
    tr.add_event(30, 40)
    assert tr.overall_apm(120) == 30.0  # still 60 total lines / 2 min


def test_overall_apm_guarded_against_near_zero_elapsed_time():
    tr = APMWindowTracker()
    tr.add_event(0.1, 4)
    # without a guard this would read as 4 / (0.0001 min) = ~2400 APM
    assert tr.overall_apm(0.2) == 0.0


def test_overall_apm_zero_before_any_event():
    tr = APMWindowTracker()
    assert tr.overall_apm(100) == 0.0


def test_snapshot_includes_overall_apm():
    tr = APMWindowTracker()
    tr.add_event(0, 60)
    snap = tr.snapshot(120)
    assert snap["apm"] == 30.0
