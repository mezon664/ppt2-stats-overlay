"""A failed start says why on screen (launch.py, start.bat)."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _launch():
    import startup_error
    return startup_error


def test_a_missing_library_points_at_the_full_zip(tmp_path):
    launch = _launch()
    text = launch.startup_message(ModuleNotFoundError("No module named 'PyQt6'", name="PyQt6"), tmp_path, "C:/Python/python.exe")
    assert "PyQt6" in text and "runtime フォルダがなく" in text and "C:/Python/python.exe" in text
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime" / "pythonw.exe").write_bytes(b"")
    assert "runtime フォルダの Python" in launch.startup_message(ImportError("x", name="cv2"), tmp_path)


def test_any_other_failure_shows_its_reason_and_the_logs(tmp_path):
    text = _launch().startup_message(RuntimeError("data_server exited during startup (code 1)"), tmp_path)
    assert "data_server exited during startup" in text and str(tmp_path / "logs" / "server.log") in text


def test_pythons_without_the_libraries_say_so_instead_of_vanishing(tmp_path):
    """The real thing: launch.py on a Python that has none of the app's
    libraries (-I -S: no site-packages) ends with the message in its log."""
    env = {**os.environ, "PPTETRICS_NO_DIALOG": "1"}
    log = ROOT / "logs" / "launch.log"
    before = log.stat().st_size if log.exists() else 0
    r = subprocess.run([sys.executable, "-I", "-S", str(ROOT / "launch.py")], env=env, cwd=str(tmp_path),
                       capture_output=True, timeout=60)
    assert r.returncode == 1
    with open(log, "rb") as f:
        f.seek(before)
        tail = f.read().decode("utf-8", "replace")
    assert "必要な部品" in tail
