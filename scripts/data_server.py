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
from logging.handlers import RotatingFileHandler
import os
import socketserver
import threading
import time
from pathlib import Path

import sys

import cv2
import websockets

# OpenCV's own worker threads: with them a frame finished a little sooner
# (24 vs 29 ms of the 67 ms it has at 15 a second) but took 46 ms of CPU
# instead of 29 (measured on burst_english / burst_boundary). One thread
# leaves more of the PC to the game (user: make the app lighter).
cv2.setNumThreads(1)

# The full package's bundled Python doesn't put this script's own folder on
# the import path (its ._pth file fixes the path), so do it here.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from live_pipeline import MatchPipeline, VideoReplaySource  # noqa: E402
from config_store import load_settings, display_settings, CONFIG_PATH
from i18n import capture_message_en
from server_control import handle_control_message

# Changes when the OBS page's files change (an update, a new cat clip): the
# page reloads itself when it sees a different value (obs/overlay.html).
_PAGE_FILES = ("obs/overlay.html", "assets/cat/cat.js", "assets/challenge_cats/clips.js")
_ROOT = Path(__file__).resolve().parent.parent
PAGE_REV = "-".join(str(int((_ROOT / f).stat().st_mtime)) if (_ROOT / f).exists() else "0" for f in _PAGE_FILES)

_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
if "pytest" in sys.modules:   # (the tests' made-up matches kept out of the real log: they were read as play)
    import tempfile
    _LOG_DIR = Path(tempfile.gettempdir()) / "pptetrics-test-logs"
_LOG_DIR.mkdir(exist_ok=True)
_server_log_handler = RotatingFileHandler(
    _LOG_DIR / "server.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
# force: live_pipeline (imported above) already set up logging to the
# console, and without it this was ignored — nothing reached server.log
# after that (found looking into an opener not recognized live).
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    handlers=[_server_log_handler], force=True)
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


# Off the match screen (home, menus, character select) for a while, the game
# is read fewer times a second: reading the window alone took ~28% of a CPU
# core at 15 a second with nothing to recognize (user: make the app lighter).
# Nothing there needs the full rate: the screen goes black as a match is left
# (that reset is seen at the full rate, from the match screen — every blackout
# in the 13 recordings came right after match-screen frames), and coming back
# to the match screen is seen within 1/IDLE_FPS s, seconds before GO!.
IDLE_FPS = 5
IDLE_AFTER_S = 3.0


def idle_period(reason, since, now, period):
    """The time between reads: longer once off the match screen IDLE_AFTER_S."""
    if reason == "no_match_ui" and since is not None and now - since >= IDLE_AFTER_S:
        return max(period, 1.0 / IDLE_FPS)
    return period


_RATING = {"reader": None, "failed": False}

# 今日の成績 (scripts/session_stats.py): since the game process started, and
# which side was you in the match under way
SESSION = {"since": None, "pid": None, "match_you": None, "match_rated": False, "resets": None, "key": None,
           "out": None}
# the "You" card on the まちうけ screen counts for a match starting this soon after
YOU_SEEN_S = 90.0


def game_started_at(cap):
    """When the game's process started (a timestamp), or None (no game)."""
    hwnd = getattr(cap, "hwnd", None)
    try:
        import win32gui
        import win32process
        import psutil
        if not hwnd or not win32gui.IsWindow(hwnd):
            return None
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid != SESSION["pid"]:
            SESSION["pid"], SESSION["started"] = pid, psutil.Process(pid).create_time()
        return SESSION["started"]
    except Exception:
        return None


OVERLAY_CHECK_S = 5.0
_OVERLAY = {"t": 0.0, "pid": None}


def ours_in_capture(cap):
    """True when a visible window of this app (the launcher's process: HUD,
    settings) over the game isn't kept out of screen captures — the screen
    then shows it over the game, and the recognition saw the HUD's numbers
    where T-SPIN banners show. Checked every OVERLAY_CHECK_S."""
    import ctypes
    import win32gui
    import win32process
    game = getattr(cap, "hwnd", None)
    pid = _OVERLAY.get("pid")
    if not game or not pid or not win32gui.IsWindow(game):
        return False
    try:
        gl, gt = win32gui.ClientToScreen(game, (0, 0))
        _, _, gw, gh = win32gui.GetClientRect(game)
    except Exception:
        return False
    found = []

    def check(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd) or win32process.GetWindowThreadProcessId(hwnd)[1] != pid:
                return True
            l, t, r, b = win32gui.GetWindowRect(hwnd)
            if r <= gl or l >= gl + gw or b <= gt or t >= gt + gh:
                return True
            got = ctypes.c_uint32(0)
            ctypes.windll.user32.GetWindowDisplayAffinity(hwnd, ctypes.byref(got))
            if got.value != 0x11:   # WDA_EXCLUDEFROMCAPTURE
                found.append(hwnd)
        except Exception:
            pass
        return True
    win32gui.EnumWindows(check, None)
    return bool(found)


def follow_overlay(cap):
    now = time.monotonic()
    if cap is None or now - _OVERLAY["t"] < OVERLAY_CHECK_S:
        return
    _OVERLAY["t"] = now
    try:
        inside = ours_in_capture(cap)
    except Exception:
        inside = False
    if inside != getattr(cap, "window_only", False):
        log.info("a window of this app over the game %s kept out of screen captures: reading %s",
                 "isn't" if inside else "is", "the game's own window" if inside else "the screen")
        cap.window_only = inside


LAST_FRAME = {"frame": None}
_COMMENTS = None


_NAMES = None


def name_reader():
    """The players' names (scripts/player_names.py), kept across states."""
    global _NAMES
    if _NAMES is None:
        import player_names
        _NAMES = player_names.NameReader()
    return _NAMES


def comment_stream():
    """縛りプレイ's comments (scripts/comments.py), kept across states."""
    global _COMMENTS
    if _COMMENTS is None:
        import comments
        _COMMENTS = comments.CommentStream()
    return _COMMENTS
_GARBAGE_HOLD = None


def _garbage_hold():
    global _GARBAGE_HOLD
    if _GARBAGE_HOLD is None:
        import mosaic
        _GARBAGE_HOLD = mosaic.GarbageHold()
    return _GARBAGE_HOLD


def garbage_rows_of(frame, side, prev=0):
    """That side's garbage rows at the bottom of the board (mosaic.count_garbage,
    as the HUD reads them itself)."""
    import mosaic
    k = frame.shape[1] / mosaic.REFERENCE_W
    x1, y1, x2, y2 = (int(round(v * k)) for v in mosaic.GRID[side])
    return mosaic.count_garbage(frame[y1:y2, x1:x2], prev)
_MOSAIC_BASE = {"key": None, "usual": None, "events": None}


def your_board(display, state):
    """Your board now ({"garbage", "height"}), for the comments; None when they're off."""
    if display.get("challenge_comments", "off") == "off" or LAST_FRAME["frame"] is None:
        return None
    if state.get("match_screen") is not True or state.get("frozen"):
        return None
    import mosaic
    you = state.get("you_side") if state.get("you_side") in ("left", "right") else "left"
    return mosaic.board_now(LAST_FRAME["frame"], you)


def usual_numbers():
    """Your usual APM / PPS / attack over your last matches (mosaic.usual), worked
    out again when the kept matches change (the mosaic and the comments)."""
    import mosaic
    import opener_stats
    try:
        key = opener_stats.HISTORY_PATH.stat().st_mtime
    except OSError:
        key = None
    if key != _MOSAIC_BASE["key"] or _MOSAIC_BASE["usual"] is None:
        _MOSAIC_BASE["key"] = key
        _MOSAIC_BASE["usual"] = mosaic.usual(opener_stats.load())
    return _MOSAIC_BASE["usual"]


def mosaic_state(display, state):
    """縛りプレイ: the mosaic's strength over your board and, for OBS, its
    coarse picture (scripts/mosaic.py). Your usual numbers come from the
    kept matches, worked out again when that file changes."""
    import mosaic
    if display.get("challenge_mosaic", "off") == "off":
        return None
    usual_numbers()
    if _MOSAIC_BASE["events"] is None:
        _MOSAIC_BASE["events"] = mosaic.EventLevel()   # ("events": goes up and fades over time)
    return mosaic.state_for(display, state, LAST_FRAME["frame"], _MOSAIC_BASE["usual"], _MOSAIC_BASE["events"])


def follow_session(cap):
    """The game's start time, and at each new match which side is you."""
    SESSION["since"] = game_started_at(cap)
    resets = getattr(PIPELINE, "match_reset_count", None)
    if resets != SESSION["resets"]:
        SESSION["resets"] = resets
        reader = _RATING.get("reader")
        seen = getattr(reader, "you_seen_t", None)
        recent = seen is not None and time.monotonic() - seen <= YOU_SEEN_S
        SESSION["match_you"] = getattr(reader, "you_side", None) if recent else None
        SESSION["match_rated"] = rated_match(recent, getattr(reader, "club", None))


def rated_match(you_seen_recently, club):
    """A rated (league) match: the まちうけ screen with your "You" card came
    just before it, and not from a club room (which shows the same card).
    A club room seen before nothing else (club None: the app started there
    without a club screen yet) can't be told: counted as rated."""
    return bool(you_seen_recently) and club is not True


def session_state():
    """state["session"]: the summary and its lines in both languages, or None.
    Worked out again only when the game session or a kept file changes."""
    import opener_stats
    import rating
    import session_stats

    def mtime(p):
        try:
            return p.stat().st_mtime
        except OSError:
            return None
    key = (SESSION["since"], mtime(opener_stats.HISTORY_PATH), mtime(rating.HISTORY_PATH))
    if key != SESSION["key"]:
        SESSION["key"] = key
        summary = session_stats.summarize(opener_stats.load(), rating.load(), SESSION["since"])
        SESSION["out"] = None if summary is None else {
            "summary": summary,
            "lines": {lang: session_stats.lines(summary, lang) for lang in ("ja", "en")}}
    return SESSION["out"]


def read_rating(frame, cap=None):
    """Off the match screen, your online rating (パズルリーグ etc.) is read
    off the まちうけ / league menu screens and kept per league (scripts/rating.py,
    user: see how the rating moves). Never stops recognition."""
    if _RATING["failed"]:
        return
    gate = getattr(PIPELINE, "gameplay_gate", None)
    if getattr(gate, "last_reason", None) != "no_match_ui":
        return
    try:
        if _RATING["reader"] is None:
            import rating
            _RATING["reader"] = rating.RatingReader()
            for p in rating.load():   # each league's last kept one
                _RATING["reader"].set_last(p["league"], p["rating"])
        import rating
        is_covered = None
        if cap is not None:
            def is_covered(box):
                return rating.covered(getattr(cap, "hwnd", None), getattr(cap, "last_client_origin", None),
                                      getattr(cap, "last_client_size", None), (frame.shape[1], frame.shape[0]), box)
        read = _RATING["reader"].update(frame, is_covered=is_covered)
        if read is not None:
            league, value = read
            if rating.add(league, value):
                log.info("rating read: %s %d", league, value)
    except Exception:
        log.exception("reading the rating failed; not trying again this run")
        _RATING["failed"] = True


def capture_loop_live(fps_target=15, stop_event=None, capture_factory=None):
    """Live game-window capture. See live_capture.py for the window-finding /
    minimized-window handling; kept separate so this module stays testable without
    a running game."""
    global CAPTURE_STATUS
    from live_capture import GameWindowCapture
    from diagnostic import Diagnostic
    make_capture = capture_factory or GameWindowCapture
    diag = Diagnostic()
    cap = None
    period = 1.0 / fps_target
    t0 = time.monotonic()
    consecutive_errors = 0
    last_error = None
    last_error_log_t = 0.0
    away_since = None   # when the game left the match screen (see idle_period)
    while stop_event is None or not stop_event.is_set():
        loop_start = time.monotonic()
        try:
            if cap is None:
                cap = make_capture()
            frame, ok, reason, profile = cap.grab()
            follow_session(cap)   # (also when the game is gone: the session ends)
            follow_overlay(cap)
            if ok:
                PIPELINE.rebuild_for_profile(profile)
                PIPELINE.process_frame(frame, time.monotonic() - t0)
                LAST_FRAME["frame"] = frame   # (縛りプレイのモザイク: mosaic_state)
                read_rating(frame, cap)
                CAPTURE_STATUS = {
                    "ok": True, "message": "capturing",
                    # the game's picture inside the window (black bars cut off), for the HUD
                    "picture": list(getattr(cap, "last_picture", None) or ()),
                    "client_size": f"{profile.client_w}x{profile.client_h}", "scale": round(profile.scale_x, 3),
                }
                consecutive_errors = 0
                last_error = None
            elif reason is None:
                pass  # window size still settling; keep the last useful status
            else:
                CAPTURE_STATUS = {"ok": False, "message": reason, "message_en": capture_message_en(reason)}
                if reason.startswith("キャプチャに失敗しました"):
                    close = getattr(cap, "close", None)
                    if close:
                        close()
                    cap = None  # recreate the capture backend before retrying
            if diag.due():   # logs/last_seen.jpg + last_status.txt, for "the numbers don't move" reports
                diag.write(frame if ok else None, diag.lines(CAPTURE_STATUS, PIPELINE, cap))
        except Exception as e:
            consecutive_errors += 1
            CAPTURE_STATUS = {
                "ok": False,
                "message": f"認識処理でエラーが発生しました: {type(e).__name__}",
                "message_en": f"Capture/recognition error ({type(e).__name__}); retrying",
            }
            error_key = (type(e).__name__, str(e))
            now = time.monotonic()
            if error_key != last_error or now - last_error_log_t >= 30:
                log.exception("live capture/recognition iteration failed; retrying")
                last_error, last_error_log_t = error_key, now
            close = getattr(cap, "close", None) if cap is not None else None
            if close:
                try:
                    close()
                except Exception:
                    log.debug("failed to close capture backend after error", exc_info=True)
            cap = None
            retry_delay = min(period * (2 ** min(consecutive_errors - 1, 6)), 5.0)
            if stop_event is not None and stop_event.wait(retry_delay):
                break
            if stop_event is None:
                time.sleep(retry_delay)
            continue
        reason = getattr(getattr(PIPELINE, "gameplay_gate", None), "last_reason", None)
        if reason != "no_match_ui":
            away_since = None
        elif away_since is None:
            away_since = loop_start
        wait = idle_period(reason, away_since, time.monotonic(), period)
        elapsed = time.monotonic() - loop_start
        if elapsed < wait:
            if stop_event is not None:
                stop_event.wait(wait - elapsed)
            else:
                time.sleep(wait - elapsed)
    close = getattr(cap, "close", None) if cap is not None else None
    if close:
        close()


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
        state["you_side"] = SESSION["match_you"] or "left"   # kept with the match (opener_stats.match_record)
        state["rated_match"] = SESSION["match_rated"]         # (display.hide_in_rated)
        # 縛りプレイ as it is now (all off in a rated match, if asked: challenge_off_in_rated)
        from config_store import challenge_display
        ch_display = challenge_display(display, state)
        try:   # the players' names (for the comments), read off the screen
            state["names"] = name_reader().update(state, LAST_FRAME["frame"]) \
                if ch_display.get("challenge_comments", "off") != "off" else {}
        except Exception:
            log.exception("reading the players' names failed")
            state["names"] = {}
        try:
            state["comments"] = comment_stream().update(ch_display, state, time.monotonic(), usual_numbers(),
                                                        your_board(ch_display, state))
        except Exception:
            log.exception("the comments failed")
            state["comments"] = None
        try:
            import mosaic
            state["challenge_garbage"] = mosaic.garbage_state(ch_display, state, LAST_FRAME["frame"], garbage_rows_of,
                                                              _garbage_hold())
        except Exception:
            log.exception("counting the garbage rows failed")
            state["challenge_garbage"] = None
        try:
            state["challenge_mosaic"] = mosaic_state(ch_display, state)
        except Exception:
            log.exception("the challenge mosaic failed")
            state["challenge_mosaic"] = None
        try:
            state["session"] = session_state()
        except Exception:
            log.exception("working out the session's results failed")
            state["session"] = None
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


class _ControlServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = False
    daemon_threads = True


def _start_control_server(host, port, instance_id, control_token, loop, stop_event):
    class ControlHandler(socketserver.StreamRequestHandler):
        def setup(self):
            self.request.settimeout(2.0)
            super().setup()

        def handle(self):
            try:
                raw = self.rfile.readline(16385)
                if len(raw) > 16384:
                    return
                request = json.loads(raw.decode("utf-8"))
                response, stop_after_response = handle_control_message(
                    request, instance_id, control_token, os.getpid())
                if stop_after_response:
                    log.info("shutdown request accepted instance_id=%s", instance_id)
                elif request.get("command") == "shutdown":
                    log.warning("shutdown request rejected instance_id=%s", instance_id)
                self.wfile.write((json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8"))
                self.wfile.flush()
                if stop_after_response:
                    loop.call_soon_threadsafe(stop_event.set)
            except Exception:
                log.exception("control request failed instance_id=%s", instance_id)

    server = _ControlServer((host, port), ControlHandler)
    thread = threading.Thread(target=server.serve_forever, name="pptetrics-control", daemon=True)
    thread.start()
    return server


async def main_async(host, port, control_host=None, control_port=None, instance_id=None, control_token=None):
    async with websockets.serve(handler, host, port):
        log.info("serving ws://%s:%d", host, port)
        if instance_id:
            loop = asyncio.get_running_loop()
            stop_event = asyncio.Event()
            control_server = _start_control_server(
                control_host or "127.0.0.1", control_port, instance_id, control_token, loop, stop_event)
            task = asyncio.create_task(broadcaster())
            log.info("server ready instance_id=%s pid=%d control_port=%d", instance_id, os.getpid(), control_port)
            try:
                stop_task = asyncio.create_task(stop_event.wait())
                done, pending = await asyncio.wait(
                    (task, stop_task), return_when=asyncio.FIRST_COMPLETED)
                if task in done:
                    task.result()  # propagate broadcaster failures as before
            finally:
                for pending_task in (task, locals().get("stop_task")):
                    if pending_task is not None and not pending_task.done():
                        pending_task.cancel()
                await asyncio.gather(task, locals().get("stop_task"), return_exceptions=True)
                control_server.shutdown()
                control_server.server_close()
                log.info("server stopped instance_id=%s", instance_id)
        else:
            # Backward-compatible standalone invocation without launcher control.
            await broadcaster()


def watch_parent(pid, interval=2.0):
    """Ends this server when the launcher that started it is gone. A normal
    quit stops the server through the control channel, but if the app was
    killed or crashed the server stayed behind (users: pythonw.exe kept
    running after closing the app; the next start then attached to that old
    server and showed nothing until it was killed in Task Manager)."""
    import psutil

    try:
        parent = psutil.Process(pid)
        started = parent.create_time()
    except psutil.Error:
        log.warning("launcher pid %d not found at start; exiting", pid)
        os._exit(0)

    def run():
        while True:
            time.sleep(interval)
            try:
                alive = parent.is_running() and parent.create_time() == started                     and parent.status() != psutil.STATUS_ZOMBIE
            except psutil.Error:
                alive = False
            if not alive:
                log.info("the launcher (pid %d) is gone; stopping the server", pid)
                logging.shutdown()
                os._exit(0)

    threading.Thread(target=run, name="pptetrics-parent-watch", daemon=True).start()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["video", "live"], required=True)
    parser.add_argument("--path", help="video file path, required for --source video")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--realtime", type=lambda s: s != "false", default=True)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--control-host", default=None)
    parser.add_argument("--control-port", type=int, default=None)
    parser.add_argument("--instance-id", default=None)
    parser.add_argument("--control-token", default=None)
    parser.add_argument("--parent-pid", type=int, default=None)
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

    if args.parent_pid:
        watch_parent(args.parent_pid)
        _OVERLAY["pid"] = args.parent_pid   # the HUD and the settings window live there
    if bool(args.instance_id) != bool(args.control_token) or (args.instance_id and not args.control_port):
        parser.error("--instance-id, --control-token and --control-port must be supplied together")
    try:
        asyncio.run(main_async(host, port, args.control_host, args.control_port,
                               args.instance_id, args.control_token))
    except OSError:
        log.exception("server failed to bind ws://%s:%d", host, port)
        raise


if __name__ == "__main__":
    main()
