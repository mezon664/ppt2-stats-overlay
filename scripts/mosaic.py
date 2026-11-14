"""縛りプレイ: a mosaic over your own board that gets coarser as one of your
numbers goes up (user's request: tied to APM, B2B ...).

display.challenge_mosaic picks what it's tied to ("off" / "events" / "apm" /
"pps" / "attack" / "b2b" / "ren").

"events" (the first choice; user: TETRIS / T-SPIN make it stronger, doing
none lets it fade): each TETRIS, T-SPIN or PERFECT CLEAR of yours adds
EVENT_STEP, and it fades by itself, from the strongest to none in
EVENT_FADE_S (EventLevel; the server keeps it, it's over time).

A number is at its coarsest when it reaches the top value:
display.challenge_mosaic_max when set (> 0), else
  - apm / pps / attack: your usual — the average over your last USUAL_N
    matches (opener_stats history, the side that was you), so the handicap
    is about the same for a beginner and a strong player (user: a fixed APM
    wouldn't bother an intermediate player); DEFAULT_TOP until USUAL_MIN
    matches are kept
  - b2b / ren: DEFAULT_TOP (a chain comes and goes: no usual to measure)

The server works out the strength (0..1) and, for OBS, the coarse picture
of the board (state["challenge_mosaic"]); the HUD grabs the board itself so
its mosaic has no delay, and uses the server's strength.
"""
import base64

import cv2
import numpy as np

REFERENCE_W = 1232   # capture_profile.REFERENCE_W

METRICS = ("events", "time", "apm", "pps", "attack", "b2b", "ren")
NUMBERS = ("time", "apm", "pps", "attack", "b2b", "ren")   # the ones with a top value
# "time": the match time (state["match_elapsed_s"]): strongest at the seconds
# the user enters (challenge_mosaic_max), growing evenly (user: tie it to time)
EVENT_STEP = 0.25      # four in a row: the strongest
EVENT_FADE_S = 25.0    # from the strongest to none, doing nothing (40 faded too slowly: user)
DEFAULT_TOP = {"time": 120.0, "apm": 60.0, "pps": 1.5, "attack": 40.0, "b2b": 8.0, "ren": 7.0}
USUAL_N, USUAL_MIN = 20, 5
HISTORY_KEY = {"apm": "apm", "pps": "pps", "attack": "lines_sent"}   # opener_stats AVERAGED names
# the mosaic's block, reference px (a cell is 23): from MIN_BLOCK just above
# none to MAX_BLOCK (a little over a cell) at the top value
MIN_BLOCK, MAX_BLOCK = 2.0, 28.0   # (46, two cells, was too strong: user)
# the number's share of the top value, raised to CURVE: slow at first, steep
# near the top (user: it got strong too early)
CURVE = 1.8
# the whole board, the strip above it included (board_read LEFT_BOX / RIGHT_BOX)
BOARD = {"left": (198, 92, 429, 563), "right": (803, 92, 1034, 563)}


def value(state, side, metric):
    """That side's number now (None when not known)."""
    s = (state or {}).get(side) or {}
    if metric == "time":
        v = (state or {}).get("match_elapsed_s")
    elif metric == "apm":
        v = (s.get("apm") or {}).get("apm")
    else:
        v = s.get(metric)
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def usual(matches, n=USUAL_N):
    """Your averages over your last n matches (the side that was you):
    {"apm", "pps", "attack", "matches"}; matches without "you" don't count."""
    mine = [m for m in matches if m.get("you") in ("left", "right")][-n:]
    out = {"matches": len(mine)}
    for metric, key in HISTORY_KEY.items():
        vals = [((m[m["you"]] or {}).get("stats") or {}).get(key) for m in mine]
        vals = [float(v) for v in vals if isinstance(v, (int, float))]
        if vals:
            out[metric] = sum(vals) / len(vals)
    return out


def top_value(display, metric, baseline=None):
    """Where the mosaic is at its coarsest."""
    manual = display.get("challenge_mosaic_max") or 0
    try:
        manual = float(manual)
    except (TypeError, ValueError):
        manual = 0.0
    if manual > 0:
        return manual
    base = baseline or {}
    if metric in HISTORY_KEY and base.get("matches", 0) >= USUAL_MIN and base.get(metric):
        return float(base[metric])
    return DEFAULT_TOP[metric]


def event_count(state, side):
    """That side's TETRIS + T-SPIN + PERFECT CLEAR this match."""
    stats = ((state or {}).get(side) or {}).get("match_stats") or {}
    return max(0, sum(int(stats.get(k) or 0) for k in ("tetris", "tspin", "perfect_clear")))


class EventLevel:
    """For "events": up EVENT_STEP with each TETRIS / T-SPIN / PERFECT CLEAR,
    down over time (EVENT_FADE_S from the strongest to none). A new match
    or another side starts from none; the count first seen is where it
    starts (the app opened mid-match: not all at once)."""

    def __init__(self):
        self.key, self.seen, self.level, self.t = None, None, 0.0, None

    def update(self, state, side, now):
        key = ((state or {}).get("match_start_t"), side)
        count = event_count(state, side)
        if key != self.key:
            self.key, self.seen, self.level, self.t = key, count, 0.0, now
        if self.t is not None:
            self.level = max(0.0, self.level - max(0.0, now - self.t) / EVENT_FADE_S)
        self.t = now
        if count > self.seen:
            self.level += EVENT_STEP * (count - self.seen)
        self.seen = count
        self.level = max(0.0, min(1.0, self.level))
        return self.level


def strength(display, state, side, baseline=None, level=None):
    """0 (none) .. 1 (coarsest) for that side now (level: EventLevel's, for "events")."""
    metric = display.get("challenge_mosaic", "off")
    if metric == "events":
        return max(0.0, min(1.0, level or 0.0))
    if metric not in NUMBERS:
        return 0.0
    v = value(state, side, metric)
    if not v or v <= 0:
        return 0.0
    top = top_value(display, metric, baseline)
    if top <= 0:
        return 0.0
    share = max(0.0, min(1.0, v / top))
    return share if metric == "time" else share ** CURVE   # (time: evenly, so "N s" reads as it is)


def block_px(s):
    """The block size in reference px for strength s (0: no mosaic)."""
    return 0.0 if s <= 0 else MIN_BLOCK + (MAX_BLOCK - MIN_BLOCK) * s


def pixelate(img, block):
    """img (BGR or RGB) as a grid of block x block averages: the small grid
    itself (each cell one pixel), to be drawn scaled up without smoothing."""
    h, w = img.shape[:2]
    gw, gh = max(1, int(round(w / block))), max(1, int(round(h / block)))
    return cv2.resize(img, (gw, gh), interpolation=cv2.INTER_AREA)


def board_picture(frame, box, block_ref, ref_scale):
    """For OBS: the board (box in frame px) as a coarse PNG, base64, and its
    grid size. ref_scale: frame px per reference px."""
    x1, y1, x2, y2 = box
    crop = frame[max(0, y1):y2, max(0, x1):x2]
    if crop.size == 0:
        return None
    small = pixelate(crop, max(1.0, block_ref * ref_scale))
    ok, png = cv2.imencode(".png", small)
    if not ok:
        return None
    return {"png": base64.b64encode(png.tobytes()).decode("ascii"), "w": int(small.shape[1]), "h": int(small.shape[0])}


def challenge_side(display, state):
    """Whose board (as hud/challenge.py challenge_side): display.challenge_side, or yours."""
    side = display.get("challenge_side", "auto")
    if side in ("left", "right"):
        return side
    you = (state or {}).get("you_side")
    return you if you in ("left", "right") else "left"


def state_for(display, state, frame=None, baseline=None, events=None, now=None):
    """state["challenge_mosaic"]: {"side", "strength"} and, for OBS while it
    shows, the coarse board ("png", "w", "h"); None when off or not now."""
    if display.get("challenge_mosaic", "off") not in METRICS or display.get("enabled") is False:
        return None
    st = state or {}
    if st.get("match_screen") is not True or st.get("frozen"):
        return None
    side = challenge_side(display, st)
    if (st.get(side) or {}).get("puyo"):
        return None
    level = None
    if display.get("challenge_mosaic") == "events" and events is not None:
        import time
        level = events.update(st, side, time.monotonic() if now is None else now)
    s = strength(display, st, side, baseline, level)
    out = {"side": side, "strength": round(s, 3)}
    if display.get("challenge_mosaic_style") == "image":
        out["image"] = image_path(display)
        return out   # (the page draws the picture itself, s as its opacity)
    if s > 0 and frame is not None and display.get("show_on_obs") is not False:
        k = frame.shape[1] / REFERENCE_W
        pic = board_picture(frame, scaled_box(side, k), block_px(s), k)
        if pic:
            out.update(pic)
    return out


DEFAULT_IMAGE = "challenge_image/cat.jpg"


def image_path(display):
    """The picture over the board, under assets/: the user's, or the cat."""
    return display.get("challenge_image") or DEFAULT_IMAGE


def cover_rect(img_w, img_h, x, y, w, h):
    """The part of an img_w x img_h picture that fills (x, y, w, h) keeping
    its shape, cut at the edges ("cover"): (sx, sy, sw, sh) in the picture."""
    if img_w <= 0 or img_h <= 0 or w <= 0 or h <= 0:
        return 0, 0, img_w, img_h
    k = max(w / img_w, h / img_h)
    sw, sh = w / k, h / k
    return (img_w - sw) / 2, (img_h - sh) / 2, sw, sh


# The board's cells (reference px): the true grid, 23 px a row, its top
# 11 px below board_read's box top (that box takes in the strip above row 20)
GRID = {"left": (198, 103, 429, 563), "right": (803, 103, 1034, 563)}
ROWS = 20


# as opener_detect.garbage_rows: a block is bright enough over BLOCK_FILL of
# its patch; garbage is grey; a garbage row has every cell but one filled
# GARBAGE_SAT_MAX: 30 in opener_detect; 60 here, as the attack's flash tints
# the grey blocks a little (up to ~45 measured), player blocks are 100 and more
CLEAR_V_MIN, BLOCK_FILL, GARBAGE_SAT_MAX = 120, 0.5, 60


def _cells(img):
    """Each cell of a board picture (row 0 the top): (lit, grey), ROWS x 10."""
    h, w = img.shape[:2]
    cw, ch = w / 10, h / ROWS
    r = max(1, int(min(cw, ch) * 0.13))
    xs = ((np.arange(10) + 0.5) * cw).astype(int)
    ys = ((np.arange(ROWS) + 0.5) * ch).astype(int)
    offs = np.arange(-r, r + 1)
    yy = np.clip(ys[:, None, None, None] + offs[None, None, :, None], 0, h - 1)
    xx = np.clip(xs[None, :, None, None] + offs[None, None, None, :], 0, w - 1)
    patches = img[yy, xx][..., :3]                        # ROWS x 10 x p x p x 3
    hsv = cv2.cvtColor(np.ascontiguousarray(patches.reshape(-1, 1, 3)), cv2.COLOR_BGR2HSV).reshape(patches.shape)
    lit = (hsv[..., 2] >= CLEAR_V_MIN).mean(axis=(2, 3)) >= BLOCK_FILL
    grey = np.median(hsv[..., 1].reshape(ROWS, 10, -1), axis=2) <= GARBAGE_SAT_MAX
    return lit, grey


def stack_height(img):
    """How high the stack is (rows from the bottom with any block, up to the
    first empty one: the falling piece above a gap isn't counted)."""
    lit, _ = _cells(img)
    height = 0
    for row in range(ROWS - 1, -1, -1):
        if not lit[row].any():
            break
        height += 1
    return height


def board_now(frame, side):
    """{"garbage", "height", "grid"} of that side's board in a picture of the game
    (scripts/comments.py); grid: ROWS x 10, True = a block (scripts/midgame.py)."""
    k = frame.shape[1] / REFERENCE_W
    x1, y1, x2, y2 = (int(round(v * k)) for v in GRID[side])
    img = frame[y1:y2, x1:x2]
    return {"garbage": count_garbage(img), "height": stack_height(img), "grid": _cells(img)[0]}


def count_garbage(img, prev=0):
    """Garbage rows at the bottom of a board picture `img` (BGR or BGRA, the
    board's GRID cut out, any size): counted from the bottom up, stopping at
    the first row that isn't one. Only the cells' middles are looked at, so
    it's quick enough for every frame (hud/challenge.py, 60 a second).
    prev: the rows counted before. Below it, a row that looks full (every
    cell lit, nine or more of them grey) is taken as still garbage: an
    attack's flash lights up the hole too (user: the effects fooled it); a
    row that was filled up for real clears within a moment and the rows
    count again then."""
    lit, grey = _cells(img)
    count = 0
    for row in range(ROWS - 1, -1, -1):                  # (row 0 is the top of the picture)
        filled = lit[row]
        n = int(filled.sum())
        garbage = n == 9 and grey[row][filled].all()
        unclear = n == 10 and int(grey[row].sum()) >= 9 and count < prev
        if not (garbage or unclear):
            break
        count += 1
    return count


GARBAGE_DROP_S = 0.5   # fewer garbage rows count only once read that long (a line clear's flash; 0.3 was short for an attack's)


class GarbageHold:
    """The garbage rows to cover: more at once, fewer only after
    GARBAGE_DROP_S (a line clear's flash reads as no garbage for a moment,
    and the holes showed: user)."""

    def __init__(self):
        self.shown, self.lower_since = 0, None

    def update(self, rows, now):
        if rows >= self.shown:
            self.shown, self.lower_since = rows, None
        elif self.lower_since is None:
            self.lower_since = now
        elif now - self.lower_since >= GARBAGE_DROP_S:
            self.shown, self.lower_since = rows, None
        return self.shown


def garbage_state(display, state, frame=None, count=None, hold=None):
    """state["challenge_garbage"]: {"side", "rows"} — that many garbage rows at
    the bottom of the board (count(frame, side): opener_detect.garbage_rows),
    covered on the game screen and in OBS so their holes don't show; None
    when off or not now."""
    if not display.get("challenge_garbage") or display.get("enabled") is False:
        return None
    st = state or {}
    if st.get("match_screen") is not True or st.get("frozen") or frame is None or count is None:
        return None
    side = challenge_side(display, st)
    if (st.get(side) or {}).get("puyo"):
        return None
    rows = int(max(0, min(ROWS, count(frame, side, hold.shown if hold is not None else 0))))
    if hold is not None:
        import time
        rows = hold.update(rows, time.monotonic())
    return {"side": side, "rows": rows}


def scaled_box(side, k):
    """BOARD in px of a picture k times the reference size."""
    return tuple(int(round(v * k)) for v in BOARD[side])
