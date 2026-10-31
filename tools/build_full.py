"""Builds the package for a first download: dist/PPTetrics-full-v<VERSION>.zip,
which runs without Python installed (double-click start.bat).

It is the release zip (tools/make_release.py) plus runtime/: Windows'
embeddable Python (python.org) with the app's libraries (requirements.txt)
in it. Updates then only fetch the small code zip; runtime/ stays as it is
(scripts/updater.py PRESERVE). When requirements.txt changes, raise
RUNTIME in scripts/version.py: the updater then sends people to the full
package instead (a code-only update could need libraries they don't have).

Run on Windows (GitHub Actions does it for each release):
    python tools/build_full.py
"""
import io
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tools"))
from version import VERSION, RUNTIME  # noqa: E402
import make_release  # noqa: E402

PY = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
EMBED_URL = f"https://www.python.org/ftp/python/{PY}/python-{PY}-embed-amd64.zip"
BUILD = ROOT / "build" / "full"


def runtime_dir():
    rt = BUILD / "runtime"
    if rt.exists():
        shutil.rmtree(rt)
    rt.mkdir(parents=True)
    with urllib.request.urlopen(EMBED_URL, timeout=60) as resp:
        zipfile.ZipFile(io.BytesIO(resp.read())).extractall(rt)
    site = rt / "Lib" / "site-packages"
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "--only-binary=:all:",
                    "--target", str(site), "-r", str(ROOT / "requirements.txt")], check=True)
    # the embeddable Python only searches the folders listed in its ._pth file
    pth = next(rt.glob("python*._pth"))
    lines = [ln for ln in pth.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    lines += [r"Lib\site-packages", r"Lib\site-packages\win32", r"Lib\site-packages\win32\lib",
              r"Lib\site-packages\Pythonwin", "import site"]
    pth.write_text("\n".join(lines) + "\n")
    # pywin32's own DLLs go next to python.exe (its .pth would put them on the path)
    for dll in (site / "pywin32_system32").glob("*.dll"):
        shutil.copy2(dll, rt / dll.name)
    (rt / "RUNTIME_VERSION").write_text(str(RUNTIME))
    return rt


def main():
    code_zip = make_release.main()
    rt = runtime_dir()
    out = ROOT / "dist" / f"{make_release.TOP}-full-v{VERSION}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        with zipfile.ZipFile(code_zip) as src:
            for item in src.infolist():
                z.writestr(item, src.read(item.filename))
        for f in sorted(rt.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f"{make_release.TOP}/runtime/{f.relative_to(rt).as_posix()}")
    print(f"{out} ({out.stat().st_size // (1024 * 1024)} MB)")
    return out


if __name__ == "__main__":
    main()
