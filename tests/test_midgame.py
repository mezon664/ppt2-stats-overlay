"""Mid-game setups (scripts/midgame.py) on boards drawn after Hard Drop Tetris Wiki's diagrams."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import midgame  # noqa: E402


def board(*rows):
    """Rows top to bottom (any letter a block), put at the bottom of a 20 x 10 board."""
    grid = [[False] * 10 for _ in range(20 - len(rows))]
    grid += [[c != "." for c in r] for r in rows]
    return grid


# Hard Drop: Super T-Spin Double, "Create overhang"
STSD = board("..SS......", "...SSSSSSS", "SS.SSSSSSS", "S..SSSSSSS", "S..SSSSSSS")
# Hard Drop: Double Triple Cannon Setups, "IT Balance 1"
DT = board("..OO......", "..OO......", "...L......", "JJ.LGGGGGG", "J..LLGGGGG", "J...TGGGSG",
           "OO.TTTZZSS", "OO.IIIIZZS")
# Hard Drop: Triple Double Attack Setups, "SZT Core"
TD = board("JJ..GGGGGG", "J...GGGGGG", "J.TTTGGGGG", "L..TSGGGOO", "L.ZZSSGGOO", "LL.ZZSIIII")
# Hard Drop: King Crimson, basic setup
KC = board("......GG..", "GGGGGGG...", "GGGGGGG.LL", "GGGGGGG..L", "GGGGGGG.SL", "GGGGGGG.SS",
           "GGGGGGG..S", "GGGGGGG..G")
# Hard Drop: FinT Cannon, before the Fin-TSD
FIN = board("LLL....JJ.", "LZ.....JOO", "ZZ.IIIIJOO", "ZG....GGGG", "GG....GGGG", "GGGG..GGGG",
            "GGGGG.GGGG")


def test_each_setup_is_found_and_only_it():
    assert midgame.find(STSD) == {"STSD"}
    assert midgame.find(DT) == {"DT砲"}
    assert midgame.find(TD) == {"TDアタック"}
    assert midgame.find(KC) == {"キングクリムゾン"}
    assert midgame.find(FIN) == {"TスピンFIN"}


def test_mirrored_too():
    flip = [list(reversed(r)) for r in STSD]
    assert midgame.find(flip) == {"STSD"}


def test_plain_boards_are_nothing():
    assert midgame.find(board()) == set()
    assert midgame.find(board("GGGGGGGGG.", "GGGGGGGGG.", "GGGGGGGGG.")) == set()   # a Tetris well
    # a plain TSD slot
    assert midgame.find(board("...GGGGGGG", "GG...GGGGG", "GGG.GGGGGG")) == set()


def test_called_out_only_when_the_t_spin_comes():
    w = midgame.Watch()
    w.see(STSD, 0.0)
    assert w.spun("tsd", 0.2) is None          # seen once: could be a piece passing by
    w.see(STSD, 0.1)
    assert w.spun("tst", 0.5) is None          # not the spin it's for
    assert w.spun("tsd", 0.5) == "STSD"
    assert w.spun("tsd", 0.9) is None          # once


def test_too_late_is_nothing():
    w = midgame.Watch()
    w.see(DT, 0.0)
    w.see(DT, 0.1)
    assert w.spun("tsd", 0.1 + midgame.HOLD_S + 0.5) is None


def test_king_crimson_then_its_stsd_is_not_said_again():
    w = midgame.Watch()
    w.see(KC, 0.0)
    w.see(KC, 0.1)
    assert w.spun("tst", 0.5) == "キングクリムゾン"
    w.see(STSD, 1.0)
    w.see(STSD, 1.1)
    assert w.spun("tsd", 1.5) is None


def _own_board(rows):
    """A setup's shape on an otherwise empty board, at the left wall (its under row the floor)."""
    shape = rows[:-1]
    grid = [[False] * 10 for _ in range(20 - len(shape))]
    grid += [[c == "#" for c in r] + [False] * (10 - len(r)) for r in shape]
    return grid


def test_every_setup_is_the_one_found_on_its_own_board():
    for name, s in midgame.SETUPS.items():
        if s["rows"][-1].count("?"):      # (drawn with an open under row: the tests above)
            continue
        found = midgame.find(_own_board(s["rows"]))
        assert midgame.best(found) == name, (name, found)


def test_the_bigger_setup_wins():
    w = midgame.Watch()
    for name in ("STSD", "超未来"):
        w._seen[name] = 0.0
    assert w.spun("tsd", 0.5) == "超未来"


def test_dks_goes_by_its_short_name_too():
    assert midgame.names("ダークネスカズスペシャル") == ["ダークネスカズスペシャル", "DKS"]
    assert midgame.names("STSD") == ["STSD"]


# Hard Drop: Fractal ("Japanese people use the term Double Dagger")
DAGGER2 = board("...GG.....", "GGGG...GGG", "GGGGG.GGGG", "GGGG...GGG", "GGGGG.GGGG")
DAGGER3 = board("...GG.....", "GGGG...GGG", "GGGGG.GGGG", "GGGG...GGG", "GGGGG.GGGG", "GGGG...GGG", "GGGGG.GGGG")


def test_double_and_triple_dagger():
    assert midgame.best(midgame.find(DAGGER2)) == "ダブルダガー"
    assert midgame.best(midgame.find(DAGGER3)) == "トリプルダガー"


def test_a_tst_tower_from_a_real_game():
    """A user's TSTタワー (the board before its TST, from the log): the tower itself, whatever's above it."""
    rows = [".....####.", ".....#####", ".....#####", ".....#####", ".#########", "##########",
            "##.#######", "#..#######", "##.#######", "##.#######", "#..#######", "##.#######",
            "########.#", "#.########", "#.########", "#######.##", "#######.##", "#######.##", "#.########"]
    assert midgame.best(midgame.find(board(*rows))) == "TSTタワー（永久機関）"


def test_an_stsd_over_an_empty_column():
    """A user's STSD (from the log) stood over a column left open below it: still an STSD."""
    rows = ["#...##..#.", "#...#####.", "##.######.", "##...#####", "####.#####", "###..#####", "###..#####",
            "###.######", "###.######", "###.######", "###.######", "##.#######", "##.#######", "#####.####"]
    assert midgame.best(midgame.find(board(*rows))) == "STSD"
