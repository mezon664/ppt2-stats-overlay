"""Updates from GitHub releases (scripts/updater.py): only newer versions,
only GitHub addresses, nothing outside the app, the user's own files kept."""
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import pytest

import updater
from version import VERSION


def test_versions():
    assert updater.parse_version("v1.2.3") == (1, 2, 3) and updater.parse_version("0.10.0") == (0, 10, 0)
    assert updater.parse_version("v1.2") is None and updater.parse_version("latest") is None
    assert updater.is_newer("v0.10.0", "0.9.9") and not updater.is_newer("v0.1.0", "0.1.0")
    assert not updater.is_newer("v0.0.9", "0.1.0") and not updater.is_newer("nonsense", "0.1.0")


def release(tag="v9.9.9", url="https://github.com/x/y/releases/download/v9.9.9/ppt2-stats-overlay-v9.9.9.zip",
            name="ppt2-stats-overlay-v9.9.9.zip", **extra):
    return {"tag_name": tag, "body": "notes", "html_url": "https://github.com/x/y/releases/tag/" + tag,
            "assets": [{"name": name, "browser_download_url": url}], **extra}


def test_release_info_only_takes_the_app_zip_from_github():
    info = updater.release_info(release())
    assert info["version"] == "9.9.9" and info["url"].endswith(".zip")
    assert updater.release_info(release(url="https://evil.example.com/ppt2-stats-overlay.zip")) is None
    assert updater.release_info(release(url="http://github.com/x/y/a.zip")) is None   # not https
    assert updater.release_info(release(name="something-else.zip")) is None
    new = updater.release_info(release(name="PPTetrics-v9.9.9.zip",
                                       url="https://github.com/x/y/releases/download/v9.9.9/PPTetrics-v9.9.9.zip"))
    assert new["url"].endswith("PPTetrics-v9.9.9.zip")   # the app's name since v0.2.0 (the old one still works)
    assert updater.release_info(release(prerelease=True)) is None
    assert updater.release_info(release(tag="nightly")) is None


def make_zip(path, files, top="ppt2-stats-overlay"):
    with zipfile.ZipFile(path, "w") as z:
        for name, text in files.items():
            z.writestr(f"{top}/{name}" if top else name, text)
    return path


def test_extract_refuses_paths_outside_and_drops_users_files(tmp_path):
    bad = make_zip(tmp_path / "bad.zip", {"../escape.txt": "x", "launch.py": ""}, top=None)
    with pytest.raises(ValueError):
        updater.extract(bad, tmp_path / "out1")
    good = make_zip(tmp_path / "good.zip", {"launch.py": "", "scripts/a.py": "",
                                            "config/overlay_settings.json": "{}", "assets/user_fonts/f.ttf": ""})
    app = updater.extract(good, tmp_path / "out2")
    assert (app / "launch.py").exists() and (app / "scripts" / "a.py").exists()
    assert not (app / "config" / "overlay_settings.json").exists()
    assert not (app / "assets" / "user_fonts").exists()
    with pytest.raises(ValueError):   # not this app
        updater.extract(make_zip(tmp_path / "other.zip", {"readme.txt": ""}), tmp_path / "out3")


def test_check_latest_says_nothing_when_not_newer(monkeypatch):
    import io
    import json

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(updater, "_open", lambda url, accept="": Resp(json.dumps(release(tag="v" + VERSION)).encode()))
    assert updater.check_latest() is None
    monkeypatch.setattr(updater, "_open", lambda url, accept="": Resp(json.dumps(release()).encode()))
    assert updater.check_latest()["version"] == "9.9.9"


def test_no_downloads_from_elsewhere():
    with pytest.raises(ValueError):
        updater._open("https://example.com/ppt2-stats-overlay.zip")


@pytest.mark.skipif(sys.platform != "win32", reason="the finishing script is PowerShell")
def test_finishing_script_copies_keeps_user_files_and_restarts(tmp_path):
    """The real thing on a throwaway app folder: waits for the (already gone)
    app, copies the new files over it, leaves the user's settings alone and
    starts the app again."""
    app = tmp_path / "my app"   # a space in the path, as in many user folders
    (app / "config").mkdir(parents=True)
    (app / "config" / "overlay_settings.json").write_text("mine", encoding="utf-8")
    (app / "scripts").mkdir()
    (app / "scripts" / "old.py").write_text("old", encoding="utf-8")
    (app / "launch.py").write_text("old", encoding="utf-8")
    new = updater.extract(make_zip(tmp_path / "u.zip", {"launch.py": "new", "scripts/new.py": "new"}), tmp_path / "x")
    marker = tmp_path / "my app" / "restarted.txt"
    restart = [sys.executable, "-c", f"open(r'{marker}', 'w').write('yes')"]
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()   # the "app" has quit
    script = tmp_path / "finish.ps1"
    script.write_text(updater.update_script(new, app, proc.pid, restart, tmp_path / "update.log"), encoding="utf-8-sig")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], timeout=60,
                   creationflags=0x08000000)
    for _ in range(50):
        if marker.exists():
            break
        time.sleep(0.1)
    assert (app / "launch.py").read_text(encoding="utf-8") == "new"
    assert (app / "scripts" / "new.py").exists() and (app / "scripts" / "old.py").exists()
    assert (app / "config" / "overlay_settings.json").read_text(encoding="utf-8") == "mine"
    assert marker.exists()


def test_release_zip_has_the_app_and_nothing_personal():
    sys.path.insert(0, str(ROOT / "tools"))
    import make_release
    names = {f.relative_to(ROOT).as_posix() for f in make_release.files()}
    assert "launch.py" in names and "scripts/updater.py" in names and "hud/overlay.py" in names
    assert "config/attack_table.json" in names                     # the game's attack table, needed to start
    assert not any(n.startswith(("tests/", "tools/", "docs/", "debug_frames/", "logs/"))
                   or "user_fonts" in n or "overlay_settings" in n for n in names)


def test_the_release_zip_runs(tmp_path):
    """Everything the app reads at start-up is in the zip: unpack it and
    build the recognition from that copy alone (v0.1.0's zip lacked
    config/attack_table.json and couldn't start)."""
    sys.path.insert(0, str(ROOT / "tools"))
    import make_release
    out = make_release.main()
    with zipfile.ZipFile(out) as z:
        z.extractall(tmp_path)
    app = next(tmp_path.glob("*/launch.py")).parent
    code = ("import sys; sys.path[:0] = ['scripts', 'hud']; import live_pipeline, opener_detect, updater; "
            "live_pipeline.MatchPipeline(); opener_detect.openers(); print('ok')")
    r = subprocess.run([sys.executable, "-c", code], cwd=app, capture_output=True, text=True, timeout=120)
    assert r.stdout.strip().endswith("ok"), r.stderr[-2000:]


def test_an_update_needing_new_libraries_is_refused(tmp_path, monkeypatch):
    """The full package's bundled libraries are older than the update needs:
    say so instead of half-updating."""
    new = tmp_path / "new"
    (new / "scripts").mkdir(parents=True)
    (new / "scripts" / "version.py").write_text('VERSION = "9.0.0"\nRUNTIME = 5\n', encoding="utf-8")
    assert updater.runtime_needed(new) == 5
    rt = tmp_path / "app" / "runtime"
    rt.mkdir(parents=True)
    (rt / "RUNTIME_VERSION").write_text("1")
    monkeypatch.setattr(updater, "ROOT", tmp_path / "app")
    assert updater.installed_runtime() == 1
    monkeypatch.setattr(updater, "ROOT", tmp_path / "nothing")
    assert updater.installed_runtime() is None          # own Python: not checked


def test_the_full_package_is_never_taken_for_an_update():
    full = updater.release_info(release(name="PPTetrics-full-v9.9.9.zip",
                                        url="https://github.com/x/y/releases/download/v9.9.9/PPTetrics-full-v9.9.9.zip"))
    assert full is None
