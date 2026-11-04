"""Cuts the cat out of the user's clip for the 「猫」 opener display (a green
screen, or a black background — the user's second clip is DNxHR with its
alpha channel, which ffmpeg can't decode yet, shown on black):
a cat walks in, holds up a sheet of paper (the opener name is drawn on it at
run time), and walks off.

Writes assets/cat/: f_NNN.webp (each frame cropped to the cat, transparent
around it) and cat.json (per frame: where the crop sits in the full picture,
and the paper's four corners when it's held up facing us).

    python tools/cat/make_cat.py "C:\\path\\cat temple.mp4"
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "cat"
STEP = 1          # every frame: 24 fps (12 looked choppy; user)
OUT_W = 1280      # the clip is shrunk to this width (1920x1080 -> 1280x720). It was 640: shown
                  # at 1.8x on a 1756-wide game it looked blurry (user). The HUD's CAT_SCALE
                  # turns these pixels into reference px (0.625: 1280 px = 800 ref px)
SCALE = 0.5       # set from the clip's width in main()


BG_BGR = np.array([57, 178, 24], np.float32)   # the green screen: measured per clip (calibrate_green)
KEY_LO, KEY_HI = 30, 95   # greenness (G - max(R, B)): <= LO is the cat, >= HI the screen (per clip too)


def calibrate_green(frame):
    """The screen's colour and how green it is, from the first frame. Clips differ: the third one's
    green is paler and uneven (greenness 80-99, the floor shadow 74-80), where
    the first's was 95+; fixed values left a faint green veil."""
    global BG_BGR, KEY_LO, KEY_HI
    px = frame.reshape(-1, 3).astype(np.float32)          # the first frame: the screen, the cat just a sliver
    greenness = px[:, 1] - np.maximum(px[:, 0], px[:, 2])
    screen = px[greenness > 40]
    BG_BGR = np.median(screen, axis=0)
    # below the screen's darkest green (the dim lower corners, the floor shadow)
    KEY_HI = float(np.percentile(greenness[greenness > 40], 0.5)) - 6
    KEY_LO = max(20.0, KEY_HI - 55)
    print(f"green screen BGR {BG_BGR.round()}, key {KEY_LO:.0f}-{KEY_HI:.0f}")


def key(frame):
    """Full-size BGR frame -> BGRA at SCALE, cut out softly (user: cleaner
    edges than the earlier on/off cut, which left a pale rim and jaggies).

    - alpha follows how green each pixel is, so the fur's edge fades out
      instead of stepping;
    - edge pixels are un-mixed from the screen colour (C = a*F + (1-a)*BG
      solved for F), which removes the green/yellow rim;
    - shrunk to SCALE only after that, with premultiplied colours, so no
      green from the screen gets averaged in."""
    f = frame.astype(np.float32)
    b, g, r = f[..., 0], f[..., 1], f[..., 2]
    greenness = g - np.maximum(r, b)
    alpha = np.clip((KEY_HI - greenness) / (KEY_HI - KEY_LO), 0, 1)
    # specks of noise in the screen / pinholes in the cat
    hard = (alpha > 0.5).astype(np.uint8)
    hard = cv2.morphologyEx(hard, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    hard = cv2.morphologyEx(hard, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    near = cv2.dilate(hard, np.ones((5, 5), np.uint8)).astype(bool)
    alpha = np.where(near, alpha, 0)
    alpha = np.where(cv2.erode(hard, np.ones((5, 5), np.uint8)).astype(bool), 1, alpha)
    # pull the edge in by about a pixel: what's left of the rim goes
    alpha = np.clip(cv2.GaussianBlur(alpha, (3, 3), 0) * 1.15 - 0.15, 0, 1)
    a = alpha[..., None]
    fg = (f - (1 - a) * BG_BGR) / np.maximum(a, 1e-3)
    fg = np.clip(fg, 0, 255)
    # despill, both ways: no greener than red/blue, and (un-mixing overshoots
    # a little) no pink rim either: green stays at least the smaller of the two
    fg[..., 1] = np.clip(fg[..., 1], np.minimum(fg[..., 0], fg[..., 2]), np.maximum(fg[..., 0], fg[..., 2]) + 6)
    pre = np.dstack([fg * a, alpha * 255])
    pre = cv2.resize(pre, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_AREA)
    al = pre[..., 3:4]
    col = pre[..., :3] * 255 / np.maximum(al, 1e-3)
    out = np.dstack([np.clip(col, 0, 255), al]).round().astype(np.uint8)
    out[al[..., 0] < 1] = 0
    return out


SHADOW_MAX, SHADOW_GREY = 60, 18
HOLE_MAX = 1500   # px at 1920x1080: holes up to this size are inside the cat (an eye is ~200)
BLACK_LO, BLACK_HI = 18, 56   # brightest channel: <= LO is the background (and the faint floor
                              # glow under the feet), >= HI fully the cat


def key_black(frame):
    """key() for a clip on black: alpha from how bright each pixel is, near
    the outline only — inside the cat's outline (dark stripes, pupils, the
    nose) stays solid. The picture on black is the cat already multiplied by
    its alpha, so it's divided back out at the soft edge."""
    f = frame.astype(np.float32)
    m = f.max(axis=2)
    # the floor shadow under the feet: dark and grey (brightest channel <= 49,
    # channels within 11 of each other), where the cat's darkest fur is
    # brown (48+ apart) — it goes with the background
    m = np.where((m < SHADOW_MAX) & (m - f.min(axis=2) < SHADOW_GREY), 0, m)
    soft = np.clip((m - BLACK_LO) / (BLACK_HI - BLACK_LO), 0, 1)
    hard = (m > BLACK_LO).astype(np.uint8)
    hard = cv2.morphologyEx(hard, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    hard = cv2.morphologyEx(hard, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    # fill the small holes only (pupils, nose, dark stripes): background
    # enclosed by legs, body and paper is a big hole and stays background
    # (filling every enclosed hole painted those gaps solid black; user: buggy cat)
    n, labels, stats, _ = cv2.connectedComponentsWithStats((hard == 0).astype(np.uint8), connectivity=4)
    h, w = hard.shape
    inside = hard.astype(bool)
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        on_border = x == 0 or y == 0 or x + bw == w or y + bh == h
        if not on_border and area <= HOLE_MAX:
            inside |= labels == i
    keep = cv2.dilate(inside.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    solid = cv2.erode(inside.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
    alpha = np.where(solid, 1.0, np.where(keep, soft, 0.0))
    alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
    a = alpha[..., None]
    fg = np.where(a > 0.02, np.clip(f / np.maximum(a, 1e-3), 0, 255), 0)   # un-premultiply the edge
    pre = np.dstack([fg * a, alpha * 255])
    pre = cv2.resize(pre, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_AREA)
    al = pre[..., 3:4]
    col = pre[..., :3] * 255 / np.maximum(al, 1e-3)
    out = np.dstack([np.clip(col, 0, 255), al]).round().astype(np.uint8)
    out[al[..., 0] < 1] = 0
    return out


NEAR_MARGIN = 80   # px around the cat (and its sign) where loose bits are kept


def keep_near_the_cat(bgra):
    """Only the cat and what's right around it: the fourth clip (the cat
    breaking through glass) leaves faint crack lines all over the picture,
    which would sit over the game the whole time and made every frame
    full-size (memory). The biggest solid part is the cat with its sign; bits
    within NEAR_MARGIN of it stay (the glass bursting around it)."""
    solid = (bgra[..., 3] > 128).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(solid, connectivity=8)
    if n < 2:
        return bgra
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h, area = stats[i]
    if area < 2000:   # no cat yet (only the first bits of glass): nothing kept
        out = bgra.copy()
        out[...] = 0
        return out
    m = NEAR_MARGIN
    keep = np.zeros(bgra.shape[:2], bool)
    keep[max(0, y - m):y + h + m, max(0, x - m):x + w + m] = True
    out = bgra.copy()
    out[~keep] = 0
    return out


def paper_quad(bgra):
    """The paper's 4 corners (x, y) when it's held up facing us, else None:
    the biggest white, colorless area, nearly rectangular and wide enough."""
    hsv = cv2.cvtColor(bgra[..., :3], cv2.COLOR_BGR2HSV)
    white = ((hsv[..., 1] < 45) & (hsv[..., 2] > 195) & (bgra[..., 3] > 200)).astype(np.uint8) * 255
    white = cv2.morphologyEx(white, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(white)
    if n < 2:
        return None
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, w, h, area = stats[i]
    if area < 1500 or w < 60:
        return None
    contour = cv2.findContours((labels == i).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0][0]
    rect = cv2.minAreaRect(contour)
    rw, rh = rect[1]
    # a flat sheet facing us, tilted or not: it fills most of its own (turned)
    # rectangle, and it's landscape like the paper (200x140), not a thin
    # edge-on strip. (Measuring against the upright bounding box missed the
    # tilted paper as the cat lifts it: blank paper for a moment; user.)
    if rw * rh == 0 or area < 0.77 * rw * rh or not 1.0 <= max(rw, rh) / min(rw, rh) <= 1.8:
        return None
    box = cv2.boxPoints(rect)                           # 4 corners
    # order: top-left, top-right, bottom-right, bottom-left
    s = box.sum(axis=1)
    d = np.diff(box, axis=1).ravel()
    tl, br = box[np.argmin(s)], box[np.argmax(s)]
    tr, bl = box[np.argmin(d)], box[np.argmax(d)]
    return [[round(float(p[0]), 1), round(float(p[1]), 1)] for p in (tl, tr, br, bl)]


STILL_DIFF = 0.5   # mean change per frame (0-255 grey) below which the cat counts as standing still


def still_part(frames):
    """The longest run of frames where the cat barely moves (standing with the
    paper up): the part that's sped up or played back and forth to fit the
    display time, so the walk in and the walk off always play as filmed."""
    prev, diffs = None, []
    for e in frames:
        g = e.pop("_grey")
        diffs.append(None if prev is None or g is None else float(np.abs(g - prev).mean()))
        prev = g
    best, start = (0, 0), None
    for i, d in enumerate(diffs + [None]):
        if d is not None and d < STILL_DIFF:
            start = i - 1 if start is None else start
        else:
            if start is not None and i - 1 - start > best[1] - best[0]:
                best = (start, i - 1)
            start = None
    return best


WALK_CYCLE = 12   # frames: the last ones repeated to finish walking off
JS_NAME = {"cat": "CAT", "cat2": "CAT2"}   # the global each clip's cat.js sets (the OBS page)


def finish_walking_off(frames, width):
    """The second clip ends with the cat still half in the picture: it would
    vanish on the spot. The last WALK_CYCLE frames are repeated, each slid
    further toward the edge at the speed it was walking, until the cat is out
    of the picture. (Same images, new positions: no extra files.)"""
    last = frames[-1]
    if not last["file"]:
        return
    n = len(frames)
    if last["x"] <= 0:   # walking off to the left (the fourth clip): its right edge moves left
        w_of = lambda e: cv2.imread(str(OUT / e["file"]), cv2.IMREAD_UNCHANGED).shape[1]
        right = last["x"] + w_of(last)
        speed = max(4.0, (frames[n - 5]["x"] + w_of(frames[n - 5]) - right) / 4)
        cycle = frames[n - WALK_CYCLE:]
        j = 0
        while right > 0:
            right -= speed
            src = cycle[j % WALK_CYCLE]
            frames.append({"file": src["file"], "x": int(round(right - w_of(src))), "y": src["y"], "paper": None,
                           "_grey": None})
            j += 1
        return
    if last["x"] >= width:
        return
    speed = max(4.0, (last["x"] - frames[n - 5]["x"]) / 4)   # px a frame, from the tail's left edge
    cycle = frames[n - WALK_CYCLE:]
    target, j = float(last["x"]), 0
    while target < width:
        target += speed
        src = cycle[j % WALK_CYCLE]
        # each repeated frame's left edge (the tail) keeps moving at the same speed
        frames.append({"file": src["file"], "x": int(round(target)), "y": src["y"], "paper": None, "_grey": None})
        j += 1


def main(video):
    OUT.mkdir(parents=True, exist_ok=True)
    for old in list(OUT.glob("f_*.png")) + list(OUT.glob("f_*.webp")):
        old.unlink()
    global SCALE
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    SCALE = OUT_W / cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    ok, first = cap.read()
    corners = [first[2, 2], first[2, -3], first[-3, 2], first[-3, -3]]
    cut = key_black if max(int(c.max()) for c in corners) < 20 else key   # black background, or green
    if cut is key:
        calibrate_green(first)
    print("background:", "black" if cut is key_black else "green", "scale", round(SCALE, 4))
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    frames, i, k = [], 0, 0
    size = None
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if i % STEP == 0:
            bgra = keep_near_the_cat(cut(f))
            size = [bgra.shape[1], bgra.shape[0]]
            ys, xs = np.nonzero(bgra[..., 3] > 8)
            entry = {"file": None, "x": 0, "y": 0, "paper": None}
            if len(xs) > 200:   # the cat (or part of it) is in the picture
                x1, x2, y1, y2 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
                crop = bgra[y1:y2, x1:x2]
                name = f"f_{k:03d}.webp"   # about a tenth of a PNG's size, transparency kept
                cv2.imwrite(str(OUT / name), crop, [cv2.IMWRITE_WEBP_QUALITY, 88])
                quad = paper_quad(bgra)
                entry = {"file": name, "x": int(x1), "y": int(y1), "paper": quad}
            grey = None
            if entry["file"]:
                grey = cv2.cvtColor(bgra[..., :3], cv2.COLOR_BGR2GRAY).astype(np.float32) * (bgra[..., 3] / 255.0)
            entry["_grey"] = grey
            frames.append(entry)
            k += 1
        i += 1
    finish_walking_off(frames, OUT_W)
    still = still_part(frames)
    held = [n for n, e in enumerate(frames) if e["paper"]]
    # a few frames while the paper is held up miss it (it's still being
    # lifted): their corners are blended from the frames either side, so the
    # name doesn't blink
    for n in range(held[0], held[-1] + 1) if held else ():
        if frames[n]["paper"] is None and frames[n]["file"]:
            a = max(k for k in held if k < n)
            b = min(k for k in held if k > n)
            w = (n - a) / (b - a)
            frames[n]["paper"] = [[round(pa[0] + (pb[0] - pa[0]) * w, 1), round(pa[1] + (pb[1] - pa[1]) * w, 1)]
                                  for pa, pb in zip(frames[a]["paper"], frames[b]["paper"])]
    data = {
        "_about": "The 「猫」 opener display (hud/overlay.py CatPopup, obs/overlay.html): the user's "
                  "green-screen cat clip, cut out by tools/cat/make_cat.py.",
        "fps": fps / STEP, "size": size,
        # frames before hold_start: walking in; hold_start..hold_end: paper up; after: walking off
        "hold_start": held[0] if held else 0, "hold_end": held[-1] if held else 0,
        # inside that, the cat standing still: stretched or squeezed to fit the time
        "still_start": still[0], "still_end": still[1],
        "frames": frames,
    }
    (OUT / "cat.json").write_text(json.dumps(data, indent=0), encoding="utf-8")
    # the OBS page is opened from a file, where it can't fetch() JSON: the same data as a script
    (OUT / "cat.js").write_text(f"window.{JS_NAME.get(OUT.name, 'CAT')} = " + json.dumps(data) + ";" + chr(10),
                                encoding="utf-8")
    total = sum(f.stat().st_size for f in OUT.glob("f_*.webp"))
    print(f"{len(frames)} frames, paper held {data['hold_start']}-{data['hold_end']}, "
          f"still {still[0]}-{still[1]}, "
          f"{len(list(OUT.glob('f_*.webp')))} images, {total // 1024} KB")


if __name__ == "__main__":
    # make_cat.py <clip> [output folder under assets/, default "cat"]
    if len(sys.argv) > 2:
        OUT = ROOT / "assets" / sys.argv[2]
    main(sys.argv[1])
