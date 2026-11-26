"""Reading the game from a window picked by its title (a streaming app's
projector): scripts/live_capture.WindowCapture."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import live_capture  # noqa: E402
from config_store import display_settings  # noqa: E402
from image_io import read_image  # noqa: E402

FRAME = sorted((ROOT / "debug_frames" / "burst2").glob("*.*"))


def _fake(monkeypatch, iconic=False, size=(1232, 693)):
    monkeypatch.setattr(live_capture, "find_window", lambda title: 42 if title == "Projector" else None)
    monkeypatch.setattr(live_capture.win32gui, "IsWindow", lambda h: True)
    monkeypatch.setattr(live_capture.win32gui, "IsIconic", lambda h: iconic)
    monkeypatch.setattr(live_capture.win32gui, "GetClientRect", lambda h: (0, 0) + size)


def test_the_setting():
    d = display_settings({})
    assert d["capture_source"] == "game" and d["capture_window"] == ""
    d = display_settings({"display": {"capture_source": "window", "capture_window": "ウィンドウ プロジェクター (ソース) - キャプチャ"}})
    assert d["capture_source"] == "window" and d["capture_window"].endswith("キャプチャ")
    assert display_settings({"display": {"capture_window": "a\nb"}})["capture_window"] == ""
    cap = live_capture.make_capture({"capture_source": "window", "capture_window": "OBS projector"})
    assert isinstance(cap, live_capture.WindowCapture) and cap.title == "OBS projector" and cap.hwnd is None


def test_says_why_when_it_cant_read(monkeypatch):
    assert live_capture.WindowCapture("").grab()[2].startswith("読み取るウィンドウが選ばれていません")
    _fake(monkeypatch)
    assert "見つかりません" in live_capture.WindowCapture("Elsewhere").grab()[2]
    _fake(monkeypatch, iconic=True)
    assert "最小化" in live_capture.WindowCapture("Projector").grab()[2]


@pytest.mark.skipif(not FRAME, reason="recording not here")
def test_reads_the_screen_unless_something_is_over_the_window(monkeypatch):
    """Its own picture (PrintWindow) makes a window draw itself again each
    time: the game's flickered. Only used while something covers it."""
    _fake(monkeypatch)
    monkeypatch.setattr(live_capture, "_is_game_window", lambda h: False)
    game = read_image(str(FRAME[100]))
    own = []
    cap = live_capture.WindowCapture("Projector", grab_window=lambda h, w, hh: own.append(1) or game,
                                     grab_screen=lambda h, w, hh: game, uncovered=lambda h, w, hh: True)
    frame, ok, reason, profile = cap.grab()
    assert ok and reason is None and profile.ok and cap.last_method == "screen" and not own
    cap = live_capture.WindowCapture("Projector", grab_window=lambda h, w, hh: game,
                                     grab_screen=lambda h, w, hh: np.zeros_like(game), uncovered=lambda h, w, hh: False)
    frame, ok, reason, profile = cap.grab()
    assert ok and cap.last_method == "window"     # (covered: its own picture)
    black = np.zeros_like(game)
    cap = live_capture.WindowCapture("Projector", grab_window=lambda h, w, hh: black,
                                     grab_screen=lambda h, w, hh: game, uncovered=lambda h, w, hh: False)
    frame, ok, reason, profile = cap.grab()
    assert ok and cap.last_method == "screen"     # (its own picture black: the screen all the same)


def test_the_games_own_window_is_left_to_pc_version(monkeypatch):
    _fake(monkeypatch)
    monkeypatch.setattr(live_capture, "_is_game_window", lambda h: True)
    drawn = []
    cap = live_capture.WindowCapture("Projector", grab_window=lambda h, w, hh: drawn.append(1),
                                     grab_screen=lambda h, w, hh: drawn.append(1))
    frame, ok, reason, _ = cap.grab()
    assert not ok and "PC 版" in reason and not drawn       # (never made to draw itself again)


def test_this_apps_own_windows_arent_offered(monkeypatch):
    wins = {1: ("Projector", 100), 2: ("PPTetrics 設定", 200), 3: ("", 300), 4: ("Tiny", 400)}
    monkeypatch.setattr(live_capture, "_own_pids", lambda: {200})
    monkeypatch.setattr(live_capture.win32gui, "EnumWindows", lambda cb, _: [cb(h, None) for h in wins])
    monkeypatch.setattr(live_capture.win32gui, "IsWindowVisible", lambda h: True)
    monkeypatch.setattr(live_capture.win32gui, "GetWindowText", lambda h: wins[h][0])
    monkeypatch.setattr(live_capture.win32process, "GetWindowThreadProcessId", lambda h: (0, wins[h][1]))
    monkeypatch.setattr(live_capture.psutil, "Process", lambda pid: type("P", (), {"name": lambda self: "obs64.exe"})())
    monkeypatch.setattr(live_capture.win32gui, "IsIconic", lambda h: False)
    monkeypatch.setattr(live_capture.win32gui, "GetClientRect", lambda h: (0, 0, 50, 30) if h == 4 else (0, 0, 800, 450))
    assert live_capture.window_titles() == ["Projector"]
