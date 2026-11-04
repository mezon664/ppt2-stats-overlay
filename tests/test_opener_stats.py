"""Opener use and win rate over the last N matches (scripts/opener_stats.py,
the settings window's 開幕の統計 tab)."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hud"))

from PyQt6 import QtWidgets

import opener_stats
from opener_stats import match_record, tally

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def m(left, right, winner, puyo=None):
    side = lambda name, sd: {"puyo": True} if puyo == sd else {"opener": name, "opener_en": name and name + "_en"}
    return {"t": 0, "winner": winner, "left": side(left, "left"), "right": side(right, "right")}


def test_only_a_finished_match_with_a_winner_is_kept():
    st = {"frozen": True, "match_elapsed_s": 60.0, "winner": "left", "match_start_t": 5.0,
          "left": {"opener": "迷走砲", "opener_en": "Meisou"}, "right": {"puyo": True}}
    rec = match_record(st, now=100)
    assert rec["winner"] == "left" and rec["left"]["opener"] == "迷走砲" and rec["right"] == {"puyo": True}
    assert match_record({**st, "winner": None}) is None             # left midway: no winner
    assert match_record({**st, "match_elapsed_s": 0}) is None       # cleared by a blackout
    assert match_record({**st, "frozen": False}) is None


def test_use_and_win_rate_over_the_last_n():
    ms = [m("A", "B", "left"), m("A", "C", "right"), m("B", "A", "left"), m(None, "A", "left")]
    rows, plays, n = tally(ms, 10, "left")
    assert rows == [("A", 2, 1), ("B", 1, 1), (None, 1, 1)] and plays == 4 and n == 4
    rows, plays, n = tally(ms, 2, "left")                           # only the newest two
    assert rows == [("B", 1, 1), (None, 1, 1)] and n == 2
    rows, _, _ = tally(ms, 10, "both")
    assert rows[0] == ("A", 4, 1)
    rows, _, _ = tally(ms, 10, "left", english=True)
    assert rows[0] == ("A_en", 2, 1)


def test_against_tetris_and_against_puyo_apart():
    ms = [m("A", "B", "left"), m("A", None, "left", puyo="right"), m("B", None, "right", puyo="right"),
          m(None, "C", "right", puyo="left")]
    rows, plays, n = tally(ms, 10, "left", opponent="tetris")
    assert rows == [("A", 1, 1)] and n == 1
    rows, plays, n = tally(ms, 10, "left", opponent="puyo")
    assert rows == [("A", 1, 1), ("B", 1, 0)] and n == 2
    rows, plays, n = tally(ms, 1, "left", opponent="puyo")          # the last 1 match against Puyo
    assert rows == [("B", 1, 0)]
    rows, _, _ = tally(ms, 10, "right", opponent="puyo")            # 2P against a Puyo 1P
    assert rows == [("C", 1, 1)]


def test_kept_once_and_only_the_newest(tmp_path, monkeypatch):
    path = tmp_path / "h.json"
    monkeypatch.setattr(opener_stats, "KEEP", 3)
    rec = {**m("A", "B", "left"), "match_start_t": 5.0, "t": 100}
    assert opener_stats.add(rec, path) and not opener_stats.add(rec, path)   # the same match once
    for i in range(5):
        opener_stats.add({**rec, "match_start_t": 10.0 + i}, path)
    assert len(opener_stats.load(path)) == 3
    opener_stats.clear(path)
    assert opener_stats.load(path) == []


def test_the_hud_records_a_match_as_it_ends(tmp_path, monkeypatch):
    monkeypatch.setattr(opener_stats, "HISTORY_PATH", tmp_path / "h.json")
    import overlay
    settings = overlay.load_settings()
    settings["hud"]["follow_game"] = False
    overlay.WsClient.start = lambda self: None
    win = overlay.HudWindow(settings)
    seen = []
    win.opener_recorded.connect(lambda: seen.append(1))
    live = {"match_elapsed_s": 50.0, "frozen": False, "match_start_t": 3.0, "capture": {"ok": True},
            "left": {"opener": "迷走砲"}, "right": {"opener": "合掌TSD"}}
    win.on_state(live)
    win.on_state({**live, "frozen": True, "winner": "right", "match_elapsed_s": 60.0})
    win.on_state({**live, "frozen": True, "winner": "right", "match_elapsed_s": 60.0, "paused": False})
    assert seen == [1]
    rec = opener_stats.load()
    assert len(rec) == 1 and rec[0]["winner"] == "right" and rec[0]["right"]["opener"] == "合掌TSD"


def test_the_settings_tab_shows_them(tmp_path, monkeypatch):
    import config_store
    monkeypatch.setattr(config_store, "CONFIG_PATH", tmp_path / "s.json")
    monkeypatch.setattr(opener_stats, "HISTORY_PATH", tmp_path / "h.json")
    opener_stats.save([m("A", "B", "left"), m("A", "C", "right"), m(None, "A", "left")])
    import settings_window
    w = settings_window.SettingsWindow(drag_available=True)
    w.st_vs.setCurrentIndex(w.st_vs.findData("all"))
    assert w.st_table.rowCount() == 2 and w.st_table.item(0, 0).text() == "A"
    assert w.st_table.item(0, 3).text().startswith("50%")
    assert w.st_pie.total == 3
    assert not config_store.CONFIG_PATH.exists() or "opener_stats" in config_store.load_settings()["ui"]


def test_the_recent_averages():
    """The average APM, PPS... over the same matches (user's request)."""
    st = {"frozen": True, "match_elapsed_s": 60.0, "winner": "left",
          "left": {"opener": "A", "apm": {"apm": 60.0}, "pps": 2.0, "app": 0.5,
                   "match_stats": {"lines_sent": 60, "pieces": 120, "max_ren": 4}},
          "right": {"opener": "B", "apm": {"apm": 30.0}, "pps": None, "app": 0.3, "match_stats": {}}}
    rec = match_record(st, now=1)
    assert rec["left"]["stats"]["apm"] == 60.0 and rec["left"]["stats"]["max_ren"] == 4
    assert "pps" not in rec["right"]["stats"]                     # no value, not a 0
    other = match_record({**st, "left": {**st["left"], "apm": {"apm": 40.0}, "pps": 3.0}}, now=2)
    old = m("A", "B", "left")                                      # kept before the numbers were
    avg = opener_stats.averages([old, rec, other], 10, "left")
    assert avg["apm"] == 50.0 and avg["pps"] == 2.5 and avg["lines_sent"] == 60
    assert opener_stats.averages([rec, other], 1, "left")["apm"] == 40.0
    assert opener_stats.averages([rec], 10, "both")["apm"] == 45.0


def test_last_n_buttons_up_to_500(tmp_path, monkeypatch):
    """How many recent matches: buttons 10-500 (user's request), an older
    saved number goes to the nearest one."""
    import config_store
    monkeypatch.setattr(config_store, "CONFIG_PATH", tmp_path / "s.json")
    monkeypatch.setattr(opener_stats, "HISTORY_PATH", tmp_path / "h.json")
    config_store.save_settings({**config_store.DEFAULTS, "ui": {"opener_stats": {"last_n": 40}}})
    import settings_window
    w = settings_window.SettingsWindow(drag_available=True)
    assert w.st_last.currentData() == 50
    assert [w.st_last.itemText(i) for i in range(w.st_last.count())] == ["10", "20", "50", "100", "200", "500"]
    w.st_last.setCurrentIndex(w.st_last.findData(500))
    assert config_store.load_settings()["ui"]["opener_stats"]["last_n"] == 500
    assert opener_stats.KEEP == 500
