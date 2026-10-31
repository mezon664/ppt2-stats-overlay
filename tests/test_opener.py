"""Opener (開幕テンプレ) detection: wiki shape data, matching rules, and real
frames where the left player had just built パフェ積み / 合掌TSD."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import cv2
import pytest
from capture_profile import compute_profile
from opener_detect import OpenerDetector, OpenerIndex, load_openers, match_openers, screen_name

FIXTURES = Path(__file__).resolve().parent / "fixtures"
OPENERS = load_openers()


def board(shape, extra=()):
    rows = [list(r) for r in shape] + [[False] * 10 for _ in range(20 - len(shape))]
    for r, c in extra:
        rows[r][c] = not rows[r][c]
    return rows


def test_shown_names_drop_the_variant_in_parentheses():
    assert screen_name("パフェ積み(中あけ)") == "パフェ積み"
    assert screen_name("りねパフェ（左凸）") == "りねパフェ"
    assert screen_name("T土台りねパフェ") == "T土台りねパフェ"
    assert not any("(" in n or "（" in n for n, *_ in OPENERS)


def test_every_shape_matches_its_own_opener():
    """Every wiki shape (as the game shows it, cleared lines dropped) is found.
    A few boards belong to several openers (the same first bag): then all of
    them are named."""
    index = OpenerIndex(OPENERS)
    for name, shape, _ in OPENERS:
        assert name in match_openers(board(shape), index)


def test_all_the_wiki_openers_are_in():
    names = {name for name, *_ in OPENERS}
    assert len(names) > 1000 and len(OPENERS) > 4000
    for known in ("迷走砲", "合掌TSD", "パフェ積み", "りねパフェ", "TKI積み", "開幕DT砲"):
        assert known in names, known


def test_one_cell_off_is_not_called_anything():
    index = OpenerIndex(OPENERS)
    for name, shape, _ in OPENERS[::25]:   # a sample: every cell of every shape takes minutes
        for r in range(len(shape)):
            for c in range(10):
                names = match_openers(board(shape, [(r, c)]), index)
                assert name not in names


def test_blocks_right_above_the_shape_spoil_it_but_higher_ones_do_not():
    from opener_detect import CLEAR_ROWS_ABOVE
    name, shape, _ = next(s for s in OPENERS if s[0] == "迷走砲")
    h = len(shape)
    assert name not in match_openers(board(shape, [(h, 4)]), OPENERS)                 # touching the shape
    assert name in match_openers(board(shape, [(h + CLEAR_ROWS_ABOVE, 4), (18, 4)]), OPENERS)  # falling piece / sparkles


def test_a_small_leftover_shape_waits_for_enough_pieces():
    """An opener that clears lines in its first bag can leave only a few
    cells; that board only counts once about that many pieces are down."""
    from opener_detect import PLACEMENT_SLACK
    name, shape, pieces = min((s for s in OPENERS if s[2]), key=lambda s: sum(map(sum, s[1])))
    index = OpenerIndex(OPENERS)
    assert name not in match_openers(board(shape), index, placements=2)
    assert name in match_openers(board(shape), index, placements=pieces - PLACEMENT_SLACK)


def test_shown_name_keeps_it_short():
    from opener_detect import shown_name
    assert shown_name(["A"]) == "A" and shown_name(["A", "B"]) == "A / B"
    assert shown_name(["A", "B", "C", "D"]) == "A / B ほか"


def detect(fixture, side="left"):
    frame = cv2.imread(str(FIXTURES / fixture))
    det = OpenerDetector(side, compute_profile(frame.shape[1], frame.shape[0]))
    return det.on_placements(frame, 1)


@pytest.mark.parametrize("fixture,name", [
    ("opener_pco_left.jpg", "パフェ積み"),
    ("opener_gassho_left.jpg", "合掌TSD"),
    ("opener_meisou_left.jpg", "迷走砲"),        # live, mirrored, hard-drop sparkles above
    ("opener_gassho_live_left.jpg", "合掌TSD"),  # live, missed when only checked on placements
])
def test_real_frames(fixture, name):
    assert detect(fixture) == name


@pytest.mark.parametrize("fixture,side", [
    # (play_ice_stage.jpg's right side was here: it is in fact a first-bag
    # T-SPIN Double setup, now named from the board just before the T-spin)
    ("tsd_left.jpg", "left"), ("play_ice_stage.jpg", "left"),
    ("opener_pco_left.jpg", "right"), ("setend_menu.jpg", "left"),
])
def test_no_opener_on_other_boards(fixture, side):
    assert detect(fixture, side) is None


def test_only_the_first_placements_are_checked():
    from opener_detect import MAX_PLACEMENTS
    frame = cv2.imread(str(FIXTURES / "opener_pco_left.jpg"))
    det = OpenerDetector("left", compute_profile(frame.shape[1], frame.shape[0]))
    det.placements = MAX_PLACEMENTS        # first bag long over (e.g. a mid-match board)
    assert det.on_placements(frame, 1) is None
    assert det.name is None


def with_garbage(frame, rows, holes=(3, 6, 0, 8), color=(205, 205, 205)):
    """The left board pushed up by `rows` garbage rows (grey, one hole each),
    the way garbage received during the opening lifts the stack."""
    from capture_profile import scale_box
    from board_read import LEFT_BOX, ROWS, COLS, cell_center
    h, w = frame.shape[:2]
    box = scale_box(LEFT_BOX, compute_profile(w, h))
    x1, y1, x2, y2 = box
    cell_h, cell_w = (y2 - y1) / ROWS, (x2 - x1) / COLS
    out = frame.copy()
    shift = int(round(cell_h * rows))
    out[y1:y2 - shift, x1:x2] = frame[y1 + shift:y2, x1:x2]
    for r in range(rows):
        row = ROWS - 1 - r
        for col in range(COLS):
            cx, cy = cell_center(box, col, row)
            fill = (15, 15, 25) if col == holes[r % len(holes)] else color
            cv2.rectangle(out, (int(cx - cell_w / 2) + 1, int(cy - cell_h / 2) + 1),
                          (int(cx + cell_w / 2) - 1, int(cy + cell_h / 2) - 1), fill, -1)
    return out


def detect_frame(frame, side="left"):
    return OpenerDetector(side, compute_profile(frame.shape[1], frame.shape[0])).on_placements(frame, 1)


@pytest.mark.parametrize("rows", [1, 2, 4])
def test_opener_on_top_of_garbage(rows):
    """Garbage received during the opening (user's request): the shape is
    found on top of it."""
    frame = cv2.imread(str(FIXTURES / "opener_meisou_left.jpg"))
    assert detect_frame(with_garbage(frame, rows)) == "迷走砲"


def test_coloured_rows_are_not_garbage():
    """A row of the player's own (colored) blocks with one gap is not
    garbage, so nothing is set aside for it."""
    frame = cv2.imread(str(FIXTURES / "opener_meisou_left.jpg"))
    assert detect_frame(with_garbage(frame, 2, color=(40, 160, 230))) is None


def test_t_spin_openers_are_found_just_before_the_t_spin():
    """A tag whose first bag clears lines with a T-spin is never on screen as
    drawn (the rows clear at once); it's recognized from the board just
    before the T goes in."""
    from opener_detect import _before_the_t_spin, _shape_rows, T_CELLS
    import json
    from pathlib import Path
    data = json.loads((Path(__file__).resolve().parent.parent / "assets" / "openers.json").read_text(encoding="utf-8"))
    op, raw = next((o, r) for o in data["openers"] for r in map(_shape_rows, o["shapes"])
                   if any(all(row) for row in r) and _before_the_t_spin(r))
    name = op.get("display") or op["name"]
    befores = _before_the_t_spin(raw)
    assert befores
    index = OpenerIndex(OPENERS)
    for rows in befores:
        assert sum(map(sum, rows)) == sum(map(sum, raw)) - 4      # the same board, minus the T
        assert not any(all(r) for r in rows)
        assert screen_name(name) in match_openers(board(rows), index)


def test_english_names():
    """English (overlay language): Hard Drop's name, else the wiki's English
    name, else the Japanese one (user's rule)."""
    from opener_detect import load_english, shown_name
    en = load_english()
    assert en.get("迷走砲") == "Stray Cannon"
    assert en.get("無名砲") in ("Pelican", "Pelican Opener")
    assert len(en) > 300
    assert "合掌TSD" not in en or en["合掌TSD"].isascii()
    assert shown_name(["A", "B", "C"], "en") == "A / B etc."


def test_detector_gives_both_languages():
    frame = cv2.imread(str(FIXTURES / "opener_meisou_left.jpg"))
    det = OpenerDetector("left", compute_profile(frame.shape[1], frame.shape[0]))
    assert det.on_placements(frame, 1) == "迷走砲"
    assert det.name_en == "Stray Cannon"


def test_english_names_drop_their_bracket_part_too():
    """User: no (…) part in English either, same as the Japanese names."""
    from opener_detect import load_english
    names = load_english().values()
    assert names and not any("(" in n or "（" in n for n in names)
