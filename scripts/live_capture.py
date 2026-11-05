"""Finds the running PuyoPuyoTetris2 window and captures it with mss.

Honors the Phase-1 finding: a minimized window's reported rect is garbage
(-32000,-32000), and GDI/mss-style capture cannot read a minimized or fully
occluded window at all. Rather than silently showing stale or wrong numbers, this
reports a clear "capture unavailable" reason so the HUD/OBS layers can say so
instead of guessing.

Fullscreen is not supported, and says so. The game's fullscreen covers the
monitor (no title bar, always-on-top, display mode unchanged) and owns the
screen: measured live, mss and PrintWindow both return pure black, Desktop
Duplication (dxcam) mostly hit DXGI access-lost errors and never once showed
the match screen, and any window placed over the game (even one that never
takes focus) made the game drop out of fullscreen and minimize — while the
click-through HUD above it simply wasn't drawn. Getting past that means hooking
the game's rendering (how Discord's overlay / OBS game capture work), which the
project rules out. So in fullscreen this reports a reason asking for windowed
mode instead of feeding black frames to recognition.

Windowed fullscreen (borderless: a window exactly the size of the monitor,
user's request 2026-11-04) is just a window and captures like one. It has the
same size and place as the real fullscreen, so the two are told apart by what
Windows says (an exclusive Direct3D fullscreen app is running:
SHQueryUserNotificationState) and, should that not be reported, by the
capture staying black (FULLSCREEN_BLACK_S).
"""
import time

import mss
import numpy as np
import win32api
import win32gui
import win32process
import psutil

import cv2

from capture_profile import compute_profile, REFERENCE_W

# A bigger game window is shrunk to the reference width before recognition:
# every template and box was made at that size, and recognition time grows
# with the pixels (user report from a 2155-wide window: T-SPINs and clear
# flashes missed, REN counts off — too few frames a second got read). All 13
# recordings give the same events shrunk, at about half the time per frame.
WORK_W = REFERENCE_W


def shrink_for_recognition(frame):
    """frame at most WORK_W wide (same aspect), and its profile."""
    h, w = frame.shape[:2]
    if w > WORK_W:
        h = round(h * WORK_W / w)
        frame = cv2.resize(frame, (WORK_W, h), interpolation=cv2.INTER_AREA)
        w = WORK_W
    return frame, compute_profile(w, h)

PROCESS_NAME = "PuyoPuyoTetris2.exe"

# Black bars around the game's picture (a window a little wider or taller
# than 16:9: the game keeps its picture 16:9 and fills the rest with black).
# Everything is placed from the picture, not the window, so the bars are cut
# off first. Left in, every box was off by up to the bar's width and the scale
# a few % big: with 2.5% of bars, the T-SPINs of the recordings went 4 -> 0
# and 4 -> 1 (a user's T-SPINs went uncounted, the HUD a little to the left).
BAR_DARK = 12          # brightest a bar's pixel may be (the game's black is 0)
BAR_STEP = 4           # every 4th pixel is looked at
BAR_SAME_READS = 3     # the same bars this many frames in a row before they're used
BAR_ASPECT_TOL = 0.015 # what's left must be this close to 16:9 (else it's dark picture, not bars)


def find_picture(frame):
    """(x, y, w, h) of the game's picture inside black bars, the whole frame
    when there are none, or None for a frame that's (nearly) all black."""
    from capture_profile import REFERENCE_ASPECT
    h, w = frame.shape[:2]
    small = frame[::BAR_STEP, ::BAR_STEP].max(axis=2)
    cols = np.flatnonzero(small.max(axis=0) > BAR_DARK)
    rows = np.flatnonzero(small.max(axis=1) > BAR_DARK)
    if len(cols) == 0 or len(rows) == 0:
        return None
    # the edges to the pixel: only the few lines around each rough one are looked at
    def first_lit(lines):
        for i in lines:
            if 0 <= i < len(profile) and profile[i] > BAR_DARK:
                return i
        return None
    profile = frame[::BAR_STEP, :].max(axis=2).max(axis=0)
    x1 = first_lit(range(int(cols[0]) * BAR_STEP - BAR_STEP, int(cols[0]) * BAR_STEP + BAR_STEP))
    x2 = first_lit(range(int(cols[-1]) * BAR_STEP + 2 * BAR_STEP, int(cols[-1]) * BAR_STEP - BAR_STEP, -1))
    x1 = int(cols[0]) * BAR_STEP if x1 is None else x1
    x2 = min(w, (int(cols[-1]) + 1) * BAR_STEP) if x2 is None else x2 + 1
    profile = frame[:, ::BAR_STEP].max(axis=2).max(axis=1)
    y1 = first_lit(range(int(rows[0]) * BAR_STEP - BAR_STEP, int(rows[0]) * BAR_STEP + BAR_STEP))
    y2 = first_lit(range(int(rows[-1]) * BAR_STEP + 2 * BAR_STEP, int(rows[-1]) * BAR_STEP - BAR_STEP, -1))
    y1 = int(rows[0]) * BAR_STEP if y1 is None else y1
    y2 = min(h, (int(rows[-1]) + 1) * BAR_STEP) if y2 is None else y2 + 1
    full = (0, 0, w, h)
    # bars on one axis only, the same on both sides (the game centers its picture)
    side_x, side_y = (x1, w - x2), (y1, h - y2)
    if abs(side_x[0] - side_x[1]) > 2 * BAR_STEP or abs(side_y[0] - side_y[1]) > 2 * BAR_STEP:
        return full
    if min(side_x) >= BAR_STEP and min(side_y) < BAR_STEP:       # pillarbox
        rect = (x1, 0, x2 - x1, h)
    elif min(side_y) >= BAR_STEP and min(side_x) < BAR_STEP:     # letterbox
        rect = (0, y1, w, y2 - y1)
    else:
        return full
    if abs(rect[2] / rect[3] - REFERENCE_ASPECT) / REFERENCE_ASPECT > BAR_ASPECT_TOL:
        return full   # not a 16:9 picture: dark picture at the edges, not bars
    return rect


class PictureFinder:
    """find_picture, kept steady: a new rectangle is used once it's been the
    same (within a few pixels) BAR_SAME_READS frames in a row; black frames
    keep the last one."""

    def __init__(self):
        self.rect = None
        self._pending, self._count = None, 0

    def update(self, frame):
        h, w = frame.shape[:2]
        if self.rect is not None and (self.rect[0] + self.rect[2] > w or self.rect[1] + self.rect[3] > h):
            self.rect = None   # the window got smaller
        found = find_picture(frame)
        if found is not None:
            close = self._pending is not None and all(abs(a - b) <= BAR_STEP for a, b in zip(found, self._pending))
            self._pending, self._count = (self._pending, self._count + 1) if close else (found, 1)
            if self._count >= BAR_SAME_READS:
                self.rect = self._pending
        return self.rect or (0, 0, w, h)

FULLSCREEN_REASON = "フルスクリーンでは認識できません (ゲームをウインドウモードにしてください)"

# A new client size is only used once it has held this long. Entering/leaving
# fullscreen and focus changes report a transient size for a frame or two
# (2544 / 2576 wide around the real 2560, seen live), and every size change
# rebuilds the trackers — which wiped the match's numbers each time.
SIZE_SETTLE_S = 0.5


def covers_monitor(left, top, width, height, monitor_rect):
    """True when the client area is exactly the monitor: the game's
    fullscreen, or a windowed (borderless) fullscreen."""
    return (left, top, left + width, top + height) == tuple(monitor_rect)


# Seconds of an all-black capture of a monitor-sized game before it's taken
# as the real fullscreen (black there: measured 0 brightness). Longer than a
# loading screen's black, which recognition must still see (the numbers are
# cleared on a black screen).
FULLSCREEN_BLACK_S = 3.0
QUNS_RUNNING_D3D_FULL_SCREEN = 3


def exclusive_fullscreen_running():
    """True when Windows reports an exclusive Direct3D fullscreen app (not a
    borderless window). False when it can't be asked."""
    try:
        import ctypes
        state = ctypes.c_int(0)
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
            return False
        return state.value == QUNS_RUNNING_D3D_FULL_SCREEN
    except Exception:
        return False


def is_black(frame):
    """Every sampled pixel (near) black."""
    return int(frame[::8, ::8].max()) <= 8


class SizeSettler:
    """Holds back a changed client size until it has been stable for settle_s.
    The very first size is taken at once (nothing to protect yet)."""

    def __init__(self, settle_s=SIZE_SETTLE_S):
        self.settle_s = settle_s
        self.accepted = None
        self._pending = None
        self._pending_since = None

    def update(self, size, now):
        """True when frames of this size may be used now."""
        if self.accepted is None or size == self.accepted:
            self.accepted, self._pending = size, None
            return True
        if size != self._pending:
            self._pending, self._pending_since = size, now
            return False
        if now - self._pending_since >= self.settle_s:
            self.accepted, self._pending = size, None
            return True
        return False


def find_game_hwnd():
    """NOTE: the callback always returns True (never stops enumeration early by
    returning False). Confirmed by direct testing: pywin32's EnumWindows wrapper
    can't distinguish "callback asked to stop" from "the underlying Win32 API call
    itself failed" — a callback that returns False to stop early makes it raise
    pywintypes.error(2, 'EnumWindows', ...) even though nothing actually went
    wrong. Letting it run to completion (33 windows, a few ms) and just keeping the
    first match in a closure variable avoids this entirely."""
    target_hwnd = None

    def callback(hwnd, _):
        nonlocal target_hwnd
        if target_hwnd is not None:
            return True
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            name_matches = proc.name().lower() == PROCESS_NAME.lower()
            has_title = bool(win32gui.GetWindowText(hwnd))
        except Exception:
            # Some system windows raise transient win32 errors on these calls —
            # not a reason to abort the whole enumeration.
            return True
        if name_matches and has_title:
            target_hwnd = hwnd
        return True

    win32gui.EnumWindows(callback, None)
    return target_hwnd


class GameWindowCapture:
    def __init__(self):
        self.sct = mss.mss()
        self.hwnd = None
        self._sizes = SizeSettler()
        self.last_client_size = None   # the game window's size before shrinking (diagnostic.py)
        self.last_client_origin = None # its top-left on the screen (rating.covered: what's over a box)
        self._black_since = None       # monitor-sized and black since then (FULLSCREEN_BLACK_S)
        self._picture = PictureFinder()
        self.last_picture = None       # the game's picture inside the client area (x, y, w, h), bars cut off

    def close(self):
        """Release the screen-capture handle before rebuilding after an error."""
        self.sct.close()

    def grab(self):
        """Returns (frame_bgr_or_None, ok, reason, profile_or_None).

        Captures the window's CLIENT area, not the outer window rect.
        GetWindowRect() (used in an earlier version) includes the title bar and
        borders, which recorded video (what every coordinate in board_read.py /
        banner_detect.py was calibrated against) never has — using it would offset
        every recognition box by the border/titlebar thickness. GetClientRect() +
        ClientToScreen() gives the actual rendered-content area in screen
        coordinates, matching what a recording shows.
        """
        if self.hwnd is None or not win32gui.IsWindow(self.hwnd):
            self.hwnd = find_game_hwnd()
            if self.hwnd is None:
                return None, False, "ゲームのウインドウが見つかりません (起動していますか？)", None

        if win32gui.IsIconic(self.hwnd):
            return None, False, "ゲームが最小化されています (認識にはウインドウ表示が必要です)", None

        client_rect = win32gui.GetClientRect(self.hwnd)  # (0, 0, width, height)
        client_w, client_h = client_rect[2], client_rect[3]
        if client_w <= 0 or client_h <= 0:
            return None, False, "ウインドウのサイズを取得できません", None

        left, top = win32gui.ClientToScreen(self.hwnd, (0, 0))
        try:
            mon = win32api.GetMonitorInfo(win32api.MonitorFromWindow(self.hwnd))["Monitor"]
        except Exception:
            mon = None
        monitor_sized = mon is not None and covers_monitor(left, top, client_w, client_h, mon)
        if monitor_sized and exclusive_fullscreen_running():
            self._black_since = None
            return None, False, FULLSCREEN_REASON, None

        if not self._sizes.update((client_w, client_h), time.monotonic()):
            # Size just changed: skip quietly (reason None) until it settles.
            return None, False, None, None

        profile = compute_profile(client_w, client_h)
        monitor = {"left": left, "top": top, "width": client_w, "height": client_h}
        try:
            shot = self.sct.grab(monitor)
        except Exception as e:
            return None, False, f"キャプチャに失敗しました: {e}", profile

        frame = np.array(shot)[:, :, :3]  # BGRA -> BGR
        if monitor_sized and is_black(frame):
            now = time.monotonic()
            if self._black_since is None:
                self._black_since = now
            elif now - self._black_since >= FULLSCREEN_BLACK_S:
                return None, False, FULLSCREEN_REASON, None
        else:
            self._black_since = None
        # the game's picture only (black bars cut off: PictureFinder), and the
        # size check on it — the caller must not show recognized numbers for
        # an unsupported size (the profile's reason says why)
        px, py, pw, ph = self._picture.update(frame)
        profile = compute_profile(pw, ph)
        if not profile.ok:
            return None, False, profile.reason, profile
        if (pw, ph) != (client_w, client_h):
            frame = frame[py:py + ph, px:px + pw]
        self.last_picture = (px, py, pw, ph)
        self.last_client_size = (pw, ph)
        self.last_client_origin = (left + px, top + py)
        frame, work_profile = shrink_for_recognition(frame)
        return frame, True, None, work_profile if work_profile.ok else profile
