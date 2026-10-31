import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from live_pipeline import format_event_log_entry, EVENT_LOG_MAX, PlayerPipeline
from banner_detect import load_templates


def test_plain_tetris_entry():
    ev = {"clear_type": "clear_4", "btb": False, "ren_count": 0, "ren_source": "estimated"}
    entry = format_event_log_entry(12.34, ev, 4)
    assert entry["label"] == "TETRIS"
    assert entry["text"] == "TETRIS +4段"
    assert entry["t"] == 12.34


def test_tspin_double_with_btb_and_ren():
    ev = {"clear_type": "tspin_double", "btb": True, "ren_count": 3, "ren_source": "screen"}
    entry = format_event_log_entry(5.0, ev, 7)
    assert entry["text"] == "T-SPIN Double +7段 BtB 3REN"


def test_lone_clear_shows_no_ren():
    # game numbering: a lone (non-chained) clear is REN 0
    ev = {"clear_type": "tspin_single", "btb": False, "ren_count": 0, "ren_source": "estimated"}
    entry = format_event_log_entry(0.0, ev, 2)
    assert "REN" not in entry["text"]
    assert entry["text"] == "T-SPIN Single +2段"


def test_second_consecutive_clear_shows_1ren_like_the_game():
    ev = {"clear_type": "clear_1", "btb": False, "ren_count": 1, "ren_source": "estimated"}
    assert format_event_log_entry(0.0, ev, 0)["text"] == "1ライン +0段 1REN"


def test_unknown_clear_type_falls_back_to_raw_string():
    ev = {"clear_type": "something_new", "btb": False, "ren_count": 1, "ren_source": "estimated"}
    entry = format_event_log_entry(0.0, ev, 0)
    assert entry["label"] == "something_new"


def test_event_log_builds_up_newest_first_and_is_capped():
    templates = load_templates()
    pp = PlayerPipeline(side="left", templates=templates)
    for i in range(EVENT_LOG_MAX + 5):
        ev = {"clear_type": "clear_4", "btb": False, "ren_count": 1, "ren_source": "estimated"}
        pp.event_log.insert(0, format_event_log_entry(float(i), ev, 4))
        del pp.event_log[EVENT_LOG_MAX:]
    assert len(pp.event_log) == EVENT_LOG_MAX
    assert pp.event_log[0]["t"] == float(EVENT_LOG_MAX + 4)  # newest first


def test_english_text_is_built_alongside_japanese():
    from live_pipeline import format_event_log_entry, format_ren_break_entry
    ev = {"clear_type": "tspin_double", "btb": True, "ren_count": 2, "ren_source": "estimated"}
    e = format_event_log_entry(10.0, ev, 6)
    assert e["text"] == "T-SPIN Double +6段 BtB 2REN"
    assert e["text_en"] == "T-SPIN Double +6 BtB 2 Combo"   # the English game says "Combo"
    e = format_event_log_entry(10.0, {"clear_type": "clear_2", "btb": False, "ren_count": 0,
                                      "ren_source": "flash_confirmed"}, 1)
    assert e["text_en"] == "Double +1"
    pc = format_event_log_entry(10.0, {**ev, "clear_type": "clear_4", "perfect_clear": True}, 10)
    assert pc["text_en"] == "PERFECT CLEAR (TETRIS) +10"
    assert format_ren_break_entry(5.0)["text_en"] == "Combo ended (no clear)"


def test_capture_messages_have_english():
    from i18n import capture_message_en
    assert capture_message_en("ゲームが最小化されています (認識にはウインドウ表示が必要です)").startswith("The game is minimized")
    assert capture_message_en("something new") == "something new"
