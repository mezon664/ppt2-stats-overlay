"""The server ends itself when the launcher that started it is gone (users:
pythonw.exe stayed behind after the app closed)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_server_side_watch_ends_when_the_parent_is_gone():
    parent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(1.0)"])
    code = ("import sys, time; sys.path.insert(0, r'%s'); import data_server; "
            "data_server.watch_parent(%d, interval=0.2); time.sleep(30)") % (ROOT / "scripts", parent.pid)
    child = subprocess.Popen([sys.executable, "-c", code], cwd=str(ROOT / "scripts"))
    try:
        assert child.wait(timeout=15) == 0     # well before its 30 s sleep
    finally:
        if child.poll() is None:
            child.kill()
        parent.wait(timeout=5)


def test_reads_fewer_times_a_second_off_the_match_screen():
    """Off the match screen for a while the game is read 5 times a second,
    not 15; on it (or paused, or just left it) at the full rate."""
    from data_server import idle_period, IDLE_AFTER_S
    p = 1 / 15
    assert idle_period(None, None, 100.0, p) == p                      # match screen
    assert idle_period("pause", 90.0, 100.0, p) == p                   # pause menu
    assert idle_period("no_match_ui", 99.0, 100.0, p) == p             # just left it
    assert idle_period("no_match_ui", 100.0 - IDLE_AFTER_S, 100.0, p) == 1 / 5
