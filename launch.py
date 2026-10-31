"""One-click start: runs the recognition server in the background and the
HUD (with its tray icon and settings window) in front. Quitting the HUD from
the tray also stops the server it started.

Double-click start.bat (no console window), or: python launch.py
Server output goes to logs/server.log.
"""

import atexit
import os
import socket
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# pythonw.exeでも起動時のエラーを記録する
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

_launch_log = open(
    LOG_DIR / "launch.log",
    "a",
    encoding="utf-8",
    buffering=1
)

sys.stdout = _launch_log
sys.stderr = _launch_log

print("\n========== PPTetrics launch ==========")
print("Python:", sys.executable)
print("Arguments:", sys.argv)


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hud"))

from config_store import load_settings  # noqa: E402


def server_already_running(host, port):
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def start_server():
    settings = load_settings()
    host, port = settings["server"]["host"], settings["server"]["port"]
    if server_already_running(host, port):
        return None  # e.g. started by hand: just attach the HUD to it
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log_file = open(logs / "server.log", "a", encoding="utf-8")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}   # the log has Japanese in it
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "scripts" / "data_server.py"), "--source", "live"],
        cwd=str(ROOT / "scripts"), stdout=log_file, stderr=subprocess.STDOUT, creationflags=flags, env=env,
    )

    def stop():
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        log_file.close()

    atexit.register(stop)
    return proc


def main():
    start_server()
    import overlay  # hud/overlay.py
    overlay.main()  # runs until "終了 / Quit" in the tray menu


if __name__ == "__main__":
    main()
