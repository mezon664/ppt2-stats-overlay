"""Updates from the GitHub releases (user's request: new features and fixes
without downloading the app again by hand).

  check_latest()   asks GitHub for the newest release (one small request)
  download()       fetches its zip (only from GitHub's own hosts)
  prepare_update() unpacks it next to nothing it shouldn't touch and writes
                   a small PowerShell script that waits for this app to quit,
                   copies the new files over it and starts it again

Nothing happens without the user pressing "更新する". The user's own files are
never overwritten: their settings, loaded fonts, logs and recordings are not
in a release zip at all (tools/make_release.py), and the copy skips them
anyway (PRESERVE).
"""
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree

from version import VERSION

ROOT = Path(__file__).resolve().parent.parent
# where releases come from: github.com/<owner>/<repo>
UPDATE_REPO = "mezon664/ppt2-stats-overlay"
LATEST_URL = f"https://api.github.com/repos/{UPDATE_REPO}/releases/latest"
RELEASES_ATOM_URL = f"https://github.com/{UPDATE_REPO}/releases.atom"
# the release zip: PPTetrics-v1.2.3.zip (the app was "ppt2-stats-overlay" up to
# v0.1.0; releases carry a copy under that name too, for copies that old)
ASSET_PREFIXES = ("PPTetrics", "ppt2-stats-overlay")
# a release zip is only downloaded from GitHub itself (redirects included)
ALLOWED_HOSTS = {"github.com", "api.github.com", "objects.githubusercontent.com",
                 "release-assets.githubusercontent.com", "codeload.github.com"}
# never replaced by an update, even if a zip had them
PRESERVE = ("config/overlay_settings.json", "assets/user_fonts", "debug_frames", "logs", ".venv", "samples", ".git",
            "runtime")   # the full package's bundled Python (tools/build_full.py)
TIMEOUT_S = 10
log = logging.getLogger("pptetrics.updater")


def parse_version(text):
    """'v1.2.3' / '1.2.3' -> (1, 2, 3); None when it isn't a version."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (text or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def is_newer(latest, current=VERSION):
    a, b = parse_version(latest), parse_version(current)
    return a is not None and b is not None and a > b


def _allowed(url):
    p = urlparse(url)
    return p.scheme == "https" and p.hostname in ALLOWED_HOSTS


def _open(url, accept="application/octet-stream"):
    if not _allowed(url):
        raise ValueError(f"not a GitHub address: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": f"PPTetrics/{VERSION}", "Accept": accept})
    resp = urllib.request.urlopen(req, timeout=TIMEOUT_S)
    if not _allowed(resp.geturl()):   # where the redirects ended up
        resp.close()
        raise ValueError(f"redirected away from GitHub: {resp.geturl()}")
    return resp


def release_info(data):
    """The parts of a GitHub release (API JSON) the updater needs, or None if
    it has no usable zip: {"version", "url", "notes", "page"}."""
    version = (data or {}).get("tag_name")
    if parse_version(version) is None or data.get("draft") or data.get("prerelease"):
        return None
    for asset in data.get("assets") or []:
        name, url = asset.get("name", ""), asset.get("browser_download_url", "")
        if name.startswith(ASSET_PREFIXES) and name.endswith(".zip") and "-full-" not in name and _allowed(url):
            return {"version": version.lstrip("v"), "url": url, "notes": data.get("body") or "",
                    "page": data.get("html_url") or ""}
    return None


def release_info_from_atom(payload):
    """Fallback for GitHub API outages/rate limits using the public releases feed.

    The feed contains release tags but not asset metadata. Release zips use a
    stable code-only name, so construct that URL and let the existing download
    host/redirect checks validate it before any file is saved.
    """
    root = ElementTree.fromstring(payload)
    ns = "{http://www.w3.org/2005/Atom}"
    for entry in root.findall(f"{ns}entry"):
        tag = (entry.findtext(f"{ns}title") or "").strip()
        version_parts = parse_version(tag)
        if version_parts is None:
            continue  # skip prerelease or non-version tags
        version = ".".join(str(part) for part in version_parts)
        tag = f"v{version}"
        return {
            "version": version,
            "url": f"https://github.com/{UPDATE_REPO}/releases/download/{tag}/PPTetrics-{tag}.zip",
            "notes": "",
            "page": f"https://github.com/{UPDATE_REPO}/releases/tag/{tag}",
        }
    return None


def check_latest():
    """The newest release if newer than this copy; falls back to GitHub's feed."""
    api_error = None
    try:
        with _open(LATEST_URL, accept="application/vnd.github+json") as resp:
            info = release_info(json.loads(resp.read().decode("utf-8")))
        if info is not None:
            return info if is_newer(info["version"]) else None
    except Exception as exc:
        api_error = exc

    try:
        with _open(RELEASES_ATOM_URL, accept="application/atom+xml") as resp:
            info = release_info_from_atom(resp.read())
        if info is None:
            raise ValueError("GitHub releases feed contains no stable version tag")
        if api_error is not None:
            log.warning("GitHub API update check failed; release feed fallback succeeded: %s", api_error)
        return info if is_newer(info["version"]) else None
    except Exception as feed_error:
        if api_error is not None:
            message = (f"GitHub API check failed ({api_error}); "
                       f"release feed fallback failed ({feed_error})")
            log.error("Update check failed: %s", message)
            raise RuntimeError(message) from feed_error
        raise


def download(url, dest, progress=None):
    """Saves the release zip to dest; progress(done_bytes, total_bytes or 0)."""
    with _open(url) as resp, open(dest, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    return dest


def extract(zip_path, dest_dir):
    """Unpacks the zip (refusing entries that would land outside dest_dir) and
    returns the folder holding the app (the one with launch.py)."""
    dest_dir = Path(dest_dir).resolve()
    with zipfile.ZipFile(zip_path) as z:
        for name in z.namelist():
            target = (dest_dir / name).resolve()
            if dest_dir not in target.parents and target != dest_dir:
                raise ValueError(f"unsafe path in the update: {name}")
        z.extractall(dest_dir)
    found = [p.parent for p in dest_dir.rglob("launch.py")]
    if len(found) != 1:
        raise ValueError("the update doesn't look like this app (no single launch.py)")
    app = found[0]
    for rel in PRESERVE:   # belt and braces: never carry these over
        p = app / rel
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    return app


# shown when an update needs newer libraries than the bundled ones
NEEDS_FULL = ("この更新には新しい部品が必要です。GitHub のリリースページから完全版（PPTetrics-full）を"
              "ダウンロードして入れ直してください（設定はそのフォルダの config を移せば引き継げます）。")


def runtime_needed(app):
    """RUNTIME of a (new) copy of the app: its scripts/version.py."""
    m = re.search(r"^RUNTIME\s*=\s*(\d+)", (Path(app) / "scripts" / "version.py").read_text(encoding="utf-8"), re.M)
    return int(m.group(1)) if m else 0


def installed_runtime():
    """The bundled runtime's version, or None when running on an own Python
    (a .venv: libraries are the user's business there)."""
    f = ROOT / "runtime" / "RUNTIME_VERSION"
    return int(f.read_text().strip()) if f.exists() else None


def restart_command():
    """How this app is started again after the update."""
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return [str(pythonw if pythonw.exists() else exe), str(ROOT / "launch.py")]


def update_script(new_app, app_root, pid, restart_cmd, log_path):
    """The PowerShell that finishes the update once this app has quit."""
    def q(s):
        return "'" + str(s).replace("'", "''") + "'"
    exe, *args = restart_cmd
    arg_line = subprocess.list2cmdline(args)   # one string, quoted the Windows way (paths with spaces)
    return "\n".join([
        "$ErrorActionPreference = 'Continue'",
        f"Start-Transcript -Path {q(log_path)} -Append | Out-Null",
        f"Wait-Process -Id {int(pid)} -Timeout 60 -ErrorAction SilentlyContinue",
        "Start-Sleep -Milliseconds 500",
        # copy everything in the new version over the app; nothing is deleted
        f"robocopy {q(new_app)} {q(app_root)} /E /R:3 /W:1 /NFL /NDL /NP",
        "if ($LASTEXITCODE -ge 8) { Write-Output \"copy failed: $LASTEXITCODE\" }",
        f"Start-Process -FilePath {q(exe)} -ArgumentList {q(arg_line)} -WorkingDirectory {q(app_root)}",
        "Stop-Transcript | Out-Null",
    ])


def prepare_update(info, progress=None):
    """Downloads and unpacks the release, writes the finishing script and
    returns the command that runs it (start it, then quit the app)."""
    work = Path(tempfile.mkdtemp(prefix="ppt2-overlay-update-"))
    zip_path = download(info["url"], work / "update.zip", progress)
    new_app = extract(zip_path, work / "new")
    needed, have = runtime_needed(new_app), installed_runtime()
    if have is not None and needed > have:
        raise RuntimeError(NEEDS_FULL)
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    script = work / "finish_update.ps1"
    script.write_text(update_script(new_app, ROOT, os.getpid(), restart_command(), logs / "update.log"),
                      encoding="utf-8-sig")
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
            "-File", str(script)]


def run_detached(cmd):
    """Starts the finishing script on its own (it outlives this app), with no window."""
    flags = 0x08000000 | 0x00000200   # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(cmd, creationflags=flags, close_fds=True)
