"""今日の成績 (scripts/session_stats.py): your results since the game was
started — wins / losses from your side, the win streak, averages and the
rating's change in the session."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import opener_stats
import session_stats


def match(t, winner, you=None, apm=50.0, pps=1.5, app=0.5):
    m = {"t": t, "winner": winner,
         "left": {"stats": {"apm": apm, "pps": pps, "app": app}},
         "right": {"stats": {"apm": 10.0, "pps": 1.0, "app": 0.1}}}
    if you:
        m["you"] = you
    return m


def test_results_since_the_game_started():
    matches = [match(50, "left"),                              # before the game started: not counted
               match(100, "left"), match(110, "right"), match(120, "left", apm=70.0),
               match(130, "right", you="right", apm=99.0)]     # you were 2P and won
    s = session_stats.summarize(matches, [], since=100)
    assert (s["wins"], s["losses"], s["matches"], s["win_rate"]) == (3, 1, 4, 75)
    assert s["streak"] == 2                                     # the last two were wins
    assert abs(s["apm"] - (50 + 50 + 70 + 10) / 4) < 1e-9      # your side's numbers (2P's in the last)
    assert s["rating"] is None


def test_a_loss_ends_the_streak():
    s = session_stats.summarize([match(100, "left"), match(110, "right")], [], since=0)
    assert s["streak"] == 0


def test_the_rating_change_in_the_session():
    ratings = [{"t": 10, "league": "puzzle", "rating": 2598},
               {"t": 20, "league": "tetris", "rating": 2500},
               {"t": 120, "league": "puzzle", "rating": 2610},
               {"t": 150, "league": "puzzle", "rating": 2633}]
    r = session_stats.summarize([], ratings, since=100)["rating"]
    assert r == {"league": "puzzle", "before": 2598, "now": 2633, "delta": 35}
    # no rating of that league before the session: from its first one in it
    r = session_stats.rating_change([{"t": 120, "league": "skill", "rating": 980},
                                     {"t": 130, "league": "skill", "rating": 985}], since=100)
    assert r["delta"] == 5


def test_nothing_yet_or_no_game():
    assert session_stats.summarize([match(50, "left")], [], since=100) is None
    assert session_stats.summarize([match(150, "left")], [], since=None) is None


def test_the_lines_shown():
    s = session_stats.summarize([match(100, "left"), match(110, "left")],
                                [{"t": 105, "league": "puzzle", "rating": 2600},
                                 {"t": 115, "league": "puzzle", "rating": 2615}], since=100)
    ja = [t for t, _ in session_stats.lines(s, "ja")]
    assert ja == ["今日の成績", "2勝 0敗  100%", "2連勝中", "レート +15（2615）", "APM 50.0  PPS 1.50  APP 0.50"]
    en = [t for t, _ in session_stats.lines(s, "en")]
    assert en[1] == "2W 0L  100%" and en[3] == "Rating +15 (2615)"


def test_the_side_you_were_is_kept_with_the_match():
    state = {"frozen": True, "match_elapsed_s": 60, "winner": "right", "you_side": "right",
             "left": {}, "right": {}}
    assert opener_stats.match_record(state, now=1)["you"] == "right"
    state["you_side"] = None
    assert "you" not in opener_stats.match_record(state, now=1)
