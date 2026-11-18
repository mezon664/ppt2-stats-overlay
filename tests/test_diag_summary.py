import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import diag_summary


def _log(lines):
    return [f"2026-11-18 23:{50 + i // 60:02d}:{i % 60:02d},000 INFO {msg}" for i, msg in enumerate(lines)]


MATCH = [
    "reading the game from camera 2",
    "[left] player name read: めぞん",
    "resetting match state (GO! disappeared — new match started) clock_start_t=1.0",
    "[left] t=2.00 clear_4 lines=4 (base=4 btb=0 ren=0) ren_source=flash_tetris",
    "[left] t=3.00 clear_4 banner ignored (no matching clear flash before it)",
    "[left] t=4.00 clear_4 banner ignored (no matching clear flash before it)",
    "[right] t=5.00 tspin_double lines=4 (base=4 btb=0 ren=0) ren_source=estimated",
    "[debug tspin peak left] {'tspin_single': (0.31, (1, 2)), 'tspin_double': (0.42, (1, 2))}",
    "[debug tspin peak left] {'tspin_single': (0.25, (1, 2)), 'tspin_double': (0.61, (1, 2))}",
    "[left] flash at t=6.0 dismissed (measured 0 lit rows, not a real clear)",
    "match concluded (victory banner) — freezing numbers",
    "[left] t=9.00 clear_4 lines=4 (base=4 btb=0 ren=0) ren_source=flash_tetris",   # after the end
    "screen went black — clearing the numbers and the summary",
]


def test_a_match_is_counted_per_side():
    (m,) = diag_summary.matches(_log(MATCH))
    left, right = m.sides["left"], m.sides["right"]
    assert m.source == "camera2" and m.end == "victory banner"
    assert left.kinds == {"clear_4": 1} and left.lines == 4
    assert left.ignored == {"clear_4": 2} and left.dismissed == 1
    assert left.peak == {"tspin_single": 0.31, "tspin_double": 0.61}
    assert right.kinds == {"tspin_double": 1}


def test_summary_is_short_newest_first_and_has_no_names(tmp_path):
    lines = []
    for _ in range(8):
        lines += MATCH
    (tmp_path / "server.log").write_text("\n".join(_log(lines)) + "\n", encoding="utf-8")
    text = diag_summary.summary(tmp_path, "9.9.9")
    assert text.startswith("PPTetrics 9.9.9")
    assert text.count("\n#") == diag_summary.MAX_MATCHES
    assert "めぞん" not in text
    assert "let go 4x2" in text and len(text) < diag_summary.MAX_CHARS


def test_older_parts_are_read_first(tmp_path):
    old = _log(["resetting match state (old one) x",
                "[left] t=1.00 clear_1 lines=0 (base=0 btb=0 ren=0) ren_source=flash_confirmed"])
    new = _log(["resetting match state (new one) x",
                "[left] t=1.00 clear_2 lines=1 (base=1 btb=0 ren=0) ren_source=flash_confirmed"])
    (tmp_path / "server.log.1").write_text("\n".join(old) + "\n", encoding="utf-8")
    (tmp_path / "server.log").write_text("\n".join(new) + "\n", encoding="utf-8")
    text = diag_summary.summary(tmp_path)
    assert text.index("new one") < text.index("old one")


def test_no_log_says_so(tmp_path):
    assert "no matches" in diag_summary.summary(tmp_path)
