"""連戦平均 (a user's request): the set's WIN counter read off the screen, and
each player's averages over the set for the summary."""
import glob
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import set_counter  # noqa: E402
import set_stats  # noqa: E402
from capture_profile import compute_profile  # noqa: E402

FRAMES = ROOT / "debug_frames"


def _frame(folder, t):
    from image_io import read_image
    fs = glob.glob(str(FRAMES / folder / "f_*.*"))
    if not fs:
        pytest.skip("recording not here")
    best = min(fs, key=lambda f: abs(float(re.search(r"_t(\d+\.\d+)", f).group(1)) - t))
    frame = read_image(best)
    return frame, compute_profile(frame.shape[1], frame.shape[0])


@pytest.mark.parametrize("folder, t, want", [
    ("burst_boundary", 86.0, ("stars", 0, 0, True)),     # a new set (frame times: the recording's own)
    ("burst_boundary", 94.7, ("stars", 1, 0, False)),    # one won
    ("burst_boundary", 149.5, ("stars", 1, 0, False)),   # マッチポイント
    ("burst_break", 20.0, ("digits", None, None, False)),   # 2★ WIN ★9: not 0-0 (a 9 isn't a 0)
])
def test_the_counter_is_read(folder, t, want):
    frame, profile = _frame(folder, t)
    r = set_counter.read(frame, profile)
    assert r is not None and (r["mode"], r["left"], r["right"], r["zero"]) == want


def test_a_zero_is_told_from_a_nine():
    import cv2
    import numpy as np
    zero = np.zeros((20, 14), np.uint8)
    cv2.ellipse(zero, (7, 10), (5, 8), 0, 0, 360, 255, 3)
    nine = np.zeros((20, 14), np.uint8)
    cv2.circle(nine, (7, 6), 4, 255, 3)
    cv2.line(nine, (10, 6), (9, 18), 255, 3)
    assert set_counter._is_zero(zero)
    assert not set_counter._is_zero(nine)


def _match(t, winner, apm, start):
    return {"t": t, "winner": winner, "match_start_t": start,
            "left": {"stats": {"apm": apm, "pps": 2.0, "tetris": 1}}, "right": {"stats": {"apm": 50.0, "pps": 1.0}}}


def _state(start, elapsed, frozen=False, counter=None, winner=None, apm=None):
    return {"match_start_t": start, "match_reset_count": start, "match_elapsed_s": elapsed, "frozen": frozen,
            "set_counter": counter, "winner": winner,
            "left": {"apm": {"apm": apm}, "pps": 3.0, "match_stats": {"tetris": 2}}, "right": {"apm": {"apm": 70.0}}}


def test_the_set_starts_at_0_0_and_counts_the_match_just_over(tmp_path):
    tr = set_stats.SetTracker(reset_path=tmp_path / "reset.json")
    zero = {"mode": "stars", "left": 0, "right": 0, "zero": True}
    one = {"mode": "stars", "left": 1, "right": 0, "zero": False}
    old = [_match(900, "left", 10.0, 1)]                       # an earlier set
    tr.update(_state(100, 2, counter=zero), old, now=1000)     # 0-0: the set starts here
    history = old + [_match(1060, "left", 80.0, 100)]
    tr.update(_state(200, 2, counter=one), history, now=1070)  # 1-0: the same set
    s = tr.update(_state(200, 50, frozen=True, counter=one, winner="right", apm=100.0), history, now=1120)
    assert s["matches"] == 2 and s["wins"] == {"left": 1, "right": 1}
    assert s["left"]["apm"] == pytest.approx(90.0)            # (80 + 100) / 2, the old set left out
    assert s["left"]["tetris"] == pytest.approx(1.5)
    assert s["right"]["apm"] == pytest.approx(60.0)
    history = history + [_match(1121, "right", 100.0, 200)]   # once kept, not counted twice
    assert tr.update(_state(200, 50, frozen=True, counter=one, winner="right", apm=100.0), history,
                     now=1125)["matches"] == 2


def test_a_long_break_or_the_reset_starts_over(tmp_path):
    tr = set_stats.SetTracker(reset_path=tmp_path / "reset.json")
    history = [_match(1000, "left", 80.0, 1)]
    tr.update(_state(1, 2), history, now=990)
    assert tr.summary(_state(1, 2), history)["matches"] == 1
    tr.update(_state(2, 2), history, now=1000 + set_stats.SET_GAP_S + 60)   # no counter, a long break
    assert tr.summary(_state(2, 2), history) is None
    tr2 = set_stats.SetTracker(reset_path=tmp_path / "reset.json")
    tr2.update(_state(1, 2), history, now=990)
    set_stats.reset_now(tmp_path / "reset.json", now=1001)
    assert tr2.update(_state(1, 2), history, now=1002) is None     # nothing since the reset


def test_the_summary_shows_the_averages_when_asked():
    from config_store import display_settings
    assert display_settings({})["summary_set_average"] is False      # off at first
    sys.path.insert(0, str(ROOT / "hud"))
    from overlay import UI_TEXT
    assert "{n}" in UI_TEXT["ja"]["set_title"] and "{v}" in UI_TEXT["ja"]["set_avg"]
    html = (ROOT / "obs" / "overlay.html").read_text(encoding="utf-8")
    assert "summary_set_average: false" in html and "summary.set = state.set" in html
