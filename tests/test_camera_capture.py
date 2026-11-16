"""A game on a capture board (Switch etc.), read through a camera — OBS's
virtual camera (scripts/live_capture.CameraCapture)."""
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import live_capture
from config_store import display_settings
from i18n import capture_message_en


class Device:
    def __init__(self, frame=None, opened=True):
        self.frame, self.opened, self.released = frame, opened, False

    def isOpened(self):
        return self.opened

    def read(self):
        time.sleep(0.005)
        return (self.frame is not None), self.frame

    def release(self):
        self.released = True


def picture(w=1920, h=1080, bars=0):
    """A 16:9 game-like picture (not black), with black bars left and right if asked."""
    f = np.zeros((h, w + 2 * bars, 3), np.uint8)
    rng = np.random.default_rng(1)
    f[:, bars:bars + w] = rng.integers(40, 220, (h, w, 3), dtype=np.uint8)
    return f


def grab_until(cam, ok_wanted=True, tries=200):
    out = None
    for _ in range(tries):
        out = cam.grab()
        if (ok_wanted and out[1]) or (not ok_wanted and out[2]):
            return out
        time.sleep(0.01)
    return out


def test_a_camera_picture_is_read_like_the_game_window():
    dev = Device(picture())
    cam = live_capture.CameraCapture(1, open_device=lambda i: dev)
    cam._sizes = live_capture.SizeSettler(0.0)
    frame, ok, reason, profile = grab_until(cam)
    assert ok and reason is None
    assert frame.shape[1] == live_capture.WORK_W and profile.ok      # (shrunk for recognition, as the window)
    assert cam.hwnd is None                                          # (no window: nothing of ours over it)
    cam.close()
    assert dev.released


def test_black_bars_round_it_are_cut_off():
    dev = Device(picture(1440, 810, bars=240))   # (a 16:9 picture in a wider one)
    cam = live_capture.CameraCapture(0, open_device=lambda i: dev)
    cam._sizes = live_capture.SizeSettler(0.0)
    for _ in range(live_capture.BAR_SAME_READS + 2):
        frame, ok, reason, profile = grab_until(cam)
    assert ok and cam.last_picture[0] == 240 and cam.last_picture[2] == 1440
    cam.close()


def test_what_goes_wrong_is_said():
    cam = live_capture.CameraCapture(7, open_device=lambda i: Device(opened=False))
    assert cam.grab()[2].startswith(live_capture.CAMERA_OPEN_REASON)
    black = live_capture.CameraCapture(0, open_device=lambda i: Device(np.zeros((1080, 1920, 3), np.uint8)))
    assert grab_until(black, ok_wanted=False)[2] == live_capture.CAMERA_BLACK_REASON
    black.close()
    silent = live_capture.CameraCapture(0, open_device=lambda i: Device(None))
    real = live_capture.CAMERA_STALE_S
    live_capture.CAMERA_STALE_S = 0.05
    try:
        assert grab_until(silent, ok_wanted=False)[2] == live_capture.CAMERA_STALE_REASON
    finally:
        live_capture.CAMERA_STALE_S = real
        silent.close()
    for reason in (live_capture.CAMERA_OPEN_REASON + " (カメラ 8)", live_capture.CAMERA_STALE_REASON,
                   live_capture.CAMERA_BLACK_REASON):
        assert capture_message_en(reason) != reason      # (in English too)


def test_the_setting_picks_the_capture():
    d = display_settings({"display": {}})
    assert d["capture_source"] == "game" and d["capture_camera"] == 0
    assert display_settings({"display": {"capture_source": "x", "capture_camera": 42}})["capture_camera"] == 9
    assert isinstance(live_capture.make_capture({"capture_source": "camera", "capture_camera": 3}),
                      live_capture.CameraCapture)
    assert live_capture.make_capture({"capture_source": "camera", "capture_camera": 3}).index == 3


def test_the_camera_numbers_match_the_settings_and_a_session_starts():
    """The reason names the camera as the settings do (index 0 is "カメラ 1"),
    and the first picture read starts the game session (today's results)."""
    cam = live_capture.CameraCapture(2, open_device=lambda i: Device(opened=False))
    assert "カメラ 3" in cam.grab()[2]
    dev = Device(picture())
    cam = live_capture.CameraCapture(0, open_device=lambda i: dev)
    cam._sizes = live_capture.SizeSettler(0.0)
    assert cam.started_at is None
    grab_until(cam)
    assert cam.started_at is not None
    import data_server
    data_server.SESSION["camera_since"] = None
    assert data_server.game_started_at(cam) == cam.started_at
    cam.close()
