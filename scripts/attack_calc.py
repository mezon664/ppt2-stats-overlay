"""Attack-power (karyoku) calculation for APM, driven entirely by config/attack_table.json.

No numbers are hardcoded here — this module only implements the *composition rule*
(base + BtB + REN, independently, with Perfect Clear overriding everything). See
config/attack_table.json for the actual values and their source/assumptions.
"""
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "attack_table.json"

CLEAR_TYPES = (
    "clear_1", "clear_2", "clear_3", "clear_4",
    "tspin_mini", "tspin_mini_double", "tspin_single", "tspin_double", "tspin_triple",
)


def load_table(path=CONFIG_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def base_power(table, clear_type):
    if clear_type.startswith("clear_"):
        n = clear_type.split("_", 1)[1]
        return table["base_clear"][n]
    if clear_type.startswith("tspin_"):
        kind = clear_type.split("_", 1)[1]
        return table["tspin"][kind]
    raise ValueError(f"unknown clear_type: {clear_type}")


def ren_bonus(table, ren_count):
    rb = table["ren_bonus"]
    key = str(ren_count)
    if key in rb["table"]:
        return rb["table"][key]
    return rb["default_beyond_table"]


def is_b2b_eligible(table, clear_type):
    return clear_type in table["back_to_back"]["eligible_clears"]


class AttackStreakTracker:
    """Tracks REN (combo) count and Back-to-Back streak across events for one player.

    This only tracks state *derived from recognized clear events* (banners / REN
    counter OCR) — it has no knowledge of the board itself. If an event is missed
    entirely (not recognized), the streak state silently desyncs from the real
    game; this is a known limitation until event recognition accuracy is validated
    (see phase2 test notes).
    """

    def __init__(self):
        self.consecutive_clears = 0
        self.b2b_streak = 0

    @property
    def ren_count(self):
        """The game's own REN number, which is what the attack table is keyed
        by: the first clear is REN 0 and the second consecutive clear is "1
        REN" (confirmed on screen: the 6th clear in a row shows "5 REN").
        Counting clears instead put every REN one too high, both in the log
        and in the bonus looked up for it."""
        return max(0, self.consecutive_clears - 1)

    def register_clear(self, table, clear_type):
        """clear_type=None means a piece locked with no line clear: that breaks
        REN only. Back-to-Back survives non-clearing placements (guideline
        rule — only a non-eligible 1-3 line clear ends it), so a T-Spin Double,
        a few plain placements, then another T-Spin Double still gets BtB."""
        if clear_type is None:
            self.consecutive_clears = 0
            return None

        self.consecutive_clears += 1
        if is_b2b_eligible(table, clear_type):
            self.b2b_streak += 1
        else:
            self.b2b_streak = 0

        return self.ren_count, self.b2b_streak


def compute_attack(table, clear_type, ren_count, b2b_streak, perfect_clear=False):
    """Returns a breakdown dict. `total` is what should be counted toward APM.

    - perfect_clear=True overrides everything (per source: "10段固定").
    - base/btb/ren are each computed independently and summed (per source's own
      worked example: 4-line + BtB + 5REN = 4+1+2 = 7).
    """
    if perfect_clear:
        pc = table["perfect_clear"]
        return {
            "mode": pc["mode"],
            "base": 0, "btb": 0, "ren": 0,
            "perfect_clear": pc["value"],
            "total": pc["value"],
        }

    base = base_power(table, clear_type)
    b2b_eligible = is_b2b_eligible(table, clear_type)
    min_streak = table["back_to_back"]["min_consecutive_for_bonus"]
    btb = table["back_to_back"]["bonus"] if (b2b_eligible and b2b_streak >= min_streak) else 0
    ren = ren_bonus(table, ren_count) if ren_count >= 1 else 0

    return {
        "mode": "normal",
        "base": base, "btb": btb, "ren": ren,
        "perfect_clear": 0,
        "total": base + btb + ren,
    }
