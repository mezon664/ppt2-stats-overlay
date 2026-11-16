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


def print_window(hwnd, width, height):
    """The game window's own client area (PrintWindow), whatever lies over it
    on the screen, or None. Slower than reading the screen (~30 ms), so only
    used when a window of ours over the game can't be kept out of screen
    captures (GameWindowCapture.window_only)."""
    import ctypes
    import win32ui
    hdc = dc = mem = bmp = None
    try:
        hdc = win32gui.GetWindowDC(hwnd)
        dc = win32ui.CreateDCFromHandle(hdc)
        mem = dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(dc, width, height)
        mem.SelectObject(bmp)
        # PW_CLIENTONLY | PW_RENDERFULLCONTENT (what a DirectX game draws, too)
        if not ctypes.windll.user32.PrintWindow(hwnd, mem.GetSafeHdc(), 1 | 2):
            return None
        bits = np.frombuffer(bmp.GetBitmapBits(True), np.uint8)
        return bits.reshape(height, width, 4)[:, :, :3].copy()
    except Exception:
        return None
    finally:
        try:
            if bmp is not None:
                win32gui.DeleteObject(bmp.GetHandle())
            if mem is not None:
                mem.DeleteDC()
            if dc is not None:
                dc.DeleteDC()
            if hdc is not None:
                win32gui.ReleaseDC(hwnd, hdc)
        except Exception:
            pass


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
        # read the game's own window instead of the screen (set by the server
        # when a window of ours over the game isn't kept out of captures)
        self.window_only = False
        self.window_unusable = False   # its own window came out black: the screen it is
        self.last_method = "screen"
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
        self.last_method = "screen"
        if self.window_only and not self.window_unusable:
            own = print_window(self.hwnd, client_w, client_h)
            if own is not None and not is_black(own):
                frame, self.last_method = own, "window"
            elif not is_black(frame):
                self.window_unusable = True   # PrintWindow gives nothing for this game here
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


# ---------------------------------------------------------------------------
# A game on another machine (Switch, PS, ...) through a capture board: read
# as a camera — OBS's virtual camera showing the capture board's source (OBS
# keeps the board to itself), or the board itself when nothing else uses it.
# Only the picture is read, as with the PC game's window (user's request: a
# Switch on a capture board into OBS said "game window not found").
# ---------------------------------------------------------------------------
CAMERA_W, CAMERA_H = 1920, 1080   # asked for (a camera gives what it has)
CAMERA_STALE_S = 2.0               # no new picture for this long: say so
CAMERA_MAX = 10                    # camera numbers 0..9 (settings)
CAMERA_RETRY_S = 2.0               # a camera that wouldn't open is tried again this often
CAMERA_OPEN_REASON = "カメラを開けません"        # (+ its number)
CAMERA_STALE_REASON = "カメラの映像が届いていません (OBS の仮想カメラを開始していますか？)"
CAMERA_BLACK_REASON = "カメラの映像が真っ黒です (仮想カメラの出力にキャプチャーボードのソースを選んでいますか？)"
# a picture this dark all over (few pixels brighter than DARK_LEVEL) counts as
# black too: a virtual camera with nothing on it isn't exactly 0 (compression
# noise) — a user's showed as a dark "read" picture instead of saying why
DARK_LEVEL, DARK_SHARE = 40, 0.005
# only once it's stayed dark this long: the game goes black for a moment
# between scenes (5 of 1325 frames of the recordings), and those frames are
# read as they are, as from the PC game's window
DARK_HOLD_S = 3.0


def is_dark(frame):
    """Almost every sampled pixel dark (see DARK_LEVEL)."""
    small = frame[::8, ::8]
    return float((small.max(axis=2) > DARK_LEVEL).mean()) < DARK_SHARE


class CameraCapture:
    """The game's picture from a camera device (DirectShow: OBS's virtual
    camera is one). A thread keeps only the newest picture, so what's read is
    now, not a queue of old ones (a camera sends 30-60 a second, this reads
    15). Same results as GameWindowCapture.grab; no window (hwnd None: nothing
    of this app's can be over it, and the HUD has no game window to sit on)."""

    def __init__(self, index=0, open_device=None):
        import threading
        self.index = int(index)
        self.hwnd = None
        self.window_only = False
        self.last_method = "camera"
        self.last_picture = None
        self.last_client_size = None
        self.last_client_origin = None
        self._picture = PictureFinder()
        self._sizes = SizeSettler()
        self._open = open_device or self._open_dshow
        self._dev = None
        self._latest, self._latest_t = None, None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._failed_t = -CAMERA_RETRY_S   # when opening it last failed
        self._opened_t = 0.0
        self._dark_since = None   # dark (black) since then (DARK_HOLD_S)
        # the "game session" (today's results since it began): no game process
        # here to ask when it started — the first picture read counts
        self.started_at = None

    @staticmethod
    def _open_dshow(index):
        dev = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if dev.isOpened():
            dev.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_W)
            dev.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_H)
        return dev

    def _start(self):
        import threading
        self._dev = self._open(self.index)
        if self._dev is None or not self._dev.isOpened():
            self._dev = None
            return False
        self._opened_t = time.monotonic()
        self._thread = threading.Thread(target=self._run, name="camera", daemon=True)
        self._thread.start()
        return True

    def _run(self):
        while not self._stop.is_set():
            ok, frame = self._dev.read()
            if not ok or frame is None:
                if self._stop.wait(0.05):
                    break
                continue
            with self._lock:
                self._latest, self._latest_t = frame, time.monotonic()

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            if self._thread.is_alive():   # (stuck in a read: letting go of the device under it could crash)
                self._dev = None
                return
        if self._dev is not None:
            try:
                self._dev.release()
            except Exception:
                pass
        self._dev = None

    def grab(self):
        if self._dev is None:
            # (tried again now and then, not every frame: opening a device takes a while)
            if time.monotonic() - self._failed_t < CAMERA_RETRY_S or not self._start():
                if time.monotonic() - self._failed_t >= CAMERA_RETRY_S:
                    self._failed_t = time.monotonic()
                return None, False, f"{CAMERA_OPEN_REASON} (カメラ {self.index + 1})", None
        with self._lock:
            frame, t = self._latest, self._latest_t
        if frame is None:
            if self._thread is not None and not self._thread.is_alive():
                return None, False, f"{CAMERA_OPEN_REASON} (カメラ {self.index + 1})", None
            if time.monotonic() - self._opened_t > CAMERA_STALE_S:   # (opened, but nothing comes)
                return None, False, CAMERA_STALE_REASON, None
            return None, False, None, None          # (just opened: the first picture's coming)
        if time.monotonic() - t > CAMERA_STALE_S:
            return None, False, CAMERA_STALE_REASON, None
        if frame.ndim == 3 and frame.shape[2] == 4:
            frame = frame[:, :, :3]
        if is_black(frame) or is_dark(frame):
            if self._dark_since is None:
                self._dark_since = time.monotonic()
            elif time.monotonic() - self._dark_since >= DARK_HOLD_S:
                return None, False, CAMERA_BLACK_REASON, None
        else:
            self._dark_since = None
        h, w = frame.shape[:2]
        if not self._sizes.update((w, h), time.monotonic()):
            return None, False, None, None
        px, py, pw, ph = self._picture.update(frame)
        profile = compute_profile(pw, ph)
        if not profile.ok:
            return None, False, profile.reason, profile
        if (pw, ph) != (w, h):
            frame = frame[py:py + ph, px:px + pw]
        self.last_picture = (px, py, pw, ph)
        self.last_client_size = (pw, ph)
        if self.started_at is None:
            self.started_at = time.time()
        frame, work_profile = shrink_for_recognition(frame)
        return frame, True, None, work_profile if work_profile.ok else profile


def make_capture(display):
    """The capture for the settings: the PC game's window, or a camera
    (display.capture_source "camera", display.capture_camera its number)."""
    if (display or {}).get("capture_source") == "camera":
        return CameraCapture(int((display or {}).get("capture_camera") or 0))
    return GameWindowCapture()


OBS_CAMERA = "OBS Virtual Camera"


def camera_names():
    """The cameras' names, in the order of their numbers (DirectShow's video
    input devices, the same list OpenCV opens by number): a user found
    several cameras among 1-10 and only one was OBS's — by number alone it
    took trying them all. [] if they can't be listed."""
    try:
        import ctypes
        from ctypes import POINTER, byref, c_void_p, wintypes
        import pythoncom

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                        ("Data4", ctypes.c_ubyte * 8)]

        def guid(text):
            g = GUID()
            ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p(text), byref(g))
            return g

        pythoncom.CoInitialize()
        dev_enum = c_void_p()
        ctypes.oledll.ole32.CoCreateInstance(byref(guid("{62BE5D10-60EB-11d0-BD3B-00A0C911CE86}")), None, 1,
                                             byref(guid("{29840822-5B84-11D0-BD3B-00A0C911CE86}")), byref(dev_enum))
        vtbl = ctypes.cast(ctypes.cast(dev_enum, POINTER(c_void_p))[0], POINTER(c_void_p))
        release = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)(vtbl[2])
        create = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, POINTER(GUID), POINTER(c_void_p), wintypes.DWORD)(vtbl[3])
        found = c_void_p()
        try:
            # (S_FALSE and no enumerator: there are no cameras)
            create(dev_enum, byref(guid("{860BB310-5D01-11d0-BD3B-00A0C911CE86}")), byref(found), 0)
        finally:
            release(dev_enum)
        if not found.value:
            return []
        monikers = pythoncom.ObjectFromAddress(found.value, pythoncom.IID_IEnumMoniker)
        ctx = pythoncom.CreateBindCtx(0)
        names = []
        while True:
            got = monikers.Next(1)
            if not got:
                break
            try:
                bag = got[0].BindToStorage(ctx, None, pythoncom.IID_IPropertyBag)
                names.append(str(bag.Read("FriendlyName", pythoncom.VT_BSTR)))
            except Exception:
                names.append("")
        return names[:CAMERA_MAX]
    except Exception:
        return []
