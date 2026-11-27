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
    ("burst_set", 20.0, ("digits", 0, 0, True)),            # 0★ WIN ★0: a set starts
    ("burst_set", 60.0, ("digits", 0, None, False)),        # 0★ WIN ★1
    ("burst_set", 280.0, ("digits", None, None, False)),    # 1★ WIN ★4 (a 4 isn't a 0 either)
])
def test_the_counter_is_read(folder, t, want):
    frame, profile = _frame(folder, t)
    r = set_counter.read(frame, profile)
    assert r is not None and (r["mode"], r["left"], r["right"], r["zero"]) == want


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
    assert "tetris" not in s["left"]                          # (only APM, PPS, APP, VS SCORE: user)
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


def test_each_match_keeps_its_set_and_the_stats_group_them(tmp_path):
    """User: the set averages in the stats too. Each match keeps the set it
    was in (its start); the stats group the kept matches by it."""
    import opener_stats
    tr = set_stats.SetTracker(reset_path=tmp_path / "reset.json")
    zero = {"mode": "stars", "left": 0, "right": 0, "zero": True}
    st = _state(100, 2, counter=zero)
    tr.update(st, [], now=1000)
    over = _state(100, 50, frozen=True, counter=zero, winner="left", apm=90.0)
    over["set"] = tr.update(over, [], now=1050)
    rec = opener_stats.match_record(over, now=1051)
    assert rec["set"] == over["set"]["since"]
    def m(t, s, win, apm):
        return {"t": t, "set": s, "winner": win, "left": {"stats": {"apm": apm}}, "right": {"stats": {"apm": 50.0}}}
    sets = set_stats.group_sets([m(10, 5, "left", 80), m(20, 5, "right", 100), m(40, 30, "right", 60),
                                 {"t": 50, "winner": "left", "left": {}, "right": {}}])   # (one kept before: no set)
    assert [s["start"] for s in sets] == [30, 5]                 # newest first
    assert sets[1]["matches"] == 2 and sets[1]["wins"] == {"left": 1, "right": 1}
    assert sets[1]["left"]["apm"] == pytest.approx(90.0)
