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
