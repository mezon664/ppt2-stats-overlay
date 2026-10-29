"""APM aggregation.

Display APM (per user decision, overriding the earlier trailing-window design):
total lines sent so far in the match, divided by elapsed match time in minutes —
a single continuously-updating number, not a per-window breakdown. Example from
the user: 60 lines over a 2-minute match = 30 APM.

The windowed (10s/30s/60s) calculations are kept here and still computed — they
were the original spec's explicit requirement for distinguishing momentary spikes
from longer trends — but are no longer what the HUD/OBS overlays display by
default; `overall_apm` in snapshot() is.
"""
from collections import deque


class APMWindowTracker:
    def __init__(self, windows_s=(10, 30, 60), start_t=None):
        """start_t: explicitly pins the elapsed-time clock used by overall_apm()
        to a known moment (e.g. the instant "ゴー!" disappears), rather than
        leaving it to default to whenever the first event happens to land. Without
        this, the very first attack of a match set the clock running from itself
        — excluding the "dead" time between gameplay actually starting and that
        first attack from the denominator, which quietly inflates early-match APM
        and doesn't match the user's own definition (total lines / elapsed MATCH
        time, not elapsed time-since-first-attack)."""
        self.windows_s = tuple(windows_s)
        self.events = deque()  # (t, lines)
        self.total_lines = 0
        self.total_events = 0
        self.match_start_t = start_t
        self.peak_apm = {w: 0.0 for w in self.windows_s}

    def add_event(self, t, lines):
        if self.match_start_t is None:
            self.match_start_t = t
        self.events.append((t, lines))
        self.total_lines += lines
        self.total_events += 1
        self._evict(t)
        for w in self.windows_s:
            apm = self.window_apm(t, w)
            if apm > self.peak_apm[w]:
                self.peak_apm[w] = apm

    def amend_event(self, t, old_lines, new_lines):
        """Changes the line count of an event already added (e.g. a clear
        that turns out to be a Perfect Clear once its banner shows a moment
        later). Still one event; only its lines change."""
        for i, (et, el) in enumerate(self.events):
            if et == t and el == old_lines:
                self.events[i] = (t, new_lines)
                break
        self.total_lines += new_lines - old_lines
        for w in self.windows_s:
            apm = self.window_apm(t, w)
            if apm > self.peak_apm[w]:
                self.peak_apm[w] = apm

    def _evict(self, now, keep_s=None):
        # keep a bit more than the largest window so window_apm() stays correct
        # even if called with a slightly stale `now`.
        keep_s = keep_s or (max(self.windows_s) + 5)
        while self.events and now - self.events[0][0] > keep_s:
            self.events.popleft()

    def window_sum(self, now, window_s):
        return sum(lines for t, lines in self.events if now - t <= window_s)

    def window_apm(self, now, window_s):
        """Lines in the trailing window_s, normalized to a per-60s ("per minute") rate."""
        return self.window_sum(now, window_s) * (60.0 / window_s)

    def overall_apm(self, now, min_elapsed_s=1.0):
        """total_lines / elapsed_minutes. Guarded below min_elapsed_s to avoid a
        huge/meaningless spike from dividing by a near-zero match time right after
        the first event (e.g. 4 lines at t=0.1s would otherwise read as 2400 APM)."""
        if self.match_start_t is None:
            return 0.0
        elapsed_s = now - self.match_start_t
        if elapsed_s < min_elapsed_s:
            return 0.0
        return self.total_lines / (elapsed_s / 60.0)

    def snapshot(self, now):
        elapsed_s = round(now - self.match_start_t, 2) if self.match_start_t is not None else 0
        return {
            "apm": round(self.overall_apm(now), 2),
            "windows": {
                str(w): {
                    "lines": self.window_sum(now, w),
                    "apm": round(self.window_apm(now, w), 2),
                    "peak_apm": round(self.peak_apm[w], 2),
                }
                for w in self.windows_s
            },
            "total_lines": self.total_lines,
            "total_events": self.total_events,
            "match_elapsed_s": elapsed_s,
        }

    def reset(self):
        self.__init__(self.windows_s)
