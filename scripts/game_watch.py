"""Starts PPTetrics when Puyo Puyo Tetris 2 starts (user's request).

Started with Windows (scripts/autostart.py puts it in the user's Run key) and
runs quietly: every few seconds it looks whether the game is running, and the
moment it starts, starts the app — unless the app is already running. It
starts it once per game session: quitting the app while playing doesn't bring
it back until the game is started again. Light: one look at the process list
every CHECK_S seconds, nothing else.
"""
import ctypes
import subprocess
import sys
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
GAME_EXE = "puyopuyotetris2.exe"
CHECK_S = 3.0
MUTEX_NAME = "Local\\PPTetricsGameWatch"
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008


def game_running():
    for p in psutil.process_iter(["name"]):
        if (p.info.get("name") or "").lower() == GAME_EXE:
            return True
    return False


def app_running():
    """PPTetrics (launch.py from this folder) is already running."""
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            cmd = p.info.get("cmdline") or []
            if any(Path(c).name == "launch.py" for c in cmd) and \
                    (str(ROOT).lower() in " ".join(cmd).lower() or Path(p.cwd()).resolve() == ROOT):
                return True
        except (psutil.Error, OSError):
            continue
    return False


def app_python():
    """The pythonw the app runs with: the full package's own, else this folder's .venv, else this one."""
    for cand in (ROOT / "runtime" / "pythonw.exe", ROOT / ".venv" / "Scripts" / "pythonw.exe"):
        if cand.exists():
            return cand
    exe = Path(sys.executable)
    return exe.with_name("pythonw.exe") if exe.with_name("pythonw.exe").exists() else exe


def start_app():
    subprocess.Popen([str(app_python()), "launch.py"], cwd=str(ROOT),
                     creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS, close_fds=True)


def already_watching():
    """Another watcher is running (one is enough)."""
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, MUTEX_NAME)
    already = ctypes.windll.kernel32.GetLastError() == 183   # ERROR_ALREADY_EXISTS
    return already, handle


def watch(check_s=CHECK_S, rounds=None):
    was_running = game_running()   # the game already open when this starts: not a new start
    n = 0
    while rounds is None or n < rounds:
        n += 1
        time.sleep(check_s)
        now = game_running()
        if now and not was_running and not app_running():
            start_app()
        was_running = now


def main():
    already, _handle = already_watching()   # (the handle is kept for as long as this runs)
    if already:
        return
    watch()


if __name__ == "__main__":
    main()
