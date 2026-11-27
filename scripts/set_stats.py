"""連戦平均 (a user's request): each player's average APM, PPS ... over the
set being played, shown in the match summary next to the match's own.

Worked out by the server from the finished matches (opener_stats' history,
kept by the HUD) and the match on screen. Where a set starts:
  - the set's WIN counter reads 0-0 at the start of a match (set_counter.py,
    read by the pipeline in the match's first seconds);
  - no counter seen and the last match ended more than SET_GAP_S ago;
  - the user's reset (a button in the settings): RESET_PATH holds its time.
"""
import json
import time
from pathlib import Path

SIDES = ("left", "right")
RESET_PATH = Path(__file__).resolve().parent.parent / "config" / "set_reset.json"
# with no counter to read, a match this long after the last one starts a new set
SET_GAP_S = 600.0
# averaged (the summary's number rows; the opener isn't)
KEYS = ("apm", "pps", "app", "vs", "lines_sent", "pieces", "max_ren", "tetris", "tspin",
        "tspin_single", "tspin_double", "tspin_triple", "tspin_mini", "perfect_clear")


def reset_now(path=RESET_PATH, now=None):
    """The user's reset: the set starts over from now."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"t": now if now is not None else time.time()}), encoding="utf-8")


def _reset_time(path):
    try:
        t = json.loads(Path(path).read_text(encoding="utf-8")).get("t")
        return float(t) if isinstance(t, (int, float)) else None
    except (OSError, ValueError, AttributeError):
        return None


def _numbers(side_state):
    """One player's numbers as the summary shows them (live state)."""
    import opener_stats
    return opener_stats.match_numbers(side_state or {})


class SetTracker:
    def __init__(self, reset_path=RESET_PATH):
        self.reset_path = reset_path
        self.since = None          # the set's start (a wall time), None: not known yet
        self._match = None         # the match on screen (its start time) already looked at
        self._counted = None       # ... and whether its counter has been looked at

    def update(self, state, history, now=None):
        """Called with each state: notes where the set starts. Returns the
        state["set"] entry (see summary)."""
        now = time.time() if now is None else now
        key = (state.get("match_start_t"), state.get("match_reset_count"))
        elapsed = state.get("match_elapsed_s") or 0
        if key != self._match and state.get("match_start_t") is not None and not state.get("frozen"):
            self._match, self._counted = key, False
            last = max((m["t"] for m in history if isinstance(m.get("t"), (int, float))), default=None)
            if self.since is None or last is None or now - elapsed - last > SET_GAP_S:
                self.since = now - elapsed - 1      # (a long break: a new set, counter or not)
        counter = state.get("set_counter")
        if key == self._match and not self._counted and counter is not None:
            self._counted = True
            if counter.get("zero"):
                self.since = now - elapsed - 1
        reset = _reset_time(self.reset_path)
        if reset is not None and (self.since is None or reset > self.since):
            self.since = reset
        return self.summary(state, history)

    def summary(self, state, history):
        """{"matches": n, "wins": {side: n}, "left": {key: average}, "right": ...}
        over the set's finished matches, the one on screen included once it's
        over; None before any."""
        if self.since is None:
            return None
        played = [m for m in history if isinstance(m.get("t"), (int, float)) and m["t"] >= self.since
                  and m.get("winner") in SIDES]
        rows = [{sd: (m.get(sd) or {}) for sd in SIDES} | {"winner": m["winner"]} for m in played]
        start = state.get("match_start_t")
        recorded = any(m.get("match_start_t") == start for m in played)
        if state.get("frozen") and state.get("winner") in SIDES and (state.get("match_elapsed_s") or 0) > 0 \
                and not recorded:
            rows.append({sd: ({"puyo": True} if (state.get(sd) or {}).get("puyo")
                              else {"stats": _numbers(state.get(sd))}) for sd in SIDES} | {"winner": state["winner"]})
        if not rows:
            return None
        out = {"matches": len(rows), "wins": {sd: sum(1 for r in rows if r["winner"] == sd) for sd in SIDES}}
        for sd in SIDES:
            sums, counts = {}, {}
            for r in rows:
                stats = r[sd].get("stats") or {}
                for k in KEYS:
                    v = stats.get(k)
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        sums[k] = sums.get(k, 0.0) + v
                        counts[k] = counts.get(k, 0) + 1
            out[sd] = {k: sums[k] / counts[k] for k in sums}
        return out
