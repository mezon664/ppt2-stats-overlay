"""Opener usage and win rate over the last few matches (user's request: a pie
chart of how often each opener was used, and each one's win rate, counted
over the most recent N matches — not a running total — updating by itself).

Each finished match (the victory banner seen, so it has a winner) is kept as
one line in config/opener_history.json; only the newest KEEP are kept. The HUD
records them (hud/overlay.py HudWindow.on_state) and the settings window's
「開幕の統計」 tab reads them (hud/settings_window.py).
"""
import json
import time
from pathlib import Path

HISTORY_PATH = Path(__file__).resolve().parent.parent / "config" / "opener_history.json"
KEEP = 500          # matches kept (the most the settings window counts over; user: up to 500)
LAST_N_CHOICES = (10, 20, 50, 100, 200, 500)   # the settings window's "last N" buttons
SIDES = ("left", "right")


def match_record(state, now=None):
    """The line kept for a finished match, from the server's state, or None
    when it isn't one (no time played, nobody won)."""
    if not state.get("frozen") or not (state.get("match_elapsed_s") or 0) > 0:
        return None
    winner = state.get("winner")
    if winner not in SIDES:
        return None
    out = {"t": round(now if now is not None else time.time()), "winner": winner,
           "match_start_t": state.get("match_start_t")}
    for side in SIDES:
        data = state.get(side) or {}
        if data.get("puyo"):
            out[side] = {"puyo": True}     # a Puyo player has no opener
        else:
            out[side] = {"opener": data.get("opener"), "opener_en": data.get("opener_en") or data.get("opener"),
                         "stats": match_numbers(data)}
    return out


# The numbers kept per player per match, averaged over the last N (user: the
# average APM, PPS... of the recent matches too)
AVERAGED = ("apm", "pps", "app", "lines_sent", "pieces", "max_ren", "tetris", "tspin", "perfect_clear")


def match_numbers(data):
    stats = data.get("match_stats") or {}
    out = {"apm": (data.get("apm") or {}).get("apm"), "pps": data.get("pps"), "app": data.get("app")}
    out.update({k: stats.get(k) for k in AVERAGED if k not in out})
    return {k: v for k, v in out.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}


def load(path=None):
    try:
        data = json.loads(Path(path or HISTORY_PATH).read_text(encoding="utf-8"))
        return [m for m in data.get("matches", []) if isinstance(m, dict)]
    except (OSError, ValueError, AttributeError):
        return []


def save(matches, path=None):
    path = Path(path or HISTORY_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"matches": matches[-KEEP:]}, ensure_ascii=False, indent=0), encoding="utf-8")
    tmp.replace(path)


def add(record, path=None):
    """Keeps a finished match. The same match twice (the same start) is kept once."""
    matches = load(path)
    if matches and record.get("match_start_t") is not None and \
            matches[-1].get("match_start_t") == record["match_start_t"] and \
            abs(matches[-1].get("t", 0) - record["t"]) < 600:
        return False
    matches.append(record)
    save(matches, path)
    return True


def clear(path=None):
    save([], path)


OPPONENTS = ("tetris", "puyo", "all")   # against a Tetris player / a Puyo player / either


def plays(match, side, opponent="all"):
    """The sides of this match counted for side "left" / "right" / "both"
    against opponent "tetris" / "puyo" / "all" (a Puyo side has no opener)."""
    out = []
    for sd in (SIDES if side == "both" else (side,)):
        data, other = match.get(sd), match.get("right" if sd == "left" else "left")
        if not isinstance(data, dict) or data.get("puyo"):
            continue
        vs_puyo = isinstance(other, dict) and bool(other.get("puyo"))
        if (opponent == "tetris" and vs_puyo) or (opponent == "puyo" and not vs_puyo):
            continue
        out.append(sd)
    return out


def recent(matches, last_n, side="left", opponent="all"):
    """The newest last_n matches of this kind (side "left" / "right" / "both",
    against opponent "tetris" / "puyo" / "all"), as (match, side) plays."""
    picked = [m for m in matches if plays(m, side, opponent)]
    picked = picked[-last_n:] if last_n > 0 else []
    return [(m, sd) for m in picked for sd in plays(m, side, opponent)], len(picked)


def averages(matches, last_n, side="left", opponent="all"):
    """Each AVERAGED number's average over the same plays as tally (only the
    matches that have it: ones kept before the numbers were, have none)."""
    sums = {}
    for m, sd in recent(matches, last_n, side, opponent)[0]:
        for k, v in (m[sd].get("stats") or {}).items():
            if k in AVERAGED:
                s, n = sums.get(k, (0.0, 0))
                sums[k] = (s + v, n + 1)
    return {k: s / n for k, (s, n) in sums.items() if n}


def tally(matches, last_n, side="left", english=False, opponent="all"):
    """Over the newest last_n matches of this kind — side "left" / "right" /
    "both", against opponent "tetris" / "puyo" / "all" (user: see them
    apart) — rows (name, used, won), most used first, None = no opener
    recognized; the number of plays counted; and the number of matches."""
    picks, picked = recent(matches, last_n, side, opponent)
    rows, total = {}, 0
    for m, sd in picks:
        data = m[sd]
        name = (english and data.get("opener_en")) or data.get("opener") or None
        used, won = rows.get(name, (0, 0))
        rows[name] = (used + 1, won + (m.get("winner") == sd))
        total += 1
    ordered = sorted(rows.items(), key=lambda kv: (kv[0] is None, -kv[1][0], kv[0] or ""))
    return [(name, used, won) for name, (used, won) in ordered], total, picked
