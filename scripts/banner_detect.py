"""Attack-banner recognition via template matching, with fade-aware dedup and
multi-banner merging into single attack events.

Coverage note (be explicit about what is and isn't supported — do not silently
mis-classify what we haven't actually seen in footage):
  - Confirmed templates: TETRIS (clear_4), T-SPIN Single/Double/Triple, T-SPIN Mini
    (with and without a line), BACK TO BACK, PERFECT CLEAR, REN counter (presence;
    digit reading only calibrated for "1" and "2" so far).
  - Plain Single/Double/Triple show no banner at all (they come from the clear flash).
"""
import glob
import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from attack_calc import load_table, AttackStreakTracker, is_b2b_eligible
from capture_profile import CaptureProfile, compute_profile, scale_box, scale_template, REFERENCE_PROFILE

# TEMPLATES' "file"/"file_right" entries are written relative to this file's own
# directory (scripts/), not the process's working directory — resolved in
# load_templates(). Without this, running from anywhere other than scripts/
# (e.g. pytest from the project root) silently loads None images that only blow
# up later, inside match_one(), far from the real cause.
SCRIPTS_DIR = Path(__file__).resolve().parent

# Templates are tied to one specific recording's resolution/UI skin. The game has
# re-skinned the badge artwork and moved some elements between recordings (confirmed:
# T-SPIN/BACK-TO-BACK stayed in the same bottom-left-of-own-side slot across both
# recordings seen so far; REN's position did NOT — center-ish in recording B vs
# fixed left-side in recording A — so REN is left out here pending recalibration;
# TETRIS renders centered on the cleared rows INSIDE the stack, not a fixed badge
# slot, so its window spans the full playfield height rather than one fixed band).
#
# Active set: samples/PuyoPuyoTetris2 2026-06-07 00-26-52.mp4 (1232x692).
RIGHT_X_OFFSET = 803 - 198

TEMPLATES = {
    # Recalibrated (current live theme) from fresh debug-dump frames after the
    # original template (a completely different bold rainbow-badge art style from
    # an older recording/theme) was confirmed to score only ~0.19 against a real,
    # clearly-visible "TETRIS" banner on screen — same per-theme mismatch class as
    # the earlier T-SPIN/BACK-TO-BACK fixes. Needed a SEPARATE right-side crop
    # (not just a mirrored window) like back_to_back: the single left-sourced
    # template only reached ~0.56 at best on the right side's own TETRIS banner.
    "tetris": {
        "file": "../assets/templates/t_tetris_left_v2.png",
        "file_right": "../assets/templates/t_tetris_right_v2.png",
        "window": (190, 90, 435, 565), "side_native": "left",
    },
    # NOTE: templates deliberately crop ONLY the variant word, not shared artwork —
    # see EXCLUSIVE_GROUPS below; this was a confirmed bug source in recording A, and
    # was ALSO present here until fixed (the full-badge tspin_double template matched
    # a real "T-SPIN Single" banner at 0.923 confidence — confirmed via user-supplied
    # ground truth at abs t=16.27s in dense2a, see phase2d notes).
    # Root cause of the live-capture T-SPIN miss, found via debug frame dumps (see
    # BannerTracker.debug_dump_dir): the word-crop templates included background
    # pixels in the ribbon badge's corner triangles. The recording used to build
    # them has an ice/crystal stage background; the live practice session used a
    # different (warm/orange) stage background — same badge, same text, different
    # background behind its corners, which was enough to drag TM_CCOEFF_NORMED's
    # score down to ~0.50 even at the best possible alignment (confirmed by
    # searching the ENTIRE live frame, not just this window — ruled out a
    # window/position bug). Window widening alone (previous fix attempt) couldn't
    # have fixed this, and didn't. Cropping tight enough to exclude the corner
    # background entirely (just the letters) recovered 0.75+ on the same live
    # frame that scored 0.50 before. Window kept wide regardless, since a tighter
    # template still benefits from search margin.
    "tspin_double": {"file": "../assets/templates/t_tsd_tight.png", "window": (15, 395, 240, 535), "side_native": "left"},
    "tspin_single": {"file": "../assets/templates/t_tss_tight.png", "window": (15, 395, 240, 535), "side_native": "left"},
    # Same badge, word "Triple" — cut the same way (40x16, word only) from a live
    # frame of a real left-side T-SPIN Triple (debug dump at t=138.86, current theme).
    "tspin_triple": {"file": "../assets/templates/t_tst_tight.png", "window": (15, 395, 240, 535), "side_native": "left"},
    # T-SPIN Mini: the same badge, smaller, with a yellow "Mini" on a navy tab
    # at its left — "Mini T-SPIN" with no line cleared, "Mini T-SPIN Single"
    # with one. The template is that yellow word (29x15, on the badge's own navy,
    # so the stage behind doesn't matter), cut from burst_tsm (t=15.05, left).
    # Measured: 0.76-0.96 on all 4 real Minis (3 with a line incl. one by the 2P
    # CPU in burst_boundary, 1 without), at most 0.52 on every other frame of
    # every recording.
    "tspin_mini": {"file": "../assets/templates/t_tspin_mini_word.png", "window": (15, 395, 240, 535), "side_native": "left"},
    # The small "Single" under a Mini badge, only read when "Mini" first shows
    # up, to tell the two kinds apart (see MINI_SINGLE_THRESHOLD). Not a
    # clear-type label on its own.
    "tspin_mini_single": {"file": "../assets/templates/t_tspin_mini_single.png", "window": (15, 395, 240, 535), "side_native": "left"},
    # A T-SPIN that cleared no line: the badge says only "T-SPIN", on a shorter
    # ribbon than the Single / Double / Triple ones. The template is its
    # "-SPIN" letters (48x17, on the badge's own navy), cut from burst_tspin_zero
    # (t=2.59, left). Measured: 0.94-0.97 while either of the 2 real ones was
    # up (0.65 on the first fade-in frame), at most 0.66 on every frame of
    # every other recording (incl. the T-SPIN Single / Double / Triple / Mini
    # badges, where its letters sit differently). Right side not yet seen on
    # a recording. Not a clear: see TSPIN_ZERO_THRESHOLD / tspin_no_line_events.
    "tspin_zero": {"file": "../assets/templates/t_tspin_zero_word.png", "window": (15, 395, 240, 535), "side_native": "left"},
    # Tighter text-only crop (just "BACK", not the blue ribbon) — the full-ribbon
    # template's background noise floor (~0.86 from icy decorative cubes, which are
    # also blue) overlapped with genuine faint-pulse confidence (~0.56-0.97), so NO
    # threshold could separate them (confirmed false "continuously active" bug via
    # user-supplied ground truth: first T-SPIN Double at abs t=8.87s was reported
    # btb=True but should have been False). The tighter crop widens the gap to
    # background~0.81 vs genuine~0.93+ — see per-label thresholds below.
    # Window widened vertically after checking the right side (badge sits ~15-45px
    # higher there than the left crop suggested). That alone wasn't enough, though:
    # even with the wider window, the right side topped out at ~0.40 confidence
    # (vs 0.90+ threshold) using the LEFT-side template image — confirmed by direct
    # frame inspection this is a genuine "BACK to BACK" badge, just not a good enough
    # pixel match against a template sourced from the other side (unlike T-SPIN/TETRIS,
    # mirroring the template image itself, not just its window, was insufficient here).
    # So back_to_back has its own per-side template image, loaded via "file_right".
    "back_to_back": {
        "file": "../assets/templates/t_b2b_word.png",
        "file_right": "../assets/templates/t_b2b_right_word2.png",
        # x1 widened from 40 to 15: the right-side badge's left edge fell just
        # outside the mirrored window (abs x=625 vs window start 645), truncating it
        # and capping confidence at ~0.41 regardless of template quality (confirmed
        # via self-match sanity check — the template matches perfectly at 1.0
        # elsewhere, just not within the too-narrow window). Widened for both sides.
        "window": (15, 470, 220, 575), "side_native": "left",
    },
    # "PERFECT CLEAR" (orange/white), shown over the upper part of the player's
    # own board for ~1.3s right after the clear. Cut from a real left-side
    # perfect clear (burst_pc f_0178, live 1245px frame resized to reference
    # scale); the text sat at reference x 212-416, y 221-320. Not a clear-type
    # banner: it marks the clear that just happened as a perfect clear (see
    # PlayerPipeline), so it isn't in RAW_CLEAR_LABELS.
    "perfect_clear": {
        "file": "../assets/templates/t_perfect_clear.png",
        "window": (190, 170, 440, 380), "side_native": "left",
    },
}

# REN digit templates. IMPORTANT, re-confirmed caveat (phase3 "REN miscount"
# investigation): the templates below (ren_digit_1..6) and REN_WINDOW_RIGHT_CONFIRMED
# were calibrated against the OLDER recorded video (overview2, a different game
# theme/session than the live game now). A live burst capture from the CURRENT
# session found the left player's real "1 REN" badge at a DIFFERENT position with a
# DIFFERENT visual style (confirmed by direct test: the old ren_digit_1 template
# scored only 0.475 against it, the new one scores 1.0) — the same
# per-theme/per-session recalibration problem that hit T-SPIN/BACK-TO-BACK earlier.
# Only digit "1" has been recalibrated for the CURRENT live theme so far (left
# side only); digits 2-6 for the left side, and the entire right-side set for the
# CURRENT theme, remain UNCONFIRMED — the ren_digit_*.png / REN_WINDOW_RIGHT_CONFIRMED
# values below are carried over from the older video and likely need the same fix
# once more combo footage from the current theme is available.
REN_WINDOW_LEFT_CONFIRMED = (59, 376, 257, 455)  # live-capture-confirmed, current theme, digit "1" only
REN_WINDOW_RIGHT_CONFIRMED = (655, 385, 795, 435)  # from the OLDER recording — unconfirmed for the current theme
REN_TEMPLATES = {
    f"ren_{d}": {"file": f"../assets/templates/ren_digit_{d}.png", "window": REN_WINDOW_LEFT_CONFIRMED, "side_native": "left"}
    for d in range(1, 7)
}
# Override just digit 1 on the left with the current-theme-confirmed template —
# the other digits still fall back to the (unconfirmed-for-this-theme) old image,
# which is honest: better to try and possibly miss than to fabricate a template.
REN_TEMPLATES["ren_1"]["file"] = "../assets/templates/ren_left_digit_1.png"
TEMPLATES.update(REN_TEMPLATES)
REN_LABELS = set(REN_TEMPLATES.keys())

REN_SUPPORTED = True

# Labels that share the same on-screen slot and are mutually exclusive (only one can
# be the "real" banner at a time). Without this, e.g. tspin_double/tspin_triple or
# ren_1/ren_2 both cross normalized-cross-correlation's threshold on the same frame
# (confirmed bug during testing — see phase2c notes) because most of each badge's
# pixels are shared artwork. Within a group, only the single highest-scoring label
# per frame is allowed to count as a candidate match.
EXCLUSIVE_GROUPS = [
    {"tspin_double", "tspin_single", "tspin_triple", "tspin_mini"},
    set(REN_LABELS),
]

ENTER_THRESHOLD = 0.70
EXIT_THRESHOLD = 0.55
EXIT_GRACE_FRAMES = 2  # consecutive below-exit frames before declaring "ended" (survives fade dips)

# Per-label overrides where the generic 0.70/0.55 pair doesn't fit the evidence:
#  - back_to_back: background noise floor ~0.81 vs genuine ~0.93+ (word-only template).
#  - tetris: best achievable match on a confirmed-genuine instance was only 0.679
#    (position/scale varies with stack height — see phase2d notes), while background
#    frames stayed under ~0.47, so 0.70 was too strict and caused a confirmed miss.
ENTER_THRESHOLDS = {"back_to_back": 0.90, "tetris": 0.60, "tspin_zero": 0.85}
EXIT_THRESHOLDS = {"back_to_back": 0.85, "tetris": 0.50, "tspin_zero": 0.70}
# tspin_zero only counts when none of the line-clearing T-SPIN words is there
# (they peaked at 0.33-0.41 on the real no-line badges; a real word is 0.7+).
TSPIN_ZERO_WORD_MAX = 0.6
TSPIN_WORDS = ("tspin_single", "tspin_double", "tspin_triple", "tspin_mini")

# back_to_back's pulse-to-pulse gap was measured at up to ~2.8s in this recording
# (peaks at rel t=6.2, 7.73, 10.53, 12.47s), so the default 2-frame (~0.13s) grace
# treated each pulse as a separate blip and ended the "active" streak between every
# pulse — meaning the live b2b-state lookup read False at every subsequent clear
# event (confirmed bug: events 2-4 in the user's ground truth all have btb=True but
# were detected as False). 45 frames (~3s at 15fps) bridges the measured gaps.
EXIT_GRACE_FRAMES_OVERRIDES = {"back_to_back": 45}

RAW_CLEAR_LABELS = {"tetris", "tspin_double", "tspin_single", "tspin_triple", "tspin_mini"}  # mutually-exclusive clear-type banners
CLEAR_TYPE_MAP = {"tetris": "clear_4", "tspin_double": "tspin_double", "tspin_single": "tspin_single",
                  "tspin_triple": "tspin_triple", "tspin_mini": "tspin_mini"}
# When "Mini" first crosses its threshold, the small "Single" under it scored
# 0.64-0.88 on the 3 real Minis with a line and 0.33-0.36 on the one without
# (same frame, fade-in included). Below this it's a Mini with no line: not a
# clear (no attack, no REN/BtB change), reported in mini_no_line_events instead.
MINI_SINGLE_THRESHOLD = 0.5

MERGE_WINDOW_S = 0.5  # banners starting within this many seconds of each other -> one attack event


def load_templates():
    out = {}
    for label, cfg in TEMPLATES.items():
        path = SCRIPTS_DIR / cfg["file"]
        img = cv2.imread(str(path))
        if img is None:
            raise FileNotFoundError(f"template image for '{label}' not found or unreadable: {path}")
        if "file_right" in cfg:
            path_right = SCRIPTS_DIR / cfg["file_right"]
            img_right = cv2.imread(str(path_right))
            if img_right is None:
                raise FileNotFoundError(f"template image for '{label}' (right) not found or unreadable: {path_right}")
        else:
            img_right = img
        out[label] = {**cfg, "img": img, "img_right": img_right}
    return out


def template_for_side(cfg, side):
    return cfg["img_right"] if side == "right" else cfg["img"]


def window_for_side(label, window, side):
    if label in REN_LABELS:
        # REN does not follow the fixed per-side offset — see REN_WINDOW_* above.
        return REN_WINDOW_RIGHT_CONFIRMED if side == "right" else REN_WINDOW_LEFT_CONFIRMED
    x1, y1, x2, y2 = window
    if side == "right":
        return (x1 + RIGHT_X_OFFSET, y1, x2 + RIGHT_X_OFFSET, y2)
    return (x1, y1, x2, y2)


def match_one(frame, tmpl_img, window):
    x1, y1, x2, y2 = window
    region = frame[y1:y2, x1:x2]
    th, tw = tmpl_img.shape[:2]
    if region.shape[0] < th or region.shape[1] < tw:
        return 0.0, (x1, y1)
    res = cv2.matchTemplate(region, tmpl_img, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    return max_val, (x1 + max_loc[0], y1 + max_loc[1])


@dataclass
class LabelState:
    active: bool = False
    below_exit_run: int = 0
    start_t: float = None
    best_conf: float = 0.0
    best_pos: tuple = None


class BannerTracker:
    """Runs template matching + hysteresis dedup for one side (left/right).

    BACK TO BACK is a continuing *state* that pulses (fades in/out repeatedly) for as
    long as the streak lasts, not a one-shot flash per attack — confirmed by direct
    frame inspection: its per-frame confidence dips as low as 0.56 between pulses
    while the badge is still genuinely (faintly) on screen, and separate clear-type
    events (e.g. multiple T-SPIN Doubles) can occur well after BtB's own start time
    while it's still active. An earlier version of this tracker only attached btb=True
    to a clear event if a back_to_back *banner_event* started within MERGE_WINDOW_S of
    it — which silently produced btb=False for every clear after the first one in a
    streak (confirmed bug, see phase2c test notes). Fixed by tracking b2b as live
    state and attaching it to a clear event the instant that clear is first seen,
    rather than post-hoc matching banner start times.
    """

    def __init__(self, side, templates, profile=None, debug_dump_dir=None, debug_dump_labels=None, debug_dump_threshold=0.35):
        self.side = side
        self.templates = templates
        # profile=None means "use the reference resolution as-is" (identity scale),
        # which is what every offline test in this project ran against — passing a
        # live-capture profile here is what makes recognition follow a resized game
        # window instead of staying pinned to the 1232x692 reference coordinates.
        self.profile = profile or REFERENCE_PROFILE
        self.states = {label: LabelState() for label in templates}
        self.match_log = []     # every raw per-frame match: (t, label, conf, pos)
        self.banner_events = []  # deduped single events: (start_t, end_t, label, best_conf)
        self.attack_events = []  # resolved, in order
        self.mini_no_line_events = []  # times of a T-SPIN Mini that cleared no line (not attacks)
        self.tspin_no_line_events = []  # times of a T-SPIN (not Mini) that cleared no line (not attacks)
        # label -> game time until which that clear's banner is already accounted
        # for (the pipeline counted it from its flash; see expect_banner)
        self._expected_banners = {}
        self.attack_table = load_table()
        self.streak = AttackStreakTracker()
        self.btb_mismatch_log = []  # (t, badge_said, streak_said) — diagnostic only
        self.ren_mismatch_log = []  # (t, screen_ren, estimated_ren) — diagnostic only
        # Live-capture T-SPIN miss investigation (phase3): dumps the raw frame to
        # disk whenever a watched label's confidence rises above debug_dump_threshold
        # (below the real ENTER threshold — catches a "something is there but not
        # confident enough" case), so a live frame from the exact moment can be
        # inspected directly instead of guessing from periodic unrelated samples.
        self.debug_dump_dir = debug_dump_dir
        self.debug_dump_labels = debug_dump_labels or set()
        self.debug_dump_threshold = debug_dump_threshold
        self._debug_dump_cooldown_until = 0.0
        self._last_dump_hits = None

    def expect_banner(self, label, until_t):
        """The clear this banner belongs to was already counted (the pipeline
        counts a 4-line flash as a TETRIS right away): the next such banner up
        to until_t is not counted again."""
        self._expected_banners[label] = until_t

    def _current_screen_ren(self):
        """Currently-active REN digit per the on-screen badge, or None if no digit
        badge is currently showing (combo not active, or digit not recognized —
        these two cases are NOT distinguished here; see REN_TEMPLATES caveat)."""
        for label in REN_LABELS:
            if self.states.get(label, LabelState()).active:
                return int(label.split("_")[1])
        return None

    def update(self, frame, t):
        raw_scores = {}
        raw_pos = {}
        for label, cfg in self.templates.items():
            window = scale_box(window_for_side(label, cfg["window"], self.side), self.profile)
            tmpl_img = scale_template(template_for_side(cfg, self.side), self.profile)
            conf, pos = match_one(frame, tmpl_img, window)
            raw_scores[label] = conf
            raw_pos[label] = pos
            self.match_log.append((round(t, 2), label, round(float(conf), 3), pos))

        if (self.debug_dump_dir and t >= self._debug_dump_cooldown_until
                and any(raw_scores.get(l, 0) >= self.debug_dump_threshold for l in self.debug_dump_labels)):
            hits = {l: round(float(raw_scores[l]), 2) for l in self.debug_dump_labels
                    if raw_scores.get(l, 0) >= self.debug_dump_threshold}
            # A static screen (e.g. a menu) scores the same every frame: saving
            # it once a second filled ~10GB. Only save when the scores change.
            if hits != self._last_dump_hits:
                import os
                os.makedirs(self.debug_dump_dir, exist_ok=True)
                fname = f"{self.side}_t{t:.2f}_" + "_".join(f"{l}{s:.2f}" for l, s in hits.items()) + ".png"
                cv2.imwrite(os.path.join(self.debug_dump_dir, fname), frame)
                self._last_dump_hits = hits
            self._debug_dump_cooldown_until = t + 1.0  # avoid dumping every frame of the same event

        # suppress all but the per-frame winner within each exclusive group
        effective_scores = dict(raw_scores)
        for group in EXCLUSIVE_GROUPS:
            present = [l for l in group if l in effective_scores]
            if not present:
                continue
            winner = max(present, key=lambda l: effective_scores[l])
            for l in present:
                if l != winner:
                    effective_scores[l] = 0.0

        for label, cfg in self.templates.items():
            conf = effective_scores[label]
            pos = raw_pos[label]
            st = self.states[label]
            enter_th = ENTER_THRESHOLDS.get(label, ENTER_THRESHOLD)
            exit_th = EXIT_THRESHOLDS.get(label, EXIT_THRESHOLD)
            exit_grace = EXIT_GRACE_FRAMES_OVERRIDES.get(label, EXIT_GRACE_FRAMES)
            if not st.active:
                if conf >= enter_th:
                    st.active = True
                    st.start_t = t
                    st.best_conf = conf
                    st.best_pos = pos
                    st.below_exit_run = 0
                    if label == "tspin_mini" and raw_scores.get("tspin_mini_single", 0.0) < MINI_SINGLE_THRESHOLD:
                        self.mini_no_line_events.append(round(t, 2))
                    elif label == "tspin_zero":
                        if all(raw_scores.get(w, 0.0) < TSPIN_ZERO_WORD_MAX and not self.states[w].active
                               for w in TSPIN_WORDS if w in self.states):
                            self.tspin_no_line_events.append(round(t, 2))
                    elif label in RAW_CLEAR_LABELS and t <= self._expected_banners.get(label, -1.0):
                        del self._expected_banners[label]   # already counted from its flash
                    elif label in RAW_CLEAR_LABELS:
                        clear_type = CLEAR_TYPE_MAP[label]
                        # BtB is derived from our OWN count of consecutive eligible
                        # clear banners, not from the B2B badge's live visual state.
                        # The badge is a *reaction* to the clear that just happened,
                        # so reading its on-screen state at the instant a clear is
                        # first detected is structurally one event too late for the
                        # clear that extends the streak to 2 (confirmed bug: user's
                        # ground-truth event 2 — second consecutive T-SPIN Double —
                        # should have btb=True but badge-state read False because the
                        # badge hadn't visually appeared yet at that exact frame; see
                        # phase2d notes). The badge is still logged for cross-checking.
                        ren_count, b2b_streak = self.streak.register_clear(self.attack_table, clear_type)
                        btb = is_b2b_eligible(self.attack_table, clear_type) and \
                            b2b_streak >= self.attack_table["back_to_back"]["min_consecutive_for_bonus"]
                        badge_said = self.states.get("back_to_back", LabelState()).active
                        if badge_said != btb:
                            self.btb_mismatch_log.append((round(t, 2), badge_said, btb))

                        # REN: prefer the on-screen digit when one is currently
                        # showing; the streak-count estimate is the fallback and is
                        # always computed regardless, so the source actually used is
                        # always recorded (requirement: never treat an unread value
                        # as confirmed). A mismatch is EXPECTED sometimes, not
                        # necessarily a bug: the badge can lag the event that just
                        # extended the combo by one frame-update, same as BACK TO
                        # BACK (see phase2d notes) — logged for later inspection
                        # either way, not silently resolved.
                        screen_ren = self._current_screen_ren()
                        if screen_ren is not None:
                            ren_value, ren_source = screen_ren, "screen"
                        else:
                            ren_value, ren_source = ren_count, "estimated"
                        if screen_ren is not None and screen_ren != ren_count:
                            self.ren_mismatch_log.append((round(t, 2), screen_ren, ren_count))

                        self.attack_events.append({
                            "t": round(t, 2),
                            "clear_type": clear_type,
                            "btb": btb,
                            "ren_count": ren_value,
                            "ren_source": ren_source,       # "screen" or "estimated"
                            "ren_estimated": ren_count,      # always available for comparison
                            "raw_label": label,
                        })
            else:
                st.best_conf = max(st.best_conf, conf)
                if conf < exit_th:
                    st.below_exit_run += 1
                    if st.below_exit_run >= exit_grace:
                        self.banner_events.append((round(st.start_t, 2), round(t, 2), label, round(float(st.best_conf), 3)))
                        self.states[label] = LabelState()
                else:
                    st.below_exit_run = 0

    def finalize(self, t_end):
        for label, st in self.states.items():
            if st.active:
                self.banner_events.append((round(st.start_t, 2), round(t_end, 2), label, round(float(st.best_conf), 3)))
        self.states = {label: LabelState() for label in self.templates}


def merge_into_attack_events(banner_events):
    """Group co-occurring banners (e.g. T-SPIN Triple + BACK TO BACK) that start within
    MERGE_WINDOW_S of each other into a single attack event, so they are never counted
    as two separate attacks."""
    events = sorted(banner_events, key=lambda e: e[0])
    groups = []
    for ev in events:
        start_t, end_t, label, conf = ev
        placed = False
        for g in groups:
            if abs(g["start_t"] - start_t) <= MERGE_WINDOW_S:
                g["labels"].append(ev)
                g["start_t"] = min(g["start_t"], start_t)
                placed = True
                break
        if not placed:
            groups.append({"start_t": start_t, "labels": [ev]})

    attack_events = []
    for g in groups:
        labels = [l[2] for l in g["labels"]]
        clear_labels = [l for l in labels if l in RAW_CLEAR_LABELS]
        btb = "back_to_back" in labels
        ren_labels = [l for l in labels if l.startswith("ren_")]

        if len(clear_labels) == 0:
            # a REN/BtB banner with no recognized clear-type banner alongside it —
            # cannot resolve what was actually cleared; log, don't guess.
            attack_events.append({
                "t": g["start_t"], "clear_type": None, "btb": btb,
                "ren_digit": ren_labels, "unresolved": True,
                "raw_labels": labels,
            })
            continue

        if len(clear_labels) > 1:
            # two mutually-exclusive clear-type banners in the same merge window:
            # ambiguous, don't silently pick one.
            attack_events.append({
                "t": g["start_t"], "clear_type": None, "btb": btb,
                "ren_digit": ren_labels, "unresolved": True,
                "raw_labels": labels, "note": "multiple clear-type banners merged, ambiguous",
            })
            continue

        clear_type = CLEAR_TYPE_MAP[clear_labels[0]]
        ren_digit = None
        if ren_labels:
            vals = [int(l.split("_")[1]) for l in ren_labels if l.split("_")[1].isdigit()]
            ren_digit = vals[0] if vals else None

        attack_events.append({
            "t": g["start_t"], "clear_type": clear_type, "btb": btb,
            "ren_digit": ren_digit, "unresolved": False,
            "raw_labels": labels,
        })
    return attack_events


def run_on_frames(frame_glob, fps, side):
    templates = load_templates()
    files = sorted(glob.glob(frame_glob))
    tracker = BannerTracker(side, templates)
    for i, f in enumerate(files):
        img = cv2.imread(f)
        tracker.update(img, i / fps)
    tracker.finalize(len(files) / fps)
    return tracker


if __name__ == "__main__":
    import sys
    frame_glob, fps, side = sys.argv[1], float(sys.argv[2]), sys.argv[3]
    tracker = run_on_frames(frame_glob, fps, side)
    print(f"=== banner events ({side}) ===")
    for e in sorted(tracker.banner_events):
        print(e)
    print(f"\n=== attack events (btb from streak count, not badge state) ===")
    for e in tracker.attack_events:
        print(e)
    print(f"\n=== badge-vs-streak BtB mismatches (diagnostic, {len(tracker.btb_mismatch_log)}) ===")
    for t, badge, streak in tracker.btb_mismatch_log:
        print(f"  t={t}: badge said {badge}, streak-count said {streak}")
