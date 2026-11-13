"""Builds the release zip: dist/PPTetrics-v<VERSION>.zip (and the same zip as
dist/ppt2-stats-overlay-v<VERSION>.zip, the name copies up to v0.1.0 look for).

What users get (and what an update copies over their app): the app itself —
launch.py / start.bat, scripts/, hud/, obs/, assets/ — and README.md /
requirements.txt. Never in it: anyone's own settings, loaded fonts, logs or
recordings (see scripts/updater.py PRESERVE), nor the developer's tests,
tools and notes.

Run by .github/workflows/release.yml on a version tag; also works locally:
    python tools/make_release.py
"""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from version import VERSION  # noqa: E402

TOP = "PPTetrics"     # the folder inside the zip
LEGACY_NAME = "ppt2-stats-overlay"   # the app's name up to v0.1.0
INCLUDE = ["launch.py", "start.bat", "README.md", "LICENSE", "requirements.txt", "requirements-vendor.txt",
           "scripts", "hud", "obs", "assets",
           "config/attack_table.json"]   # the game's attack table (the settings file next to it is each user's own)
SKIP_PARTS = {"__pycache__", "user_fonts", ".pytest_cache"}
# the second cat clip (6 MB) is held back for now (hud/overlay.py CAT2_EVERY)
SKIP_DIRS = {("assets", "cat2"), ("assets", "challenge_cats")}   # (challenge cats: not released yet)
# Libraries added after the bundled runtime (requirements-vendor.txt), shipped
# in the zip as vendor/: an update from the settings window brings them, no
# new full package needed (the runtime is Python 3.12 on 64-bit Windows).
VENDOR_REQ = ROOT / "requirements-vendor.txt"
VENDOR_BUILD = ROOT / "build" / "vendor"
RUNTIME_PY = "3.12"


def build_vendor():
    import shutil
    import subprocess
    import sys
    if VENDOR_BUILD.exists():
        shutil.rmtree(VENDOR_BUILD)
    VENDOR_BUILD.mkdir(parents=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "--only-binary=:all:",
                    "--platform", "win_amd64", "--python-version", RUNTIME_PY, "--implementation", "cp",
                    "--target", str(VENDOR_BUILD), "-r", str(VENDOR_REQ)], check=True)
    return VENDOR_BUILD
SKIP_SUFFIXES = {".pyc", ".tmp", ".log"}


def files():
    for name in INCLUDE:
        p = ROOT / name
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                rel = f.relative_to(ROOT)
                if (f.is_file() and not (set(rel.parts) & SKIP_PARTS) and f.suffix not in SKIP_SUFFIXES
                        and tuple(rel.parts[:2]) not in SKIP_DIRS):
                    yield f
        else:
            raise SystemExit(f"missing from the release: {name}")


def main():
    out = ROOT / "dist" / f"{TOP}-v{VERSION}.zip"
    out.parent.mkdir(exist_ok=True)
    count = 0
    vendor = build_vendor()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files():
            z.write(f, f"{TOP}/{f.relative_to(ROOT).as_posix()}")
            count += 1
        for f in sorted(vendor.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
                z.write(f, f"{TOP}/vendor/{f.relative_to(vendor).as_posix()}")
                count += 1
    legacy = out.with_name(f"{LEGACY_NAME}-v{VERSION}.zip")
    legacy.write_bytes(out.read_bytes())
    print(f"{out} ({count} files, {out.stat().st_size // 1024} KB), copy: {legacy.name}")
    return out


if __name__ == "__main__":
    main()
