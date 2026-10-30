"""Builds the release zip: dist/ppt2-stats-overlay-v<VERSION>.zip.

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

TOP = "ppt2-stats-overlay"     # the folder inside the zip
INCLUDE = ["launch.py", "start.bat", "README.md", "requirements.txt", "scripts", "hud", "obs", "assets"]
SKIP_PARTS = {"__pycache__", "user_fonts", ".pytest_cache"}
SKIP_SUFFIXES = {".pyc", ".tmp", ".log"}


def files():
    for name in INCLUDE:
        p = ROOT / name
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                rel = f.relative_to(ROOT)
                if f.is_file() and not (set(rel.parts) & SKIP_PARTS) and f.suffix not in SKIP_SUFFIXES:
                    yield f
        else:
            raise SystemExit(f"missing from the release: {name}")


def main():
    out = ROOT / "dist" / f"{TOP}-v{VERSION}.zip"
    out.parent.mkdir(exist_ok=True)
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files():
            z.write(f, f"{TOP}/{f.relative_to(ROOT).as_posix()}")
            count += 1
    print(f"{out} ({count} files, {out.stat().st_size // 1024} KB)")
    return out


if __name__ == "__main__":
    main()
