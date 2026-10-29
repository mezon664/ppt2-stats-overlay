import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import cv2
import numpy as np
from queue_tracker import NextQueueTracker, count_advances
from gameplay_gate import NEXT_TEMPLATE_PATH, NEXT_WINDOWS, QUEUE_SLOTS
from capture_profile import REFERENCE_W, REFERENCE_H

PIECE_BGR = {"I": (255, 255, 0), "O": (0, 255, 255), "T": (200, 0, 200), "S": (0, 255, 0),
             "Z": (0, 0, 255), "J": (255, 0, 0), "L": (0, 128, 255)}


def queue_frame(seq, side="left"):
    f = np.full((REFERENCE_H, REFERENCE_W, 3), 40, dtype=np.uint8)
    tmpl = cv2.imread(str(NEXT_TEMPLATE_PATH))
    th, tw = tmpl.shape[:2]
    x1, y1, _, _ = NEXT_WINDOWS[side]
    lx, ly = x1 + 15, y1 + 10
    f[ly:ly + th, lx:lx + tw] = tmpl
    for (a, b, c, d), piece in zip(QUEUE_SLOTS, seq):
        f[ly + b:ly + d, lx + a:lx + c] = PIECE_BGR[piece]
    return f


def feed(tracker, seqs, t0=0.0, dt=0.1):
    out, t = [], t0
    for s in seqs:
        out.extend(tracker.update(queue_frame(s), t))
        t += dt
    return out


def test_count_advances():
    assert count_advances("TJISO", "TJISO") == 0
    assert count_advances("TJISO", "JISOL") == 1
    assert count_advances("TJISO", "ISOLZ") == 2
    assert count_advances("ISOLO", "ISIIO") is None  # mid-slide misread


def test_reads_piece_letters():
    tr = NextQueueTracker("left")
    tr.update(queue_frame("TJISO"), 0.0)
    assert tr.last_reading == "TJISO"


def test_placement_is_stamped_when_the_new_queue_first_appears():
    tr = NextQueueTracker("left")
    placed = feed(tr, ["TJISO", "TJISO", "JISOL", "JISOL", "JISOL"])
    assert placed == [0.2]  # first seen at t=0.2, confirmed at t=0.3


def test_single_frame_misread_is_ignored():
    tr = NextQueueTracker("left")
    placed = feed(tr, ["ISOLO", "ISOLO", "ISIIO", "ISOLO", "ISOLO"])
    assert placed == []


def test_two_placements_between_readings():
    tr = NextQueueTracker("left")
    placed = feed(tr, ["TJISO", "TJISO", "ISOLZ", "ISOLZ"])
    assert placed == [0.2, 0.2]


def test_discard_first_shift_swallows_only_the_first_advance():
    # A confirmed match start (see queue_tracker.py docstring): the tracker's
    # first-ever shift is the first piece spawning, not a placement, so it's
    # dropped — but the next one counts normally.
    tr = NextQueueTracker("left", discard_first_shift=True)
    placed = feed(tr, ["TJISO", "TJISO", "JISOL", "JISOL", "JISOL", "ISOLZ", "ISOLZ"])
    assert placed == [0.5]  # the TJISO->JISOL shift is swallowed; ISOLZ counts
    assert tr.pieces_placed == 1


def test_discard_first_shift_off_by_default():
    tr = NextQueueTracker("left")  # discard_first_shift defaults to False
    placed = feed(tr, ["TJISO", "TJISO", "JISOL", "JISOL", "JISOL"])
    assert placed == [0.2]
    assert tr.pieces_placed == 1


def test_discard_first_shift_only_applies_once():
    tr = NextQueueTracker("left", discard_first_shift=True)
    placed = feed(tr, ["TJISO", "TJISO", "JISOL", "JISOL", "JISOL",
                        "ISOLZ", "ISOLZ", "SOLZT", "SOLZT"])
    assert placed == [0.5, 0.7]
    assert tr.pieces_placed == 2
