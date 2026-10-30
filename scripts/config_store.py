"""Settings persistence: the server, HUD and OBS overlay all read the same file
(config/overlay_settings.json) so their configuration stays in sync.

The "display" block is what users customize (from the HUD's settings window,
or by editing the file). The server re-reads it when the file changes and
sends it with every update, so the HUD and the OBS overlay both follow it
without a restart.
"""
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "overlay_settings.json"

# Display options. Offsets are in the game's reference pixels (1232x692
# client area), so they mean the same thing at any window size.
DISPLAY_DEFAULTS = {
    # Look of the APM / PPS display:
    #   "band"   dark band fading out from the board (TETRA-like)
    #   "pop"    rounded badges with a thick white rim, in the player's color
    #   "gauge"  numbers with a thin bar under each
    #   "text"   text only, white with a dark outline like the score
    #   "versus" one block between the boards comparing both players
    "style": "band",
    "text_weight": "bold",       # how thick the overlay text is: "normal" / "bold"
    "text_outline": True,        # black outline around all overlay text
    "language": "ja",           # "ja" / "en": overlay text (states, events) and the settings window
    "stats_position": "left",    # "left": each board's lower-left, "right": lower-right
    "scale": 1.0,                # size of everything shown (0.5 - 2.0)
    "offset_x": 0,               # move the APM / PPS blocks: + = right
    "offset_y": 0,               # + = down
    "clock_offset_x": 0,         # move the match time
    "clock_offset_y": 0,
    "event_offset_x": 0,         # move the event history (it otherwise sits above the stats)
    "event_offset_y": 0,
    "summary_offset_x": 0,       # move the end-of-match summary
    "summary_offset_y": 0,
    "background_opacity": 0.85,  # 0 = no background band
    "show_apm": True,
    "show_pps": True,
    "show_app": True,            # attack per piece (lines sent / pieces placed)
    "show_clock": True,          # match time, above the マッチポイント banner
    "show_event_log": False,     # recent clears / REN breaks above the stats
    "show_summary": True,        # both players' totals between the boards when a match ends
    "show_opener": True,         # show the recognized opener (開幕テンプレ)
    # where: "board"   big over the player's own board, for a few seconds (A)
    #        "hold"    small under the HOLD box, for the rest of the match (B)
    #        "namebar" on the player's name bar, for the rest of the match (C)
    #        "top"     both players at the top center, for the rest of the match (D)
    "opener_display": "board",
    "event_log_count": 3,        # 1 - 5
}

# (min, max) for numeric options; out-of-range values are clamped.
DISPLAY_RANGES = {
    "scale": (0.5, 2.0),
    # Offsets: anywhere on the game screen (reference size 1232x692), so a
    # part can be moved from its default spot to any edge.
    "offset_x": (-1232, 1232),
    "offset_y": (-692, 692),
    "clock_offset_x": (-1232, 1232),
    "clock_offset_y": (-692, 692),
    "event_offset_x": (-1232, 1232),
    "event_offset_y": (-692, 692),
    "summary_offset_x": (-1232, 1232),
    "summary_offset_y": (-692, 692),
    "background_opacity": (0.0, 1.0),
    "event_log_count": (1, 5),
}
STATS_POSITIONS = ("left", "right")
STYLES = ("band", "pop", "gauge", "text", "versus")
# allowed values for the text options
LANGUAGES = ("ja", "en")
OPENER_DISPLAYS = ("board", "hold", "namebar", "top")
TEXT_WEIGHTS = ("normal", "bold")
DISPLAY_CHOICES = {"stats_position": STATS_POSITIONS, "style": STYLES, "language": LANGUAGES,
                   "opener_display": OPENER_DISPLAYS, "text_weight": TEXT_WEIGHTS}

DEFAULTS = {
    "server": {"host": "127.0.0.1", "port": 8765, "broadcast_hz": 10},
    # APM display: total lines sent / elapsed match minutes, a single number (user's
    # explicit decision — see apm_tracker.overall_apm). windows_s is kept only for
    # apm_tracker's internal peak/trend tracking, not for separate on-screen rows.
    "apm_windows_s": [10, 30, 60],
    "display": dict(DISPLAY_DEFAULTS),
    # Developer option: save raw frames around recognition events (banners,
    # clear flashes, pause) to debug_frames/ for investigating misses. Off for
    # users — each frame is ~0.6MB. max_files caps what one run keeps (the
    # oldest files from this run are removed; earlier files are never touched).
    "debug": {"save_frames": False, "max_files": 2000},
    "hud": {
        "visible": True,
        "click_through": True,
        "follow_game": True,                      # cover the game window and follow it
        "position": {"x": 40, "y": 40},          # used only when follow_game is off
        "hide_from_capture": True,                # keep the HUD out of screen captures (see hud/overlay.py)
    },
}


def load_settings():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        return _merge(DEFAULTS, saved)
    save_settings(DEFAULTS)
    return json.loads(json.dumps(DEFAULTS))


def display_settings(settings):
    """The display block with every value checked: unknown or broken values
    fall back to the defaults (or are clamped) instead of breaking the
    overlays — the file may be hand-edited by users."""
    raw = settings.get("display") or {}
    display = dict(DISPLAY_DEFAULTS)
    for key, default in DISPLAY_DEFAULTS.items():
        value = raw.get(key, default)
        if isinstance(default, bool):
            display[key] = value if isinstance(value, bool) else default
        elif isinstance(default, (int, float)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                value = default
            lo, hi = DISPLAY_RANGES.get(key, (value, value))
            value = min(max(value, lo), hi)
            display[key] = int(round(value)) if isinstance(default, int) else float(value)
        else:
            display[key] = value if value in DISPLAY_CHOICES[key] else default
    return display


def save_settings(settings):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    tmp.replace(CONFIG_PATH)  # never leave a half-written file for the server to read


def _merge(defaults, saved):
    out = dict(defaults)
    for k, v in saved.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out
