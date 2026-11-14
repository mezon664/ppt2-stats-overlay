"""T-SPIN Mini Double (T-SPIN NEO): "Double" under the Mini badge, 2 lines,
1 line sent (+1 with BtB: the user saw 2 with BtB)."""
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import attack_calc
import banner_detect
import live_pipeline


def test_the_double_under_mini_is_told_from_single():
    # the banner area of the user's recording (tsmd_20261114_024420.mp4, t=185.75, 1P), from y 380 / x 0
    crop = cv2.imread(str(ROOT / "tests" / "fixtures" / "tspin_mini_double_left.png"))
    tm = {k: cv2.imread(str(ROOT / "scripts" / banner_detect.TEMPLATES[k]["file"]))
          for k in ("tspin_mini", "tspin_mini_single", "tspin_mini_double")}
    score = {k: float(cv2.matchTemplate(crop, t, cv2.TM_CCOEFF_NORMED).max()) for k, t in tm.items()}
    assert score["tspin_mini"] > 0.7
    assert score["tspin_mini_double"] >= banner_detect.MINI_DOUBLE_THRESHOLD
    assert score["tspin_mini_double"] > score["tspin_mini_single"]


def test_mini_double_attack():
    table = attack_calc.load_table()
    assert attack_calc.base_power(table, "tspin_mini_double") == 1
    assert "tspin_mini_double" in table["back_to_back"]["eligible_clears"]
    assert live_pipeline.BANNER_LINES["tspin_mini_double"] == 2
    assert live_pipeline.CLEAR_TYPE_LABEL_JA["tspin_mini_double"] == "T-SPIN Mini Double"
