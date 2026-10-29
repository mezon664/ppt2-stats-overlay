import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import pytest
from attack_calc import load_table, compute_attack, AttackStreakTracker, is_b2b_eligible

TABLE = load_table()


# --- base power, no BtB (streak<2), no REN (ren_count=1 -> +0), not perfect clear ---
@pytest.mark.parametrize("clear_type,expected", [
    ("clear_1", 0),
    ("clear_2", 1),
    ("clear_3", 2),
    ("clear_4", 4),
    ("tspin_mini", 0),
    ("tspin_single", 2),
    ("tspin_double", 4),
    ("tspin_triple", 6),
])
def test_base_power_only(clear_type, expected):
    r = compute_attack(TABLE, clear_type, ren_count=1, b2b_streak=1)
    assert r["base"] == expected
    assert r["btb"] == 0
    assert r["ren"] == 0
    assert r["total"] == expected


# --- REN bonus table (ぷよぷよテトリス2 column), independent of base/btb ---
@pytest.mark.parametrize("ren_count,expected_bonus", [
    (1, 0), (2, 1), (3, 1), (4, 2), (5, 2), (6, 3), (7, 3),
    (8, 4), (9, 4), (10, 4), (11, 4), (12, 4), (13, 5), (20, 5),
])
def test_ren_bonus_table(ren_count, expected_bonus):
    r = compute_attack(TABLE, "clear_1", ren_count=ren_count, b2b_streak=1)
    assert r["ren"] == expected_bonus
    assert r["total"] == 0 + expected_bonus  # clear_1 base is 0


# --- Back-to-Back: only applies to eligible clears, only from the 2nd consecutive one ---
def test_btb_does_not_apply_on_first_eligible_clear():
    r = compute_attack(TABLE, "clear_4", ren_count=1, b2b_streak=1)
    assert r["btb"] == 0
    assert r["total"] == 4


def test_btb_applies_from_second_consecutive_eligible_clear():
    r = compute_attack(TABLE, "clear_4", ren_count=1, b2b_streak=2)
    assert r["btb"] == 1
    assert r["total"] == 5


def test_btb_does_not_apply_to_ineligible_clear_even_with_high_streak():
    # clear_2 (2-line) is not a BtB-eligible clear type, regardless of streak count
    r = compute_attack(TABLE, "clear_2", ren_count=1, b2b_streak=9)
    assert r["btb"] == 0
    assert r["total"] == 1


def test_tspin_mini_is_btb_eligible_even_though_base_is_zero():
    assert is_b2b_eligible(TABLE, "tspin_mini") is True
    r = compute_attack(TABLE, "tspin_mini", ren_count=1, b2b_streak=2)
    assert r["base"] == 0
    assert r["btb"] == 1
    assert r["total"] == 1


# --- The exact worked example given on the source page:
# "5Ren目にBtB付きの4ライン消しを行った場合は4+1+2で7段" ---
def test_source_worked_example_5ren_btb_tetris():
    r = compute_attack(TABLE, "clear_4", ren_count=5, b2b_streak=2)
    assert r["base"] == 4
    assert r["btb"] == 1
    assert r["ren"] == 2
    assert r["total"] == 7


# --- Perfect Clear overrides everything (not additive), per source: "10段固定" ---
def test_perfect_clear_alone():
    r = compute_attack(TABLE, "clear_1", ren_count=1, b2b_streak=1, perfect_clear=True)
    assert r["total"] == 10
    assert r["base"] == 0 and r["btb"] == 0 and r["ren"] == 0


def test_perfect_clear_overrides_even_with_high_ren_and_btb():
    # without the override this would be 4 (tetris) + 1 (btb) + 5 (13+ ren) = 10 anyway,
    # so use a combo that would NOT coincidentally equal 10 to prove it's an override.
    r = compute_attack(TABLE, "clear_4", ren_count=5, b2b_streak=2, perfect_clear=True)
    assert r["total"] == 10
    assert r["base"] == 0 and r["btb"] == 0 and r["ren"] == 0


def test_perfect_clear_with_tspin_triple_and_max_ren_still_ten():
    r = compute_attack(TABLE, "tspin_triple", ren_count=20, b2b_streak=5, perfect_clear=True)
    assert r["total"] == 10


# --- No double counting: each component computed once, summed once ---
def test_components_sum_without_double_counting():
    r = compute_attack(TABLE, "clear_4", ren_count=5, b2b_streak=2)
    assert r["base"] + r["btb"] + r["ren"] == r["total"]
    assert r["perfect_clear"] == 0


# --- AttackStreakTracker: REN/BtB streak bookkeeping across a sequence of events ---
def test_tracker_builds_ren_and_btb_streaks():
    t = AttackStreakTracker()
    # REN uses the game's numbering: first clear REN 0, second in a row "1 REN"
    assert t.register_clear(TABLE, "clear_4") == (0, 1)   # 1st tetris: REN 0, b2b streak=1
    assert t.register_clear(TABLE, "clear_4") == (1, 2)   # 2nd tetris in a row: 1REN, b2b streak=2
    assert t.register_clear(TABLE, "clear_2") == (2, 0)   # non-eligible clear resets b2b streak
    assert t.ren_count == 2                                 # but REN (combo) keeps going


def test_no_clear_placement_breaks_ren_but_keeps_btb():
    t = AttackStreakTracker()
    t.register_clear(TABLE, "clear_4")
    t.register_clear(TABLE, "clear_4")
    assert t.ren_count == 1 and t.b2b_streak == 2
    t.register_clear(TABLE, None)  # a piece locked with no line clear
    assert t.ren_count == 0 and t.consecutive_clears == 0
    assert t.b2b_streak == 2       # BtB is only broken by a plain 1-3 line clear
    assert t.register_clear(TABLE, "clear_4") == (0, 3)
