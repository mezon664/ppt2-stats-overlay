"""APP (attack per piece) and the per-match totals behind the summary."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from banner_detect import load_templates
from live_pipeline import PlayerPipeline


def player():
    return PlayerPipeline(side="left", templates=load_templates())


def emit(p, t, clear_type, lines, ren=0, btb=False):
    ev = {"clear_type": clear_type, "btb": btb, "ren_count": ren, "ren_source": "flash_confirmed"}
    p._emit_attack_event(t, ev, lines, {"base": lines, "btb": 0, "ren": 0, "total": lines})


def test_app_is_lines_sent_per_piece():
    p = player()
    assert p.snapshot(10.0, 10.0)["app"] is None          # no pieces yet
    emit(p, 1.0, "clear_4", 4)
    emit(p, 2.0, "tspin_double", 4)
    p.queue_tracker.pieces_placed = 16
    snap = p.snapshot(10.0, 10.0)
    assert snap["app"] == 0.5                                # 8 lines / 16 pieces


def test_match_stats_count_the_summary_rows():
    p = player()
    emit(p, 1.0, "clear_4", 4)
    emit(p, 2.0, "tspin_double", 5, ren=1, btb=True)
    emit(p, 3.0, "clear_1", 0, ren=2)
    emit(p, 4.0, "tspin_triple", 6)
    p.queue_tracker.pieces_placed = 30
    stats = p.snapshot(10.0, 10.0)["match_stats"]
    assert stats == {"lines_sent": 15, "pieces": 30, "max_ren": 2, "tetris": 1,
                     "tspin": 2, "perfect_clear": 0,
                     # each kind on its own too (the summary can show them separately)
                     "tspin_single": 0, "tspin_double": 1, "tspin_triple": 1, "tspin_mini": 0}


def test_perfect_clear_counts_in_the_summary():
    p = player()
    emit(p, 5.0, "clear_4", 5)
    p._on_pc_edge(5.3)
    stats = p.snapshot(10.0, 10.0)["match_stats"]
    assert stats["perfect_clear"] == 1 and stats["lines_sent"] == 10 and stats["tetris"] == 1
