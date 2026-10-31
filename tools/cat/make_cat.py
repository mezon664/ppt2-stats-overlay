"""Cuts the cat out of the user's green-screen clip for the 「猫」 opener display:
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
SCALE = 0.5       # 1280x720 -> 640x360


BG_BGR = np.array([57, 178, 24], np.float32)   # the green screen (sampled at the corners)
KEY_LO, KEY_HI = 30, 95   # greenness (G - max(R, B)): <= LO is the cat, >= HI the screen


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
    if area < 1500 or w < 60 or area < 0.72 * w * h:   # not a flat sheet facing us (0.75 before the softer cut, which trims the sheet's rim a little)
        return None
    contour = cv2.findContours((labels == i).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0][0]
    box = cv2.boxPoints(cv2.minAreaRect(contour))       # 4 corners
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


def main(video):
    OUT.mkdir(parents=True, exist_ok=True)
    for old in list(OUT.glob("f_*.png")) + list(OUT.glob("f_*.webp")):
        old.unlink()
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    frames, i, k = [], 0, 0
    size = None
    while True:
        ok, f = cap.read()
        if not ok:
            break
        if i % STEP == 0:
            bgra = key(f)
            size = [bgra.shape[1], bgra.shape[0]]
            ys, xs = np.nonzero(bgra[..., 3] > 8)
            entry = {"file": None, "x": 0, "y": 0, "paper": None}
            if len(xs) > 200:   # the cat (or part of it) is in the picture
                x1, x2, y1, y2 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
                crop = bgra[y1:y2, x1:x2]
                name = f"f_{k:03d}.webp"   # about a tenth of a PNG's size, transparency kept
                cv2.imwrite(str(OUT / name), crop, [cv2.IMWRITE_WEBP_QUALITY, 82])
                quad = paper_quad(bgra)
                entry = {"file": name, "x": int(x1), "y": int(y1), "paper": quad}
            grey = None
            if entry["file"]:
                grey = cv2.cvtColor(bgra[..., :3], cv2.COLOR_BGR2GRAY).astype(np.float32) * (bgra[..., 3] / 255.0)
            entry["_grey"] = grey
            frames.append(entry)
            k += 1
        i += 1
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
    (OUT / "cat.js").write_text("window.CAT = " + json.dumps(data) + ";" + chr(10), encoding="utf-8")
    total = sum(f.stat().st_size for f in OUT.glob("f_*.webp"))
    print(f"{len(frames)} frames, paper held {data['hold_start']}-{data['hold_end']}, "
          f"still {still[0]}-{still[1]}, "
          f"{len(list(OUT.glob('f_*.webp')))} images, {total // 1024} KB")


if __name__ == "__main__":
    main(sys.argv[1])
