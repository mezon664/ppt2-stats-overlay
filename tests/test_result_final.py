"""A match won by its last clear (a REN that finished the opponent) is kept
with that clear counted: max REN one short before (user's report)."""
import glob
import os
import re
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hud"))
import live_pipeline as lp  # noqa: E402
from image_io import read_image  # noqa: E402

FRAMES = sorted(glob.glob(str(ROOT / "debug_frames" / "burst_ren" / "*.jpg")) +
                glob.glob(str(ROOT / "debug_frames" / "burst_ren" / "*.png")))
WIN, LAST_CLEAR = 19.53, 17.92     # the victory banner's first frame; the 12th REN's flash


@pytest.mark.skipif(not FRAMES, reason="recording not here")
def test_the_clear_that_won_it_is_in_the_result():
    """burst_ren with its end brought forward: the opponent goes down 0.3 s
    after the 12th REN (frames between left out, the rest moved up)."""
    shift = WIN - (LAST_CLEAR + 0.3)
    pipe = lp.MatchPipeline()
    final = None
    for f in FRAMES:
        t = float(re.search(r"_t(\d+\.\d+)", f).group(1))
        if LAST_CLEAR + 0.1 < t < WIN:
            continue
        pipe.process_frame(read_image(f), t - shift if t >= WIN else t)
        s = pipe.snapshot()
        if s["frozen"] and s["match_elapsed_s"] > 5:
            if not s["result_final"]:
                assert final is None        # (not complete yet: nothing kept)
                continue
            final = final or s
    assert final is not None
    assert final["left"]["match_stats"]["max_ren"] == 12 and final["left"]["attack"] == 32


def test_the_hud_keeps_a_match_once_its_result_is_complete(monkeypatch):
    import overlay
    kept = []
    monkeypatch.setattr(overlay.opener_stats, "match_record", lambda st: dict(st))
    monkeypatch.setattr(overlay.opener_stats, "add", lambda r: kept.append(r) or True)

    class Hud:
        preview = False
        _was_frozen = None

        class opener_recorded:
            @staticmethod
            def emit():
                pass
    hud = Hud()
    keep = overlay.HudWindow._record_finished_match
    keep(hud, {"frozen": False})
    keep(hud, {"frozen": True, "result_final": False, "n": 1})
    assert kept == []
    keep(hud, {"frozen": True, "result_final": True, "n": 2})
    keep(hud, {"frozen": True, "result_final": True, "n": 3})
    assert [k["n"] for k in kept] == [2]          # once, with the result complete
    keep(hud, {"frozen": True, "result_final": True, "n": 4})
    assert len(kept) == 1
