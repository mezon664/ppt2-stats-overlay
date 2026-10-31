import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import numpy as np
from match_boundary import MatchBoundaryDetector, GO_ENTER, GO_EXIT, YATTA_ENTER, YATTA_EXIT
from capture_profile import REFERENCE_W, REFERENCE_H


def blank_frame():
    return np.full((REFERENCE_H, REFERENCE_W, 3), 30, dtype=np.uint8)


def test_no_edges_on_blank_frames():
    det = MatchBoundaryDetector()
    for i in range(10):
        v, g = det.update(blank_frame(), float(i))
        assert v is False
        assert g is False


def test_victory_edge_fires_once_on_sustained_presence(monkeypatch):
    det = MatchBoundaryDetector()
    scores = [0.1, 0.9, 0.9, 0.9, 0.1]  # rises above YATTA_ENTER, stays, then drops

    def fake_match(frame, tmpl, window):
        # called once per side (left/right) per frame; both must see the same
        # score for a given frame index, so index by frame count, not call count.
        return scores[int(frame[0, 0, 0])]

    import match_boundary
    monkeypatch.setattr(match_boundary, "_match", fake_match)

    edges = []
    for i in range(5):
        f = blank_frame()
        f[0, 0, 0] = i  # smuggle the frame index through so fake_match can read it
        edges.append(det.update(f, float(i))[0])
    assert edges == [False, True, False, False, False]


def test_go_disappeared_edge_fires_once_when_confidence_drops(monkeypatch):
    det = MatchBoundaryDetector()
    scores = iter([0.0, 0.2, 0.2, 0.01, 0.01])  # rises above GO_ENTER, then drops below GO_EXIT

    import match_boundary
    monkeypatch.setattr(match_boundary, "_orange_ratio", lambda frame, box: next(scores))

    edges = [det.update(blank_frame(), float(i))[1] for i in range(5)]
    assert edges == [False, False, False, True, False]


def test_hysteresis_gap_prevents_chatter_at_mid_confidence(monkeypatch):
    # a score that sits between GO_EXIT and GO_ENTER should never flip state once
    # active, and never activate if it never reaches GO_ENTER.
    mid = (GO_ENTER + GO_EXIT) / 2
    det = MatchBoundaryDetector()

    import match_boundary
    monkeypatch.setattr(match_boundary, "_orange_ratio", lambda frame, box: mid)

    edges = [det.update(blank_frame(), float(i))[1] for i in range(10)]
    assert not any(edges)  # never activated in the first place


def test_orange_banner_in_the_center_gap_is_seen_as_go():
    import cv2
    from match_boundary import GO_REGION
    det = MatchBoundaryDetector()
    f = blank_frame()
    x1, y1, x2, y2 = GO_REGION
    f[y1:y2, x1:x2] = 255                                   # white letters
    cv2.rectangle(f, (x1, y1), (x2 - 1, y2 - 1), (0, 110, 255), 25)  # thick orange outline (BGR)
    det.update(f, 0.0)
    assert det.last_go_conf >= GO_ENTER
    _, gone = det.update(blank_frame(), 1.0)
    assert gone is True


def _go_edges(monkeypatch, ratios):
    import match_boundary
    seq = iter(ratios)
    monkeypatch.setattr(match_boundary, "_orange_ratio", lambda frame, box: next(seq))
    det = MatchBoundaryDetector()
    return [det.update(blank_frame(), float(i))[1] for i in range(len(ratios))]


def test_go_on_a_stage_with_orange_background_is_seen_to_leave(monkeypatch):
    # measured live: this stage's background reads 0.097 in the GO! region,
    # GO! itself 0.20-0.26; with fixed thresholds it never read as gone
    ratios = [0.097] * 10 + [0.25, 0.22, 0.24] + [0.097] * 3
    edges = _go_edges(monkeypatch, ratios)
    assert edges.index(True) == 13
    assert edges.count(True) == 1


def test_background_drift_then_black_screen_is_not_a_go(monkeypatch):
    # the false start: background creeping just past 0.10, then a transition
    ratios = [0.097] * 10 + [0.105, 0.11, 0.104] + [0.0] * 5
    assert not any(_go_edges(monkeypatch, ratios))


def test_english_game_yeah_ends_the_match():
    """The English game says "Yeah!" where the Japanese one says 「やった!」
    (debug_frames/burst_english): either side's win is seen, ordinary play isn't."""
    import cv2
    fixtures = Path(__file__).resolve().parent / "fixtures"
    for name, won in (("en_yeah_left.jpg", True), ("en_yeah_right.jpg", True), ("en_play.jpg", False)):
        det = MatchBoundaryDetector()
        frame = cv2.imread(str(fixtures / name))
        victory, _ = det.update(frame, 0.0)
        assert victory is won, (name, det.last_yatta_conf)
