import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from i18n import capture_message_en
from live_capture import FULLSCREEN_REASON, SizeSettler, covers_monitor


def test_fullscreen_reason_has_an_english_message():
    assert "fullscreen" in capture_message_en(FULLSCREEN_REASON)


def test_covers_monitor_only_when_exactly_the_monitor():
    mon = (0, 0, 2560, 1440)
    assert covers_monitor(0, 0, 2560, 1440, mon)
    assert not covers_monitor(21, 52, 1156, 650, mon)        # windowed
    assert not covers_monitor(-8, -8, 2576, 1456, mon)       # maximized with borders hanging off


def test_covers_monitor_on_a_second_monitor():
    assert covers_monitor(2560, 0, 1920, 1080, (2560, 0, 4480, 1080))


def test_first_size_is_used_at_once():
    s = SizeSettler(settle_s=0.5)
    assert s.update((1156, 650), 0.0)


def test_brief_size_flicker_is_ignored():
    # entering fullscreen / focus changes report 2544 or 2576 for a frame or two
    s = SizeSettler(settle_s=0.5)
    assert s.update((2560, 1440), 0.0)
    assert not s.update((2544, 1440), 0.1)
    assert not s.update((2544, 1440), 0.2)
    assert s.update((2560, 1440), 0.3)
    assert s.accepted == (2560, 1440)


def test_a_real_resize_is_taken_once_it_holds():
    s = SizeSettler(settle_s=0.5)
    s.update((1156, 650), 0.0)
    assert not s.update((2560, 1440), 1.0)
    assert not s.update((2560, 1440), 1.3)
    assert s.update((2560, 1440), 1.5)
    assert s.accepted == (2560, 1440)


def test_settle_timer_restarts_when_the_pending_size_changes():
    s = SizeSettler(settle_s=0.5)
    s.update((1156, 650), 0.0)
    assert not s.update((2544, 1440), 1.0)
    assert not s.update((2560, 1440), 1.4)   # different again: wait from here
    assert not s.update((2560, 1440), 1.8)
    assert s.update((2560, 1440), 1.9)


def test_windowed_fullscreen_is_captured_and_the_real_one_refused(monkeypatch):
    """A borderless window the size of the monitor is read like any window;
    the exclusive fullscreen (Windows says so, or the capture stays black) is
    refused with the fullscreen message."""
    import numpy as np
    import live_capture as lc

    clock = [100.0]
    monkeypatch.setattr(lc.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(lc.win32gui, "IsWindow", lambda h: True)
    monkeypatch.setattr(lc.win32gui, "IsIconic", lambda h: False)
    monkeypatch.setattr(lc.win32gui, "GetClientRect", lambda h: (0, 0, 1920, 1080))
    monkeypatch.setattr(lc.win32gui, "ClientToScreen", lambda h, p: (0, 0))
    monkeypatch.setattr(lc.win32api, "MonitorFromWindow", lambda h: 1)
    monkeypatch.setattr(lc.win32api, "GetMonitorInfo", lambda m: {"Monitor": (0, 0, 1920, 1080)})
    exclusive = [False]
    monkeypatch.setattr(lc, "exclusive_fullscreen_running", lambda: exclusive[0])
    picture = [np.full((1080, 1920, 4), 120, np.uint8)]

    class FakeShot:
        def grab(self, monitor):
            return picture[0]

        def close(self):
            pass

    cap = lc.GameWindowCapture.__new__(lc.GameWindowCapture)
    cap.sct, cap.hwnd, cap._sizes = FakeShot(), 1, lc.SizeSettler()
    cap.last_client_size = cap.last_client_origin = cap._black_since = cap.last_picture = None
    cap._picture = lc.PictureFinder()

    frame, ok, reason, _ = cap.grab()
    assert ok and reason is None and frame is not None          # windowed fullscreen: read

    picture[0] = np.zeros((1080, 1920, 4), np.uint8)             # a black loading screen: still read
    assert cap.grab()[1]
    clock[0] += lc.FULLSCREEN_BLACK_S + 0.1                      # black for seconds: the real fullscreen
    assert cap.grab()[2] == lc.FULLSCREEN_REASON

    picture[0] = np.full((1080, 1920, 4), 120, np.uint8)
    assert cap.grab()[1]                                         # a picture again
    exclusive[0] = True                                          # Windows: exclusive fullscreen
    assert cap.grab()[2] == lc.FULLSCREEN_REASON


def test_black_bars_around_the_picture_are_cut_off():
    """A window a little wider or taller than 16:9: the game keeps its
    picture 16:9 inside black bars. Everything is placed from the picture
    (left in, 2.5% of bars cost the recordings nearly every T-SPIN)."""
    import cv2
    import numpy as np
    import live_capture as lc
    pic = cv2.imread(str(Path(__file__).resolve().parent / "fixtures" / "play_sky_stage.jpg"))
    h, w = pic.shape[:2]
    assert lc.find_picture(pic) == (0, 0, w, h)                              # no bars: the whole frame
    side = cv2.copyMakeBorder(pic, 0, 0, 17, 17, cv2.BORDER_CONSTANT, value=0)
    assert lc.find_picture(side) == (17, 0, w, h)                            # pillarbox, to the pixel
    top = cv2.copyMakeBorder(pic, 9, 9, 0, 0, cv2.BORDER_CONSTANT, value=0)
    assert lc.find_picture(top) == (0, 9, w, h)                              # letterbox
    one_side = cv2.copyMakeBorder(pic, 0, 0, 30, 0, cv2.BORDER_CONSTANT, value=0)
    assert lc.find_picture(one_side) == (0, 0, w + 30, h)                    # not centered: not bars
    assert lc.find_picture(np.zeros_like(pic)) is None                       # all black: can't tell
    finder = lc.PictureFinder()
    got = [finder.update(side) for _ in range(lc.BAR_SAME_READS)]
    assert got[0] == (0, 0, w + 34, h) and got[-1] == (17, 0, w, h)           # used once it's steady
    assert finder.update(np.zeros_like(side)) == (17, 0, w, h)               # a black frame keeps it
