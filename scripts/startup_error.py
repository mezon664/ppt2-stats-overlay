"""What a failed start says (launch.py). Only the standard library: it has to
work on a Python that has none of the app's libraries."""
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def startup_message(exc, root=ROOT, exe=None):
    """What a failed start says on screen (started with pythonw, a failure
    used to end with nothing shown at all: a user's report). A missing
    library is nearly always the app started by the PC's own Python, not the
    one the full zip brings in runtime/."""
    exe = exe or sys.executable
    log_path = root / "logs" / "launch.log"
    if isinstance(exc, ImportError):
        name = getattr(exc, "name", None) or str(exc)
        if (root / "runtime" / "pythonw.exe").exists():
            where = "runtime フォルダの Python に、この部品が入っていません。"
        else:
            where = f"アプリのフォルダに runtime フォルダがなく、PC の Python（{exe}）で起動しています。"
        return ("PPTetrics を起動できませんでした。\n\n"
                f"必要な部品（{name}）が見つかりません。{where}\n"
                "runtime フォルダ入りの完全版の zip を、新しいフォルダに入れ直してください。\n\n"
                f"A library the app needs ({name}) is missing: reinstall the full zip (with runtime/).\n\n"
                f"記録 / Log: {log_path}")
    text = f"{type(exc).__name__}: {exc}"
    if len(text) > 400:
        text = text[:400] + "…"
    return ("PPTetrics を起動できませんでした（または途中で止まりました）。\n\n"
            f"{text}\n\n"
            "PPTetrics stopped with an error.\n\n"
            f"記録 / Log: {log_path}（サーバー / server: {root / 'logs' / 'server.log'}）")


def show_startup_error(exc):
    """The reason, in the log and in a message box (Windows' own: needs no library)."""
    message = startup_message(exc)
    traceback.print_exception(exc)
    print(message)
    if os.environ.get("PPTETRICS_NO_DIALOG"):     # (tests)
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "PPTetrics", 0x10 | 0x40000)   # error icon, on top
    except Exception:
        traceback.print_exc()
