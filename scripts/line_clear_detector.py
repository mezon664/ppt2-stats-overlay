"""Lightweight line-clear detection via aggregate filled-cell-count deltas.

Deliberately NOT a piece tracker (board_tracker.py, shelved in phase 2 after its
line-clear-cascade problems were too noisy at the individual-cell/shape level).
This only watches ONE number per board: the total non-empty cell count, sampled
periodically with stability debouncing (same technique as the match-boundary
empty-board check) — never trying to identify which piece is falling, its shape,
or its exact position. A STABLE-to-STABLE transition in that single number is
classified purely by its SIZE:

  - a drop of ~10*N cells  -> N line(s) cleared (a full row disappearing removes
    exactly 10 cells; only clean rows can clear, so the signature is clean)
  - a rise of ~4 cells     -> a single tetromino locked without clearing anything
    (every piece is exactly 4 cells) -> breaks any combo in progress
  - a rise of ~10*N cells  -> N row(s) of incoming garbage added (not the
    player's own action; doesn't affect their own combo either way)
  - anything else          -> logged as unclassified, not acted on — per the
    project's own rule, an ambiguous reading must not be guessed into an event

This exists specifically to fix two things banner-only detection cannot:
  1. Plain (non-T-spin) 1-3 line clears, which show NO banner at all (confirmed
     directly by the user) — this gives at least the LINE COUNT (not type) by
     the size of the drop.
  2. True combo/REN continuity — the estimated REN count previously just counted
     recognized banner events, with no way to know a non-clearing placement
     happened in between and should have reset it (confirmed wrong against real
     footage: the real on-screen REN read 1, the estimate had drifted to 4).
"""
import logging

from board_read import count_non_empty

log = logging.getLogger("line_clear_detector")

CHECK_INTERVAL_S = 0.25
STABLE_FRAMES = 2            # consecutive identical raw readings before trusting a value
PLACEMENT_DELTA = 4          # one tetromino
PLACEMENT_TOLERANCE = 2
LINE_CELLS = 10
LINE_TOLERANCE = 2
MAX_LINES_PER_EVENT = 4      # a single clear event covers at most a Tetris


def _closest_line_count(delta_abs):
    """Returns (n_lines, residual) for the best-fitting multiple of 10, or None
    if even the best fit is outside LINE_TOLERANCE."""
    best_n, best_residual = None, None
    for n in range(1, MAX_LINES_PER_EVENT + 1):
        residual = abs(delta_abs - n * LINE_CELLS)
        if best_residual is None or residual < best_residual:
            best_n, best_residual = n, residual
    if best_residual is not None and best_residual <= LINE_TOLERANCE:
        return best_n, best_residual
    return None


class LineClearDetector:
    def __init__(self, check_interval_s=CHECK_INTERVAL_S, stable_frames=STABLE_FRAMES):
        self.check_interval_s = check_interval_s
        self.stable_frames = stable_frames
        self._last_check_t = None
        self._pending_count = None
        self._pending_streak = 0
        self._stable_count = None
        self.events = []        # (t, kind, value) kind in {"clear","place","garbage"}
        self.unclassified = []  # (t, delta) — logged, never acted on

    def update(self, board, t):
        """Returns the classified event for this check, or None (no change yet,
        not stable yet, or the check was skipped by the interval throttle)."""
        if self._last_check_t is not None and t - self._last_check_t < self.check_interval_s - 1e-6:
            return None
        self._last_check_t = t

        raw = count_non_empty(board)
        if raw == self._pending_count:
            self._pending_streak += 1
        else:
            self._pending_count = raw
            self._pending_streak = 1
        if self._pending_streak < self.stable_frames:
            return None  # not confirmed stable yet

        if self._stable_count is None:
            self._stable_count = raw
            return None  # first stable reading just establishes the baseline

        delta = raw - self._stable_count
        if delta == 0:
            return None
        self._stable_count = raw

        event = self._classify(delta, t)
        if event is None:
            self.unclassified.append((t, delta))
            log.info("[line_clear_detector] unclassified delta=%+d at t=%.2f", delta, t)
        else:
            self.events.append(event)
        return event

    def _classify(self, delta, t):
        if delta < 0:
            fit = _closest_line_count(-delta)
            if fit is not None:
                n_lines, _ = fit
                return (t, "clear", n_lines)
            return None
        # delta > 0
        if abs(delta - PLACEMENT_DELTA) <= PLACEMENT_TOLERANCE:
            return (t, "place", delta)
        fit = _closest_line_count(delta)
        if fit is not None:
            n_lines, _ = fit
            return (t, "garbage", n_lines)
        return None
