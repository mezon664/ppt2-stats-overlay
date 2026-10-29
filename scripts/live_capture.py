"""Finds the running PuyoPuyoTetris2 window and captures it with mss.

Honors the Phase-1 finding: a minimized window's reported rect is garbage
(-32000,-32000), and GDI/mss-style capture cannot read a minimized or fully
occluded window at all. Rather than silently showing stale or wrong numbers, this
reports a clear "capture unavailable" reason so the HUD/OBS layers can say so
instead of guessing.
"""
import mss
import win32gui
import win32process
import psutil

from capture_profile import compute_profile

PROCESS_NAME = "PuyoPuyoTetris2.exe"


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

        left_top = win32gui.ClientToScreen(self.hwnd, (0, 0))
        profile = compute_profile(client_w, client_h)
        if not profile.ok:
            # Don't even capture: the caller must not show recognized numbers for
            # an unsupported size, per spec — surfacing the profile's reason here
            # makes that the caller's responsibility to honor, not guess around.
            return None, False, profile.reason, profile

        monitor = {"left": left_top[0], "top": left_top[1], "width": client_w, "height": client_h}
        try:
            shot = self.sct.grab(monitor)
        except Exception as e:
            return None, False, f"キャプチャに失敗しました: {e}", profile

        import numpy as np
        frame = np.array(shot)[:, :, :3]  # BGRA -> BGR
        return frame, True, None, profile
