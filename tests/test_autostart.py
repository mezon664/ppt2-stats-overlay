"""「ぷよテト2と一緒に起動」: the watcher starts the app when the game starts
(scripts/game_watch.py), switched on and off through the user's Run key
(scripts/autostart.py). The registry and processes are faked here."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import autostart
import game_watch


def test_the_app_starts_once_when_the_game_starts(monkeypatch):
    game = iter([False, False, True, True, True, False, True])   # first look, then one per round
    started = []
    monkeypatch.setattr(game_watch, "game_running", lambda: next(game))
    monkeypatch.setattr(game_watch, "app_running", lambda: False)
    monkeypatch.setattr(game_watch, "start_app", lambda: started.append(1))
    monkeypatch.setattr(game_watch.time, "sleep", lambda s: None)
    game_watch.watch(rounds=6)
    assert started == [1, 1]          # at each start of the game, not while it keeps running


def test_not_started_again_when_already_running(monkeypatch):
    game = iter([False, True])
    started = []
    monkeypatch.setattr(game_watch, "game_running", lambda: next(game))
    monkeypatch.setattr(game_watch, "app_running", lambda: True)
    monkeypatch.setattr(game_watch, "start_app", lambda: started.append(1))
    monkeypatch.setattr(game_watch.time, "sleep", lambda s: None)
    game_watch.watch(rounds=1)
    assert started == []


def test_switching_it_on_and_off(monkeypatch):
    reg = {}
    monkeypatch.setattr(autostart, "_read", lambda: reg.get("v"))
    monkeypatch.setattr(autostart, "_write", lambda v: reg.pop("v", None) if v is None else reg.update(v=v))
    popen, stopped = [], []

    class Proc:
        def terminate(self):
            stopped.append(1)
    running = []
    monkeypatch.setattr(autostart, "watchers", lambda: list(running))
    monkeypatch.setattr(autostart.subprocess, "Popen", lambda *a, **k: (popen.append(a[0]), running.append(Proc())))
    assert not autostart.is_enabled()
    autostart.set_enabled(True)
    assert autostart.is_enabled() and "game_watch.py" in reg["v"] and len(popen) == 1
    autostart.set_enabled(True)                      # already watching: not a second one
    assert len(popen) == 1
    autostart.set_enabled(False)
    assert not autostart.is_enabled() and stopped == [1]
