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
