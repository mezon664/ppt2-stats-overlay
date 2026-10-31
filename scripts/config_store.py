"""Settings persistence: the server, HUD and OBS overlay all read the same file
(config/overlay_settings.json) so their configuration stays in sync.

The "display" block is what users customize (from the HUD's settings window,
or by editing the file). The server re-reads it when the file changes and
sends it with every update, so the HUD and the OBS overlay both follow it
without a restart.
"""
import json
import re
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
    #   "simple" plain square boxes in one color
    #   "frame" / "slash" / "hex" / "meter" / "tower" /
    #   "minimal" / "trend"  the designs added later (hud/overlay.py NEW_STYLES)
    "style": "gauge",            # ミニゲージ (user's choice for the default)
    # Colors (#rrggbb) of the dark boxes and of the main text, in every style
    # (the player-colored parts — pop's pills, gauge bars — keep blue / red).
    "bg_color": "#000000",   # black (user's choice for the default; was navy #0c163c)
    "text_color": "#ffffff",
    # The "minimal" design's lines: its background (no box there), so they get
    # their own color, white to start with (user's request).
    "line_color": "#ffffff",
    # Font for all overlay text: a family name ("" = the system UI font, Yu Gothic UI), and,
    # for a font loaded from a file, that file under assets/user_fonts/ so the
    # OBS page can load it too.
    "font_family": "Meiryo",     # メイリオ (user's choice for the default)
    "font_file": "",
    # how thick the overlay text is, 0 (thin) - 100, set with a slider; 65 is
    # what used to be "bold", 30 what used to be "normal" (see weight_style)
    "text_weight": 65,
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
    # Each player's numbers on their own, on top of offset_x/y (which moves both)
    "stats_left_offset_x": 0,
    "stats_left_offset_y": 0,
    "stats_right_offset_x": 0,
    "stats_right_offset_y": 0,
    # the opener name: both players at once, then each one on its own on top
    # (any opener display; the top-center one moves with "both" only)
    "opener_offset_x": 0,
    "opener_offset_y": 0,
    "opener_left_offset_x": 0,
    "opener_left_offset_y": 0,
    "opener_right_offset_x": 0,
    "opener_right_offset_y": 0,
    "background_opacity": 0.85,  # 0 = no background band
    # Which numbers the stat block shows, top to bottom (any of STAT_ITEMS).
    # Replaces the old show_apm / show_pps / show_app switches (still read, see
    # display_settings).
    "stat_items": ["apm", "pps", "app"],
    # Own wording for a stat's label ({"apm": "火力/分"}); missing = the default.
    "labels": {},
    # The two players' colors (pop pills, gauge bars, accents; text tints follow).
    "player_color_left": "#3b8eea",
    "player_color_right": "#e5484d",
    # Per part overrides of the overall size / colors / background: each part
    # may set scale, bg_color, text_color, background_opacity; anything it
    # doesn't set follows the overall value above, so changing the overall
    # value changes every part that hasn't been given its own.
    "parts": {},
    # False: shown only while a match screen is up (from after character
    # select; hidden again back at the home screen / menus — see
    # live_pipeline.MATCH_SCREEN_HIDE_S). True: always shown.
    "always_show": False,
    # dragging on the game screen moves 1P's and 2P's numbers / opener name
    # separately (off: both together)
    "drag_each_side": False,
    # The tool's on/off switch (top of the settings window, and the tray menu):
    # off hides everything, on the HUD and in OBS. Recognition keeps running,
    # so turning it back on shows the current numbers straight away.
    "enabled": True,
    # Shown off the match screen too, for now (user: switch it on from the
    # home screen with the on/off button). Cleared when a match screen next
    # comes up, so the usual hiding is back after that.
    "force_show": False,
    "show_clock": True,          # match time, above the マッチポイント banner
    "show_event_log": False,     # recent clears / REN breaks above the stats
    "show_summary": True,        # both players' totals between the boards when a match ends
    # which rows the summary shows (any of SUMMARY_ITEMS, always in that order)
    "summary_items": ["opener", "apm", "pps", "app", "lines_sent", "pieces", "max_ren", "tetris", "tspin",
                      "perfect_clear"],
    "show_opener": True,         # show the recognized opener (開幕テンプレ)
    # where: "board"   big over the player's own board, for a few seconds (A)
    #        "hold"    small under the HOLD box, for a few seconds (B)
    #        "namebar" on the player's name bar, for a few seconds (C)
    #        "top"     both players at the top center, for a few seconds (D)
    "opener_display": "board",
    # how long the opener name stays up, seconds; 0 = until the match ends
    "opener_seconds": 4,
    # the opener's name in Japanese or English; "auto" = the same as "language"
    "opener_language": "auto",
    # whose display is shown: "both", "left" (1P only) or "right" (2P only)
    "players": "both",
    "event_log_count": 3,        # 1 - 10 (was 5; user: allow more)
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
    "stats_left_offset_x": (-1232, 1232),
    "stats_left_offset_y": (-692, 692),
    "stats_right_offset_x": (-1232, 1232),
    "stats_right_offset_y": (-692, 692),
    "opener_offset_x": (-1232, 1232),
    "opener_offset_y": (-692, 692),
    "opener_left_offset_x": (-1232, 1232),
    "opener_left_offset_y": (-692, 692),
    "opener_right_offset_x": (-1232, 1232),
    "opener_right_offset_y": (-692, 692),
    "background_opacity": (0.0, 1.0),
    "event_log_count": (1, 10),
    "opener_seconds": (0, 30),
    "text_weight": (0, 100),
}
# text_weight used to be a choice; those values still read as what they looked like
OLD_TEXT_WEIGHTS = {"normal": 30, "bold": 65}
STATS_POSITIONS = ("left", "right")
STYLES = ("band", "pop", "gauge", "text", "versus", "simple",
          # added 2026-10-30 (see hud/overlay.py NEW_STYLES)
          "frame", "slash", "hex", "meter", "tower", "minimal", "trend")
# designs that were renamed: old name -> new
STYLE_RENAMES = {"neon": "frame"}
# allowed values for the text options
LANGUAGES = ("ja", "en")
OPENER_DISPLAYS = ("board", "hold", "namebar", "top", "cat")   # cat: a cat walks over the board holding up the name
PLAYERS = ("both", "left", "right")
OPENER_LANGUAGES = ("auto", "ja", "en")
DISPLAY_CHOICES = {"stats_position": STATS_POSITIONS, "style": STYLES, "language": LANGUAGES,
                   "opener_display": OPENER_DISPLAYS, "players": PLAYERS, "opener_language": OPENER_LANGUAGES}


def opener_language(display):
    """The language opener names are shown in: display.opener_language, or
    the overlay's own language while that's "auto"."""
    lang = display.get("opener_language", "auto")
    return display.get("language", "ja") if lang == "auto" else lang
# free-form text options: the pattern a value must match
COLOR_PATTERN = r"#[0-9a-fA-F]{6}"
DISPLAY_PATTERNS = {"bg_color": COLOR_PATTERN, "text_color": COLOR_PATTERN, "line_color": COLOR_PATTERN,
                    "player_color_left": COLOR_PATTERN, "player_color_right": COLOR_PATTERN,
                    "font_family": r"[^\x00-\x1f]{0,100}",
                    "font_file": r"user_fonts/[^/\\\x00-\x1f]{1,120}\.(ttf|otf|ttc)"}
# What the stat block can show (see stat_items):
#   apm / pps / app  as before; attack = lines sent this match; pieces = pieces placed;
#   ren = the current REN; b2b = the current Back-to-Back chain
STAT_ITEMS = ("apm", "pps", "app", "attack", "pieces", "ren", "b2b")
LABEL_PATTERN = r"[^\x00-\x1f<>]{1,12}"
# What the end-of-match summary can show, top to bottom: tspin = all T-spins;
# tspin_single / _double / _triple / _mini = each kind on its own row
SUMMARY_ITEMS = ("opener", "apm", "pps", "app", "lines_sent", "pieces", "max_ren", "tetris", "tspin",
                 "tspin_single", "tspin_double", "tspin_triple", "tspin_mini", "perfect_clear")
PARTS = ("stats", "clock", "events", "summary", "opener")
PART_KEYS = {"scale": "scale", "background_opacity": "background_opacity",
             "bg_color": "bg_color", "text_color": "text_color", "line_color": "line_color"}   # what a part may override

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
    # Named looks saved from the settings window: {name: display block without "language"}
    "presets": {},
    # Updates (scripts/updater.py): look for a newer release when the app starts.
    "update": {"check_on_start": True},
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
        if key == "style":
            value = STYLE_RENAMES.get(value, value)
        if key == "text_weight" and isinstance(value, str):
            value = OLD_TEXT_WEIGHTS.get(value, default)
        if key == "stat_items":
            display[key] = _stat_items(raw)
        elif key == "labels":
            value = value if isinstance(value, dict) else {}
            display[key] = {k: v for k, v in value.items()
                            if k in STAT_ITEMS and isinstance(v, str) and re.fullmatch(LABEL_PATTERN, v)}
        elif key == "summary_items":
            display[key] = ([k for k in SUMMARY_ITEMS if k in value] if isinstance(value, list)
                            else list(default))
        elif key == "parts":
            display[key] = _parts(value)
        elif isinstance(default, bool):
            display[key] = value if isinstance(value, bool) else default
        elif isinstance(default, (int, float)):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                value = default
            lo, hi = DISPLAY_RANGES.get(key, (value, value))
            value = min(max(value, lo), hi)
            display[key] = int(round(value)) if isinstance(default, int) else float(value)
        elif key in DISPLAY_PATTERNS:
            ok = isinstance(value, str) and (value == "" and key.startswith("font")
                                             or re.fullmatch(DISPLAY_PATTERNS[key], value, re.IGNORECASE))
            display[key] = value if ok else default
        else:
            display[key] = value if value in DISPLAY_CHOICES[key] else default
    return display


def _stat_items(raw):
    """stat_items checked: known items, each once, in the given order. A file
    from before stat_items existed is read from its show_apm/pps/app switches."""
    if "stat_items" not in raw and any(f"show_{k}" in raw for k in ("apm", "pps", "app")):
        return [k for k in ("apm", "pps", "app") if raw.get(f"show_{k}", True) is not False]
    value = raw.get("stat_items", DISPLAY_DEFAULTS["stat_items"])
    if not isinstance(value, list):
        return list(DISPLAY_DEFAULTS["stat_items"])
    out = []
    for k in value:
        if k in STAT_ITEMS and k not in out:
            out.append(k)
    return out


def _parts(value):
    """Per-part overrides checked; a part only keeps the keys it really sets."""
    value = value if isinstance(value, dict) else {}
    out = {}
    for part in PARTS:
        own = value.get(part) if isinstance(value.get(part), dict) else {}
        clean = {}
        for k in PART_KEYS:
            if k not in own:
                continue
            v = own[k]
            if k in ("bg_color", "text_color", "line_color"):
                if isinstance(v, str) and re.fullmatch(COLOR_PATTERN, v):
                    clean[k] = v
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                lo, hi = DISPLAY_RANGES[k]
                clean[k] = float(min(max(v, lo), hi))
        out[part] = clean
    return out


PRESET_FORMAT = "ppt2-stats-overlay-preset"


def preset_of(display):
    """What a preset keeps: the whole look, but not the viewer's language."""
    return {k: v for k, v in display.items() if k != "language"}


def preset_file(name, display):
    """The JSON a preset is shared as."""
    return {"format": PRESET_FORMAT, "version": 1, "name": name, "display": preset_of(display)}


def read_preset_file(data):
    """(name, checked display) from a shared preset file; ValueError if it isn't one.
    A font loaded from a file only works where that file exists (assets/user_fonts/);
    elsewhere the text falls back to the system font."""
    if not isinstance(data, dict) or data.get("format") != PRESET_FORMAT or not isinstance(data.get("display"), dict):
        raise ValueError("not a preset file")
    name = data.get("name") if isinstance(data.get("name"), str) else ""
    name = re.sub(r"[\x00-\x1f]", "", name).strip()[:40] or "preset"
    return name, preset_of(display_settings({"display": data["display"]}))


def part_value(display, part, key):
    """A part's own value for key, else the overall one."""
    return display["parts"].get(part, {}).get(key, display[key])


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
