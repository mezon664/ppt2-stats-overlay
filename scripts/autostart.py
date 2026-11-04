"""「ぷよテト2と一緒に起動」 (user's request): on, scripts/game_watch.py starts
with Windows (the current user's Run key, no admin rights) and starts the app
whenever the game starts; off, that entry is removed and the watcher stops.
"""
import subprocess
from pathlib import Path

import psutil

import game_watch

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "PPTetrics (start with Puyo Puyo Tetris 2)"
WATCHER = Path(game_watch.__file__).resolve()


def command():
    return f'"{game_watch.app_python()}" "{WATCHER}"'


def _read():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return winreg.QueryValueEx(key, VALUE_NAME)[0]
    except OSError:
        return None


def _write(value):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if value is None:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
        else:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, value)


def is_enabled():
    return _read() is not None


def set_enabled(on):
    """Turns it on or off, and starts / stops the watcher right away (no
    need to restart Windows)."""
    if on:
        _write(command())
        if not watchers():
            subprocess.Popen([str(game_watch.app_python()), str(WATCHER)], cwd=str(WATCHER.parent.parent),
                             creationflags=game_watch.CREATE_NO_WINDOW | game_watch.DETACHED_PROCESS,
                             close_fds=True)
    else:
        _write(None)
        for p in watchers():
            try:
                p.terminate()
            except psutil.Error:
                pass


def watchers():
    out = []
    for p in psutil.process_iter(["cmdline"]):
        try:
            if any(Path(c).name == "game_watch.py" for c in (p.info.get("cmdline") or [])):
                out.append(p)
        except (psutil.Error, OSError):
            continue
    return out
