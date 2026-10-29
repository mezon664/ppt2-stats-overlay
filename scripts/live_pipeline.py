"""Ties recognition (banner_detect) + attack table (attack_calc) + windowed
aggregation (apm_tracker) together into one running pipeline, fed by either a
live game-window capture or a recorded video (for testing/replay).

PPS comes from NEXT-queue advances (queue_tracker.py), not board tracking —
board_tracker.py was shelved after phase 2's line-clear-cascade problems.
"""
import time
import logging
from dataclasses import dataclass, field

import cv2

from banner_detect import BannerTracker, load_templates
from attack_calc import load_table, compute_attack, is_b2b_eligible
from i18n import CLEAR_TYPE_LABEL_EN, REN_BREAK_EN
from apm_tracker import APMWindowTracker
from board_read import board_is_clear, LEFT_BOX, RIGHT_BOX
from capture_profile import scale_box, REFERENCE_PROFILE
from match_boundary import MatchBoundaryDetector
from flash_clear_detector import FlashClearDetector, MAX_LINES_PER_EVENT
from queue_tracker import NextQueueTracker
from gameplay_gate import GameplayGate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("live_pipeline")

CLEAR_TYPE_LABEL_JA = {
    "clear_1": "1ライン",
    "clear_2": "2ライン",
    "clear_3": "3ライン",
    "clear_4": "TETRIS",
    "tspin_double": "T-SPIN Double",
    "tspin_single": "T-SPIN Single",
    "tspin_triple": "T-SPIN Triple",
    "tspin_mini": "T-SPIN Mini",
}

EVENT_LOG_MAX = 15  # recent entries kept per side, for on-screen verification of what was recognized

# Lines each banner type clears, checked against the clear flash's lit rows.
BANNER_LINES = {"clear_4": 4, "tspin_double": 2, "tspin_single": 1, "tspin_triple": 3}


def format_event_log_entry(t, ev, lines):
    """Builds the on-screen log entry for one recognized attack event. Pulled out
    as its own function so the formatting (what the user actually reads to verify
    recognition is working) can be unit-tested without needing real template
    matching / a live frame."""
    label_ja = CLEAR_TYPE_LABEL_JA.get(ev["clear_type"], ev["clear_type"])
    label_en = CLEAR_TYPE_LABEL_EN.get(ev["clear_type"], ev["clear_type"])
    parts, parts_en = [f"+{lines}段"], [f"+{lines}"]
    if ev.get("perfect_clear"):
        # A Perfect Clear's 10 lines replace base/BtB/REN entirely (see
        # attack_calc.compute_attack), so those aren't listed as if they added.
        text = f"PERFECT CLEAR（{label_ja}） +{lines}段"
        text_en = f"PERFECT CLEAR ({label_en}) +{lines}"
        label_ja = "PERFECT CLEAR"
    else:
        extra = []
        if ev["btb"]:
            extra.append("BtB")
        if ev["ren_count"] and ev["ren_count"] >= 1:  # game numbering: 2nd consecutive clear = "1REN"
            extra.append(f"{ev['ren_count']}REN")
        text = f"{label_ja} " + " ".join(parts + extra)
        text_en = f"{label_en} " + " ".join(parts_en + extra)
    return {
        "t": round(t, 2),
        "label": label_ja,
        "lines": lines,
        "btb": ev["btb"],
        "ren_count": ev["ren_count"],
        "ren_source": ev["ren_source"],
        "perfect_clear": bool(ev.get("perfect_clear")),
        "text": text,
        "text_en": text_en,
    }


def format_ren_break_entry(t):
    """Same shape as format_event_log_entry's output, so the HUD's log
    rendering doesn't need a special case — a REN break has no clear_type
    or line count of its own, just the fact that the streak ended."""
    return {
        "t": round(t, 2),
        "label": "REN途切れ",
        "lines": 0,
        "btb": False,
        "ren_count": 0,
        "ren_source": "placement_without_clear",
        "text": "REN途切れ（クリアなし設置）",
        "text_en": REN_BREAK_EN,
    }


@dataclass
class PlayerPipeline:
    side: str
    templates: dict
    profile: object = None
    table: dict = field(default_factory=load_table)
    tracker: BannerTracker = None
    apm: APMWindowTracker = None
    last_event: dict = None
    last_frame_ok_t: float = None

    debug_dump_dir: str = None
    clock_start_t: float = None  # see APMWindowTracker's start_t docstring

    # A flash with no banner anywhere nearby only falls through to a plain
    # clear_N event after this much time has passed without one showing up —
    # a real banner can take noticeably longer to cross its own confidence
    # threshold than the flash does (confirmed: flash at t=8.03, matching
    # TETRIS banner only confirmed at t=8.73; live play showed gaps over 1s
    # too), so resolving too eagerly would both mislabel a real T-SPIN/TETRIS
    # as a plain clear_N here AND let the banner event double-count it when
    # it arrives a beat later.
    FLASH_GRACE_S = 1.5
    # A banner only counts if a real clear flash (1-4 lit rows) came within
    # this long before it. Every real clear flashes, and its banner follows
    # 0.07-0.7s later (all banner events in the recordings); banners with no
    # flash were all template false positives — e.g. the right-side TETRIS
    # template scoring ~0.61 on a garbage-filled board, credited 6 TETRISes
    # to a player who had placed 18 pieces and scored 200 points.
    BANNER_FLASH_WINDOW_S = 1.6
    # "PERFECT CLEAR" shows over the player's board right after the clear
    # that emptied it. It turns that clear's attack into a fixed 10 lines
    # (attack_table perfect_clear). The banner is paired with a clear whose
    # event time (its flash, or its TETRIS/T-SPIN banner) is at most
    # PC_AFTER_S before the PC banner or PC_BEFORE_S after it; a PC banner
    # with no clear in that span is not counted.
    PC_AFTER_S = 1.6
    PC_BEFORE_S = 0.6

    def __post_init__(self):
        self.tracker = BannerTracker(
            self.side, self.templates, profile=self.profile,
            debug_dump_dir=self.debug_dump_dir, debug_dump_labels={"tspin_double", "tspin_single", "tspin_triple", "tetris"},
        )
        self.apm = APMWindowTracker(start_t=self.clock_start_t)
        self.event_log = []  # newest first; for on-screen "what was recognized" verification
        self.flash_detector = FlashClearDetector(self.side, profile=self.profile,
                                                  debug_dump_dir=self.debug_dump_dir)
        self.queue_tracker = NextQueueTracker(self.side, profile=self.profile)
        self._clear_flash_times = []   # flash edges with 1-4 lit rows not yet attributed to a placement
        self._banner_flash_times = []  # the same flashes, each usable to back one banner event
        self.rejected_banner_count = 0
        self._last_placement_t = None
        self._pending_breaks = []      # REN breaks waiting for older clears to resolve first
        # Flashes awaiting resolution, oldest first: {"flash_t":, "n_lines":}.
        # n_lines is measured once, at the flash's own rising-edge frame (see
        # FlashClearDetector.last_edge_row_count) — NOT re-derived later from
        # board-state diffing. An earlier version compared filled-cell counts
        # before/after the flash and got noisy, unusable deltas on real
        # footage (-4, +27, -129 for genuine single-digit-line clears); the
        # flash's own row extent turned out to measure the true line count
        # directly and exactly (validated against a user-run ground-truth
        # 1/2/3/4-line sequence and 8 banner-confirmed events — every single
        # one matched). A QUEUE, not a single slot — an earlier version only
        # tracked one pending flash at a time, so a second real clear within
        # the first one's grace window was silently dropped entirely
        # (confirmed bug: fast consecutive plain clears never showed up).
        self._pending_flashes = []
        self.confirmed_flash_clear_count = 0  # flash events that measured a real line count
        self.dismissed_flash_count = 0  # flash events with no lit rows at all (not a real clear)
        self._pc_active = False      # PERFECT CLEAR banner on screen last frame
        self._recent_events = []     # emitted clears, kept briefly so a later PC banner can upgrade one
        self.perfect_clear_count = 0
        # per-match counts for the end-of-match summary
        self.tetris_count = 0
        self.tspin_count = 0
        self.max_ren = 0

    def _emit_attack_event(self, t, ev, lines, result):
        if ev.get("perfect_clear"):
            result = compute_attack(self.table, ev["clear_type"], ev["ren_count"], 0, perfect_clear=True)
            lines = result["total"]
            self.perfect_clear_count += 1
        self.apm.add_event(t, lines)
        self.last_event = {**ev, "lines": lines, "breakdown": result}
        if ev["clear_type"] == "clear_4":
            self.tetris_count += 1
        elif ev["clear_type"].startswith("tspin_"):
            self.tspin_count += 1
        self.max_ren = max(self.max_ren, ev.get("ren_count") or 0)
        entry = format_event_log_entry(t, ev, lines)
        self.event_log.insert(0, entry)
        del self.event_log[EVENT_LOG_MAX:]
        self._recent_events = [e for e in self._recent_events if t - e["t"] <= 5.0]
        self._recent_events.append({"t": t, "ev": ev, "lines": lines, "entry": entry})
        log.info("[%s] t=%.2f %s lines=%d (base=%d btb=%d ren=%d%s) ren_source=%s",
                  self.side, t, ev["clear_type"], lines,
                  result["base"], result["btb"], result["ren"],
                  " PERFECT CLEAR" if ev.get("perfect_clear") else "", ev["ren_source"])

    def _on_pc_edge(self, t):
        """The PC banner just appeared: the clear that emptied the board is the
        LATEST clear before it (in a REN chain the earlier clears in the window
        are not the PC). That clear is either still waiting out its flash grace
        period — then it's marked and emitted as a PC later — or was already
        counted via its TETRIS / T-SPIN banner, in which case it's upgraded to
        10 lines now. No clear in the span: the banner isn't counted."""
        candidates = []
        for pf in self._pending_flashes:
            if 1 <= pf["n_lines"] <= MAX_LINES_PER_EVENT and \
                    t - self.PC_AFTER_S <= pf["flash_t"] <= t + self.PC_BEFORE_S:
                candidates.append((pf["flash_t"], "pending", pf))
        for e in self._recent_events:
            if not e["ev"].get("perfect_clear") and t - self.PC_AFTER_S <= e["t"] <= t + self.PC_BEFORE_S:
                candidates.append((e["t"], "emitted", e))
        if not candidates:
            log.info("[%s] PERFECT CLEAR banner at t=%.2f ignored (no clear just before it)", self.side, t)
            return
        _, kind, item = max(candidates, key=lambda c: c[0])
        if kind == "pending":
            item["perfect_clear"] = True
            return
        e = item
        ev = {**e["ev"], "perfect_clear": True}
        result = compute_attack(self.table, ev["clear_type"], ev["ren_count"], 0, perfect_clear=True)
        new_lines = result["total"]
        self.apm.amend_event(e["t"], e["lines"], new_lines)
        e["entry"].clear()
        e["entry"].update(format_event_log_entry(e["t"], ev, new_lines))  # same dict as in event_log
        e["ev"], e["lines"] = ev, new_lines
        if self.last_event is not None and self.last_event.get("clear_type") == ev["clear_type"]:
            self.last_event = {**ev, "lines": new_lines, "breakdown": result}
        self.perfect_clear_count += 1
        log.info("[%s] t=%.2f PERFECT CLEAR: %s at t=%.2f upgraded to %d lines",
                 self.side, t, ev["clear_type"], e["t"], new_lines)

    def _resolve_pending_flashes(self, t):
        """Emits (or drops) each flash once its banner grace period has
        passed, using the line count measured at the flash's own rising edge
        (see __init__). 0 lit rows means the flash wasn't a real clear (e.g.
        a spin-flash effect with no clear, confirmed as a live false-positive
        source — see live debug dumps), so it's dropped rather than
        fabricating a REN-advancing event for it. An out-of-range count (more
        than MAX_LINES_PER_EVENT) means the row-reading itself was unreliable
        for this frame, so it's dropped too rather than guessed."""
        still_pending = []
        for pf in self._pending_flashes:
            if t - pf["flash_t"] < self.FLASH_GRACE_S:
                still_pending.append(pf)
                continue
            n_lines = pf["n_lines"]
            if not (1 <= n_lines <= MAX_LINES_PER_EVENT):
                self.dismissed_flash_count += 1
                log.info("[%s] flash at t=%.2f dismissed (measured %d lit rows, not a real clear)",
                          self.side, pf["flash_t"], n_lines)
                continue
            clear_type = f"clear_{n_lines}"
            self.confirmed_flash_clear_count += 1
            ren_count, b2b_streak = self.tracker.streak.register_clear(self.table, clear_type)
            min_streak = self.table["back_to_back"]["min_consecutive_for_bonus"]
            btb = is_b2b_eligible(self.table, clear_type) and b2b_streak >= min_streak
            result = compute_attack(self.table, clear_type, ren_count, b2b_streak)
            ev = {"clear_type": clear_type, "btb": btb, "ren_count": ren_count, "ren_source": "flash_confirmed"}
            if pf.get("perfect_clear"):
                ev["perfect_clear"] = True
            self._emit_attack_event(pf["flash_t"], ev, result["total"], result)
        self._pending_flashes = still_pending

    def process_frame(self, frame, t):
        """Flash-based clear detection (flash_clear_detector.py) supplements —
        never replaces — banner detection below. Fixes two things banner-only
        detection could not: plain (non-T-spin) clears show NO banner at all
        (user-confirmed), and the REN estimate had no way to know a clear
        happened at all when no banner fired for it, so it silently drifted
        away from the real on-screen value. A flash with no corresponding
        banner gets its line count from the flash's own row extent, measured
        at the rising edge — see _resolve_pending_flashes."""
        streak = self.tracker.streak
        streak_before = (streak.consecutive_clears, streak.b2b_streak)
        before = len(self.tracker.attack_events)
        self.tracker.update(frame, t)
        self.last_frame_ok_t = t
        new_events = self.tracker.attack_events[before:]
        pc_state = self.tracker.states.get("perfect_clear")
        pc_on = bool(pc_state and pc_state.active)
        if pc_on and not self._pc_active:
            self._on_pc_edge(t)
        self._pc_active = pc_on

        flash_edge = self.flash_detector.update(frame, t)
        if flash_edge:
            n_lines = self.flash_detector.last_edge_row_count
            self._pending_flashes.append({"flash_t": t, "n_lines": n_lines})
            if 1 <= n_lines <= MAX_LINES_PER_EVENT:
                self._clear_flash_times.append(t)
                self._banner_flash_times.append((t, n_lines))

        new_events = self._keep_flash_backed_banners(new_events, t, streak_before)

        # REN break: a placement (NEXT queue advance) with no clear flash since
        # the previous placement — see queue_tracker.py. Queued rather than
        # applied now: a plain clear just before it may still be waiting out
        # its banner grace period, and applying the break first would let that
        # clear count as REN 1 of a new chain instead of ending the old one.
        for placed_t in self.queue_tracker.update(frame, t):
            prev = self._last_placement_t
            cleared = any((prev is None or f > prev) and f <= placed_t for f in self._clear_flash_times)
            if not cleared:
                self._pending_breaks.append(placed_t)
            self._last_placement_t = placed_t
            self._clear_flash_times = [f for f in self._clear_flash_times if f > placed_t]

        # Each banner-confirmed clear this frame accounts for one pending
        # flash (oldest first — a burst of several real clears shouldn't let a
        # later banner steal an earlier flash's slot) so it isn't ALSO
        # resolved as a plain clear_N and double-counted.
        for i in range(min(len(new_events), len(self._pending_flashes))):
            if self._pending_flashes.pop(0).get("perfect_clear"):
                new_events[i]["perfect_clear"] = True  # PC banner came before this clear's own banner

        self._resolve_pending_flashes(t)

        for ev in new_events:
            # compute_attack takes b2b_streak (an int), not the already-resolved
            # btb bool. Synthesize a streak value that reproduces exactly that bool
            # through compute_attack's own threshold check, rather than reading
            # self.tracker.streak.b2b_streak after the fact — that reflects
            # whatever the LAST event in this frame's batch left it at, which is
            # only correct here because in practice at most one clear event fires
            # per processed frame; this sidesteps that assumption entirely.
            min_streak = self.table["back_to_back"]["min_consecutive_for_bonus"]
            b2b_streak = min_streak if ev["btb"] else 0
            result = compute_attack(self.table, ev["clear_type"], ev["ren_count"], b2b_streak)
            self._emit_attack_event(t, ev, result["total"], result)

        self._apply_ready_breaks()

    def _keep_flash_backed_banners(self, new_events, t, streak_before):
        """Drops banner events with no matching clear flash just before them
        (see BANNER_FLASH_WINDOW_S). "Matching" means the flash lit the number
        of rows that banner clears — that held for every real banner in the
        recordings (TETRIS 4, T-SPIN Double 2, T-SPIN Single 1) — so one real
        plain clear can't lend its flash to a false TETRIS right after it."""
        self._banner_flash_times = [(f, n) for f, n in self._banner_flash_times
                                    if t - f <= self.BANNER_FLASH_WINDOW_S]
        if not new_events:
            return new_events
        accepted = []
        for ev in new_events:
            want = BANNER_LINES.get(ev["clear_type"])
            match = next((i for i, (_, n) in enumerate(self._banner_flash_times)
                          if want is None or n == want), None)
            if match is None:
                self.rejected_banner_count += 1
                log.info("[%s] t=%.2f %s banner ignored (no matching clear flash before it)",
                         self.side, t, ev["clear_type"])
                continue
            self._banner_flash_times.pop(match)
            accepted.append(ev)
        if len(accepted) != len(new_events):
            # BannerTracker already applied every event to the REN/B2B streak;
            # rewind and replay only the ones that count.
            streak = self.tracker.streak
            streak.consecutive_clears, streak.b2b_streak = streak_before
            min_streak = self.table["back_to_back"]["min_consecutive_for_bonus"]
            for ev in accepted:
                ren, b2b = streak.register_clear(self.table, ev["clear_type"])
                if ev["ren_source"] != "screen":
                    ev["ren_count"] = ren
                ev["btb"] = is_b2b_eligible(self.table, ev["clear_type"]) and b2b >= min_streak
        return accepted

    def _apply_ready_breaks(self):
        """Applies queued REN breaks in time order, each only once every clear
        flash that happened before it has been resolved."""
        while self._pending_breaks:
            b = self._pending_breaks[0]
            if any(pf["flash_t"] < b for pf in self._pending_flashes):
                return
            self._pending_breaks.pop(0)
            streak = self.tracker.streak
            if streak.consecutive_clears == 0:
                continue  # nothing to end
            ended = streak.ren_count
            streak.register_clear(self.table, None)
            if ended == 0:
                continue  # a lone clear (REN 0) — reset, but no on-screen REN ended, so don't log it
            self.event_log.insert(0, format_ren_break_entry(b))
            del self.event_log[EVENT_LOG_MAX:]
            log.info("[%s] t=%.2f REN broke after %dREN (placement without a clear)", self.side, b, ended)

    def snapshot(self, now, elapsed_s=None):
        return {
            "apm": self.apm.snapshot(now),
            "last_event": self.last_event,
            "event_log": self.event_log,
            # Pieces come from NEXT-queue advances (queue_tracker.py), the same
            # placements the REN-break logic is validated against; PPS is over
            # match time (pause excluded), like APM.
            "pieces": self.queue_tracker.pieces_placed,
            "pps": round(self.queue_tracker.pieces_placed / elapsed_s, 2) if elapsed_s and elapsed_s >= 1.0 else None,
            # APP (attack per piece) = lines sent / pieces placed: how much each
            # piece sends, independent of speed.
            "app": round(self.apm.total_lines / self.queue_tracker.pieces_placed, 2)
                   if self.queue_tracker.pieces_placed else None,
            "capture_ok": self.last_frame_ok_t is not None and (now - self.last_frame_ok_t) < 2.0,
            "confirmed_flash_clear_count": self.confirmed_flash_clear_count,
            "perfect_clear_count": self.perfect_clear_count,
            # totals for the end-of-match summary
            "match_stats": {
                "lines_sent": self.apm.total_lines,
                "pieces": self.queue_tracker.pieces_placed,
                "max_ren": self.max_ren,
                "tetris": self.tetris_count,
                "tspin": self.tspin_count,
                "perfect_clear": self.perfect_clear_count,
            },
            "dismissed_flash_count": self.dismissed_flash_count,
        }


#   Diagnostic evidence (phase3 match-reset investigation): a real play session
#   logged left_non_empty/right_non_empty every check, and the fully-empty window
#   (both sides 0 non-empty cells) was caught in exactly 1 of 2 real match
#   transitions, for exactly ONE 0.5s-spaced check each time — pieces were already
#   back on the board by the very next check. The original EMPTY_CONFIRM_COUNT=3
#   (1.5s sustained) could never be satisfied; the transition is faster than that.
#   Dropped to a single confirmation. This is less of a risk than it sounds: both
#   boards reading empty AT THE SAME INSTANT essentially only happens at a real
#   match boundary — mid-match, even a Perfect Clear only empties the ONE player's
#   own board, never both sides simultaneously — so the "both sides" requirement
#   is itself most of the real debounce.
# Every frame (0.0). The both-boards-empty window between matches can be as
# short as two frames (~0.13s, confirmed on a real recording); sampling every
# 0.2s only caught it by luck, and missing it leaves the old match frozen so
# the next one is never counted. Reading both boards costs ~4.5ms per frame.
EMPTY_CHECK_INTERVAL_S = 0.0
# User's request: a match starts when "ゴー!" disappears, not before. The
# board-empty fallback notices a new match earlier, during the レディ/ゴー
# countdown, so after it resets nothing is counted and the clock stays at 0:00
# until GO! goes away. If GO! is never seen (a stage where the banner color
# check fails), start anyway after this long rather than lose the match.
GO_WAIT_TIMEOUT_S = 8.0
# ...and even then only once the NEXT queues have actually moved this many
# times: the set-end menu (ゲームをつづける / ルールセレクト ...) keeps both
# NEXT queues on screen, full and static, so "8s passed" alone started a
# phantom match there (live bug, 2026-10-29).
GO_TIMEOUT_MIN_QUEUE_ADVANCES = 2
# A real GO! only disappears right after a countdown that began on two empty
# boards: in every recorded match start (8 of 8, five stages) both boards last
# read empty 2.22-2.30s before the GO! edge. The set-end "WINNER!" cut-scene
# has orange artwork that rises and fades in the same center area, but the
# winner's board is still full there, so an edge without empty boards shortly
# before it is ignored.
GO_EMPTY_LOOKBACK_S = 4.0
# The board-empty fallback doesn't end a match this soon after it started:
# both boards are still empty for a moment right after GO!.
START_GRACE_S = 5.0
EMPTY_CONFIRM_COUNT = 1       # consecutive empty confirmations before treating the match as concluded
NONEMPTY_CONFIRM_COUNT = 1     # consecutive non-empty confirmations before treating a new match as started


class MatchPipeline:
    def __init__(self, profile=None, debug_dump_dir=None, gate=None, wait_for_start=False):
        self.profile = profile
        self.debug_dump_dir = debug_dump_dir
        # Recognition only runs while the in-match screen is showing (see
        # gameplay_gate.py). `gate` is injectable so tests driving synthetic
        # frames (which contain no NEXT labels) can supply an always-open one.
        self._gate_injected = gate is not None
        self.gameplay_gate = gate or GameplayGate(profile=profile)
        # Pause handling (user's request: freeze numbers while paused, carry on
        # after resuming). Every timestamp handed to the trackers is "game
        # time": capture time minus all the time spent off the match screen.
        # With no pauses it's identical to capture time, so nothing about the
        # existing APM/clock-anchoring behavior changes; across a pause the
        # hidden stretch simply doesn't exist, so APM and elapsed time don't
        # dilute while paused.
        self._paused = False
        self._paused_offset = 0.0
        self._last_on_screen_t = None
        self._recreate_pipelines()
        self.start_t = None
        self.frame_count = 0
        self._last_fps_t = None
        self._last_fps_count = 0
        self.fps = 0.0
        self._last_t = 0.0
        # Match-end/start detection, a 2-state machine (user's explicit request:
        # freeze the numbers when a match concludes, reset only when the NEXT
        # match actually starts — not immediately on the boards going empty).
        #   ACTIVE: normal operation, both boards non-empty (mid-match).
        #   FROZEN: both boards confirmed empty (match just concluded — the result
        #     screen's board-clear is the only time both boards go fully empty
        #     simultaneously). Frames stop being fed into the trackers and
        #     self._last_t stops advancing, so every derived number (APM, elapsed
        #     time) holds at its final value instead of decaying while the result
        #     screen sits idle. capture_ok naturally stays true through this, since
        #     last_frame_ok_t is frozen at the same instant.
        # FROZEN -> ACTIVE (with a full reset) only once pieces reappear on both
        # boards (debounced), i.e. the next match has actually begun.
        self._frozen = False
        self._last_empty_check_t = None
        self._empty_confirm_streak = 0
        self._nonempty_confirm_streak = 0
        # Confirmed bug: freezing via the victory banner, then immediately having
        # the fallback's "frozen and board is non-empty -> pieces reappeared,
        # reset" check fire on the VERY SAME frame, because right when "やった!"
        # appears the loser's board is still showing its final (non-empty) state
        # — not empty yet. The fallback must only treat "non-empty while frozen"
        # as "a new match started" AFTER it has actually seen both boards empty
        # at least once during this freeze; otherwise it just undoes the freeze
        # it was never supposed to touch.
        self._fallback_saw_empty_since_freeze = False
        # Game time at which the board-empty fallback saw what looks like the
        # next match (boards empty, then filled again) while frozen. Nothing is
        # reset at that point: the last match's numbers stay on screen until
        # the new match is confirmed by GO! (or the timeout + queue movement).
        self._awaiting_go_since = None
        self._last_both_empty_t = None  # last game time both boards read empty
        self._probe_queues = None       # NEXT trackers used only for the GO! timeout
        self._probe_advances = 0
        # wait_for_start (the live server): begin in the frozen state and count
        # nothing until a match is confirmed — by GO! like any match start, or,
        # when started mid-match, by the NEXT queues moving. Live bug: starting
        # the server on the set-end menu ran the clock with nothing happening.
        self._startup_wait = wait_for_start
        self._play_started_t = None  # when GO! (or the queue fallback) started the current match
        if wait_for_start:
            self._frozen = True
        self.match_reset_count = 0
        # Primary match-boundary signal (user's explicit request): freeze the
        # instant "やった!" (victory) appears — that's when the match is actually
        # decided, well before the longer celebration -> board-clear -> GO!
        # sequence finishes — and reset the instant "ゴー!" (GO!) disappears,
        # which is right as the next round's first pieces drop. Validated against
        # a real match boundary: fired exactly once each, at the frames that
        # visually match (see phase3 "GO!/victory banner" notes). The board-empty
        # check above is kept running as a fallback for match endings that don't
        # show these banners (e.g. a draw), not as the primary trigger anymore.
        self.boundary_detector = MatchBoundaryDetector(profile=self.profile or REFERENCE_PROFILE)

    def _recreate_pipelines(self, clock_start_t=None):
        templates = load_templates()
        self.left = PlayerPipeline(side="left", templates=templates, profile=self.profile,
                                    debug_dump_dir=self.debug_dump_dir, clock_start_t=clock_start_t)
        self.right = PlayerPipeline(side="right", templates=templates, profile=self.profile,
                                     debug_dump_dir=self.debug_dump_dir, clock_start_t=clock_start_t)

    def rebuild_for_profile(self, profile):
        """Re-creates both side trackers for a new capture profile (e.g. the game
        window was resized). Match history (APM totals etc.) is intentionally NOT
        carried over — the old trackers' in-flight candidate/streak state refers to
        pixel positions that are no longer valid under the new scale, and silently
        reusing it risks exactly the kind of made-up-looking numbers the project
        rule prohibits. The elapsed-time clock also resets, so the HUD/OBS side
        shows this as a fresh match segment rather than a discontinuity in an old
        one."""
        if self.profile is not None and (
            profile.scale_x == self.profile.scale_x and profile.scale_y == self.profile.scale_y
        ):
            return  # no change
        log.info("capture profile changed (scale %.3f -> %.3f); rebuilding trackers",
                  self.profile.scale_x if self.profile else 1.0, profile.scale_x)
        self.profile = profile
        self._recreate_pipelines()
        self.boundary_detector = MatchBoundaryDetector(profile=profile)
        self._probe_queues = None  # pixel positions changed with the scale
        if not self._gate_injected:
            self.gameplay_gate = GameplayGate(profile=profile)
        self.start_t = None
        self.frame_count = 0

    def reset_match(self, reason="new match detected", clock_start_t=None):
        """Resets APM/event history for a fresh match, keeping the same profile and
        loaded templates (cheaper than rebuild_for_profile, and correct — the
        capture size hasn't changed, only the match has).

        clock_start_t: when the caller knows the PRECISE moment gameplay began
        (the "ゴー!" disappeared edge), pass it so both the displayed elapsed time
        and the APM calculation's own internal clock are anchored exactly there —
        see APMWindowTracker's start_t docstring for why this matters. Left as
        None for the board-empty fallback path, which has no such precise moment
        to offer (less precise by nature, not the primary signal)."""
        log.info("resetting match state (%s)%s", reason,
                  f" clock_start_t={clock_start_t:.2f}" if clock_start_t is not None else "")
        self._recreate_pipelines(clock_start_t=clock_start_t)
        self._awaiting_go_since = None
        self._probe_queues = None
        self._probe_advances = 0
        self._startup_wait = False
        self.start_t = clock_start_t
        self._play_started_t = clock_start_t  # None for a reset with no known start
        self.frame_count = 0
        self.match_reset_count += 1

    def _count_queue_advances(self, frame, t):
        """NEXT-queue shifts on either side this frame (only while a possible
        next match is waiting for GO!)."""
        if self._probe_queues is None:
            return 0
        return sum(len(q.update(frame, t)) for q in self._probe_queues)

    def _start_play(self, t, reason):
        """Ends the "waiting for GO!" countdown: the clock and counting start at t."""
        self._awaiting_go_since = None
        self.start_t = t
        self._play_started_t = t
        self._last_t = t
        self.left.apm.match_start_t = t
        self.right.apm.match_start_t = t
        log.info("match started at t=%.2f (%s)", t, reason)

    def _check_match_boundary(self, frame, t, raw_t=None):
        """Returns True if the match is currently frozen. Primary signal: the
        "やった!"/"ゴー!" banners (see MatchBoundaryDetector) — validated against a
        real match boundary, each fired exactly once at the frame that visually
        matches. Checked every frame (not throttled) since GO! was observed to be
        on screen for well under a second. The board-empty check below runs as a
        throttled FALLBACK for match endings that don't show these banners (e.g. a
        draw), not as the primary trigger."""
        victory_edge, go_disappeared_edge = self.boundary_detector.update(frame, t)
        # The "boards were empty just before GO!" look-back runs on capture
        # time, not game time: the between-match empty boards are often seen
        # while the gate is closed (empty queues), where game time is still
        # missing that closed stretch, so the two clocks don't line up.
        raw = t if raw_t is None else raw_t

        # Board emptiness is read first, so a GO! edge on this very frame can
        # see it. small epsilon so float accumulation can't land a hair under
        # the interval and skip a check it should run.
        both_empty = None
        if (self._last_empty_check_t is None
                or raw - self._last_empty_check_t >= EMPTY_CHECK_INTERVAL_S - 1e-6):
            self._last_empty_check_t = raw
            profile = self.profile or REFERENCE_PROFILE
            # Bright cells only (board_read.board_is_clear): stage art inside
            # the boards must not count as blocks.
            both_empty = (board_is_clear(frame, scale_box(LEFT_BOX, profile))
                          and board_is_clear(frame, scale_box(RIGHT_BOX, profile)))
            if both_empty:
                self._last_both_empty_t = raw

        if victory_edge and not self._frozen:
            self._frozen = True
            self._fallback_saw_empty_since_freeze = False
            log.info("match concluded (victory banner) — freezing numbers")
        if go_disappeared_edge and self._frozen:
            if (self._last_both_empty_t is not None
                    and raw - self._last_both_empty_t <= GO_EMPTY_LOOKBACK_S):
                self._frozen = False
                self._fallback_saw_empty_since_freeze = False
                self.reset_match(reason="GO! disappeared — new match started", clock_start_t=t)
                return False
            log.info("ignored a GO!-like edge at t=%.2f: boards were not empty just before it "
                     "(last both-empty %s) — not a match start",
                     t, "never" if self._last_both_empty_t is None else f"{raw - self._last_both_empty_t:.1f}s earlier")

        if both_empty is not None:
            if not self._frozen:
                # Right after GO! both boards are still empty for a moment;
                # that's the new match starting, not one ending.
                just_started = self._play_started_t is not None and t - self._play_started_t < START_GRACE_S
                if both_empty and not just_started:
                    self._empty_confirm_streak += 1
                    self._nonempty_confirm_streak = 0
                    if self._empty_confirm_streak >= EMPTY_CONFIRM_COUNT:
                        self._frozen = True
                        self._fallback_saw_empty_since_freeze = True  # already true by definition here
                        log.info("match concluded (fallback: both boards empty) — freezing numbers")
                else:
                    self._empty_confirm_streak = 0
            else:
                if both_empty:
                    # Confirms the board genuinely cleared at some point during
                    # this freeze — only AFTER this is "board became non-empty
                    # again" allowed to mean "a new match started" below. Without
                    # this, freezing via the victory banner (loser's board is
                    # still showing its final, non-empty state right then) made
                    # the very next check see "frozen + non-empty" and
                    # immediately undo the freeze it had just set (confirmed bug).
                    self._fallback_saw_empty_since_freeze = True
                    self._nonempty_confirm_streak = 0
                elif self._fallback_saw_empty_since_freeze and self._awaiting_go_since is None:
                    self._nonempty_confirm_streak += 1
                    if self._nonempty_confirm_streak >= NONEMPTY_CONFIRM_COUNT:
                        # Looks like the next match's countdown, but the set-end
                        # cut-scene can look the same, so nothing is reset here:
                        # stay frozen on the last match's numbers until GO!
                        # (above) or the timeout check confirms a new match.
                        self._nonempty_confirm_streak = 0
                        self._awaiting_go_since = t
                        self._probe_queues = (NextQueueTracker("left", self.profile),
                                              NextQueueTracker("right", self.profile))
                        self._probe_advances = 0
                        log.info("possible next match at t=%.2f — waiting for GO!", t)
                # else: still frozen, boards non-empty, but we haven't seen them
                # go empty yet this freeze — this is the expected "loser's board
                # still showing its final state" period; do nothing and wait.

        return self._frozen

    def process_frame(self, frame, t):
        if not self.gameplay_gate.update(frame):
            # Menu, dialog, loading wipe or pause: hold every number where it
            # is, and don't run the board-empty fallback either — on non-board
            # screens it reads artwork as pieces and invents match boundaries.
            # One exception: after a match has ended, the queues also go empty
            # for a moment between matches (same signature as pause), but that
            # IS the board screen, and the empty boards there are exactly what
            # the fallback watches for to notice the next match. The window is
            # only ~2 frames, so it needs every one of them.
            if self._frozen and getattr(self.gameplay_gate, "last_reason", None) == "pause":
                self._check_match_boundary(frame, t - self._paused_offset, raw_t=t)
            if not self._paused:
                self._paused = True
                log.info("match screen not visible (%s) — holding numbers",
                         getattr(self.gameplay_gate, "last_reason", None))
                # Mid-match only (not after a match ended): save what's on
                # screen, so a pause can be confirmed as detected from the dumps.
                if self.debug_dump_dir and not self._frozen:
                    import os
                    os.makedirs(self.debug_dump_dir, exist_ok=True)
                    cv2.imwrite(os.path.join(self.debug_dump_dir, f"gate_closed_t{t:.2f}.png"), frame)
            return
        if self._paused:
            self._paused = False
            if self._last_on_screen_t is not None:
                self._paused_offset += t - self._last_on_screen_t
            log.info("match screen visible again — resuming (%.1fs excluded so far)", self._paused_offset)
        self._last_on_screen_t = t
        raw_t = t
        t = t - self._paused_offset  # game time from here on

        frozen = self._check_match_boundary(frame, t, raw_t=raw_t)
        if frozen and (self._awaiting_go_since is not None or self._startup_wait):
            if self._probe_queues is None:
                self._probe_queues = (NextQueueTracker("left", self.profile),
                                      NextQueueTracker("right", self.profile))
            self._probe_advances += self._count_queue_advances(frame, t)
            # At startup there is no countdown to wait out: a match already in
            # progress shows itself by its queues moving.
            waited = self._startup_wait or t - self._awaiting_go_since >= GO_WAIT_TIMEOUT_S
            if waited and self._probe_advances >= GO_TIMEOUT_MIN_QUEUE_ADVANCES:
                self._frozen = False
                self._fallback_saw_empty_since_freeze = False
                self.reset_match(reason="next match confirmed by NEXT-queue movement")
                self._start_play(t, f"GO! not seen within {GO_WAIT_TIMEOUT_S:.0f}s, "
                                    "but the NEXT queues are moving")
                frozen = False
        if frozen:
            # Hold every derived number at its value from the instant the match
            # concluded: don't feed this frame into the trackers, and don't let
            # self._last_t (the "now" used for the APM/elapsed-time ratio) advance.
            return
        if self.start_t is None:
            self.start_t = t
        # APM shares the displayed clock: with no GO! anchor (e.g. the server
        # started mid-match) it would otherwise start at the first attack, and
        # the overlay's own ATTACK / TIME wouldn't equal the APM shown next to it.
        for side in (self.left, self.right):
            if side.apm.match_start_t is None:
                side.apm.match_start_t = self.start_t
        self.left.process_frame(frame, t)
        self.right.process_frame(frame, t)
        self._last_t = t
        self.frame_count += 1
        now_wall = time.time()
        if self._last_fps_t is None:
            self._last_fps_t = now_wall
        elif now_wall - self._last_fps_t >= 1.0:
            self.fps = (self.frame_count - self._last_fps_count) / (now_wall - self._last_fps_t)
            self._last_fps_t = now_wall
            self._last_fps_count = self.frame_count

    def snapshot(self):
        elapsed = round((self._last_t - self.start_t), 2) if self.start_t is not None else 0
        return {
            "match_elapsed_s": elapsed,
            "match_start_t": self.start_t,  # same clock as event_log "t", for match-relative log times
            "left": self.left.snapshot(self._last_t, elapsed),
            "right": self.right.snapshot(self._last_t, elapsed),
            "recognition": {"fps": round(self.fps, 1), "frame_count": self.frame_count},
            "match_reset_count": self.match_reset_count,
            "frozen": self._frozen and not self._startup_wait,
            "paused": self._paused and not self._frozen,
            # A possible next match is waiting for GO!. The overlays show
            # 試合終了 first while frozen, so on the set-end menu (which can
            # look like a countdown) they never claim a match is starting.
            "waiting_start": self._awaiting_go_since is not None or self._startup_wait,
        }


class VideoReplaySource:
    """Reads a recorded video file, yielding (frame, t) pairs. Used for testing the
    pipeline end-to-end without a live game running."""

    def __init__(self, path, speed=1.0, realtime=True):
        self.cap = cv2.VideoCapture(str(path))
        if not self.cap.isOpened():
            raise RuntimeError(f"cannot open video: {path}")
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.speed = speed
        self.realtime = realtime

    def __iter__(self):
        frame_idx = 0
        wall_start = time.monotonic()
        while True:
            ok, frame = self.cap.read()
            if not ok:
                break
            t = frame_idx / self.fps
            frame_idx += 1
            if self.realtime:
                target_wall = wall_start + t / self.speed
                sleep_s = target_wall - time.monotonic()
                if sleep_s > 0:
                    time.sleep(sleep_s)
            yield frame, t
        self.cap.release()


if __name__ == "__main__":
    import sys
    path = sys.argv[1]
    speed = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0  # fast by default for a quick smoke test
    pipeline = MatchPipeline()
    source = VideoReplaySource(path, speed=speed, realtime=True)
    for frame, t in source:
        pipeline.process_frame(frame, t)
    print("done:", pipeline.snapshot())
