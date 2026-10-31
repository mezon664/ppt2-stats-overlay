"""Local WebSocket server broadcasting the live match state to any connected client
(the desktop HUD and the OBS browser-source overlay both connect to this same
server, as required: capture/recognition runs once, display is decoupled from it).

Usage:
  python data_server.py --source video --path "<video file>" --speed 1.0
  python data_server.py --source live
"""
import argparse
import asyncio
import json
import logging
import threading
import time
from pathlib import Path

import sys

import cv2
import websockets

# The full package's bundled Python doesn't put this script's own folder on
# the import path (its ._pth file fixes the path), so do it here.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from live_pipeline import MatchPipeline, VideoReplaySource  # noqa: E402
from config_store import load_settings, display_settings, CONFIG_PATH
from i18n import capture_message_en

# Changes when the OBS page's files change (an update, a new cat clip): the
# page reloads itself when it sees a different value (obs/overlay.html).
_PAGE_FILES = ("obs/overlay.html", "assets/cat/cat.js")
_ROOT = Path(__file__).resolve().parent.parent
PAGE_REV = "-".join(str(int((_ROOT / f).stat().st_mtime)) if (_ROOT / f).exists() else "0" for f in _PAGE_FILES)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("data_server")

CLIENTS = set()
PROJECT_DIR = Path(__file__).resolve().parent.parent
DEBUG_DIR = PROJECT_DIR / "debug_frames"
_DEBUG = load_settings().get("debug", {})
# Saving raw frames around recognition events is a developer option
# (settings "debug.save_frames"), off by default.
DEBUG_DUMP_DIR = str(DEBUG_DIR) if _DEBUG.get("save_frames") else None
DEBUG_MAX_FILES = int(_DEBUG.get("max_files", 2000))
RUN_STARTED = time.time()
# wait_for_start: the server may start on a menu or result screen that
# still shows the NEXT queues; count nothing until a match is confirmed.
PIPELINE = MatchPipeline(debug_dump_dir=DEBUG_DUMP_DIR, wait_for_start=True)


def prune_debug_frames():
    """Keeps at most DEBUG_MAX_FILES frames saved by THIS run (oldest go
    first). Files from earlier runs — and recordings in sub-folders — are
    left alone."""
    if not DEBUG_DUMP_DIR or not DEBUG_DIR.exists():
        return
    try:
        mine = [p for p in DEBUG_DIR.glob("*.png") if p.stat().st_mtime >= RUN_STARTED]
        if len(mine) <= DEBUG_MAX_FILES:
            return
        mine.sort(key=lambda p: p.stat().st_mtime)
        for p in mine[:len(mine) - DEBUG_MAX_FILES]:
            p.unlink(missing_ok=True)
    except Exception as e:
        log.warning("couldn't prune debug frames: %s", e)
CAPTURE_STATUS = {"ok": False, "message": "starting"}


def capture_loop_video(path, speed, realtime):
    global CAPTURE_STATUS
    try:
        source = VideoReplaySource(path, speed=speed, realtime=realtime)
        CAPTURE_STATUS = {"ok": True, "message": f"replaying {path}"}
        for frame, t in source:
            PIPELINE.process_frame(frame, t)
        CAPTURE_STATUS = {"ok": False, "message": "replay finished"}
    except Exception as e:
        log.exception("video capture loop failed")
        CAPTURE_STATUS = {"ok": False, "message": f"error: {e}"}


def capture_loop_live(fps_target=15):
    """Live game-window capture. See live_capture.py for the window-finding /
    minimized-window handling; kept separate so this module stays testable without
    a running game."""
    global CAPTURE_STATUS
    from live_capture import GameWindowCapture
    cap = GameWindowCapture()
    period = 1.0 / fps_target
    t0 = time.monotonic()
    while True:
        loop_start = time.monotonic()
        frame, ok, reason, profile = cap.grab()
        if ok:
            PIPELINE.rebuild_for_profile(profile)
            CAPTURE_STATUS = {
                "ok": True, "message": "capturing",
                "client_size": f"{profile.client_w}x{profile.client_h}", "scale": round(profile.scale_x, 3),
            }
            PIPELINE.process_frame(frame, time.monotonic() - t0)
        elif reason is None:
            pass  # window size still settling (live_capture.SizeSettler): keep the last status
        else:
            CAPTURE_STATUS = {"ok": False, "message": reason, "message_en": capture_message_en(reason)}
        elapsed = time.monotonic() - loop_start
        if elapsed < period:
            time.sleep(period - elapsed)


def _debug_tspin_peak(side_pipeline, window_s=3.0):
    """Temporary diagnostic (phase3 live T-SPIN miss investigation): max confidence
    seen for tspin_double/tspin_single in the trailing window_s seconds, so we can
    tell a near-miss (score just under threshold) apart from a complete non-match
    (score near 0, implying wrong window/template entirely) without needing to
    capture raw frames from a live session after the fact."""
    log_entries = side_pipeline.tracker.match_log
    if not log_entries:
        return None
    now = log_entries[-1][0]
    best = {}
    for t, label, conf, pos in reversed(log_entries):
        if now - t > window_s:
            break
        if label in ("tspin_double", "tspin_single"):
            if label not in best or conf > best[label][0]:
                best[label] = (conf, pos)
    return best


async def broadcaster():
    settings = load_settings()
    hz = settings.get("server", {}).get("broadcast_hz", 10)
    period = 1.0 / hz
    tick = 0
    display = display_settings(settings)
    settings_mtime = CONFIG_PATH.stat().st_mtime if CONFIG_PATH.exists() else None
    while True:
        tick += 1
        if tick % (hz * 30) == 0:  # ~30s
            await asyncio.get_running_loop().run_in_executor(None, prune_debug_frames)
        if tick % hz == 0:  # ~1s: pick up display changes saved to the settings file
            try:
                mtime = CONFIG_PATH.stat().st_mtime
                if mtime != settings_mtime:
                    settings_mtime = mtime
                    display = display_settings(load_settings())
                    log.info("display settings: %s", display)
            except Exception as e:  # mid-save or invalid JSON: keep the last good values
                log.warning("couldn't read settings (%s); keeping %s", e, display)
        if DEBUG_DUMP_DIR and tick % (hz * 2) == 0:  # every ~2s, developer option only
            for side_name, pp in (("left", PIPELINE.left), ("right", PIPELINE.right)):
                peak = _debug_tspin_peak(pp)
                if peak:
                    log.info("[debug tspin peak %s] %s", side_name, peak)
        state = PIPELINE.snapshot()
        state["capture"] = CAPTURE_STATUS
        state["display"] = display
        state["page_rev"] = PAGE_REV
        payload = json.dumps(state, ensure_ascii=False)
        dead = set()
        # A copy: each send awaits, and a client disconnecting meanwhile is
        # removed from CLIENTS by its handler, which crashed the whole server
        # ("Set changed size during iteration") when iterating the set itself.
        for ws in list(CLIENTS):
            try:
                await ws.send(payload)
            except Exception:
                dead.add(ws)
        CLIENTS.difference_update(dead)
        await asyncio.sleep(period)


async def handler(websocket):
    CLIENTS.add(websocket)
    log.info("client connected (%d total)", len(CLIENTS))
    try:
        async for _ in websocket:
            pass  # this server doesn't expect incoming messages
    finally:
        CLIENTS.discard(websocket)
        log.info("client disconnected (%d total)", len(CLIENTS))


async def main_async(host, port):
    async with websockets.serve(handler, host, port):
        log.info("serving ws://%s:%d", host, port)
        await broadcaster()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["video", "live"], required=True)
    parser.add_argument("--path", help="video file path, required for --source video")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--realtime", type=lambda s: s != "false", default=True)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    settings = load_settings()
    host = args.host or settings["server"]["host"]
    port = args.port or settings["server"]["port"]

    if args.source == "video":
        if not args.path:
            parser.error("--path is required for --source video")
        t = threading.Thread(target=capture_loop_video, args=(args.path, args.speed, args.realtime), daemon=True)
    else:
        t = threading.Thread(target=capture_loop_live, daemon=True)
    t.start()

    asyncio.run(main_async(host, port))


if __name__ == "__main__":
    main()
