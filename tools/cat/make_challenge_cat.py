"""Cuts a cat out of a green-screen clip for 縛りプレイ's cats (hud/challenge.py):
the cat comes in from the screen's edge on your side, does what the clip
shows and goes, again and again: a clip of a cat coming in by one side works
best (leaving by the other side, it fades out instead of being cut off).

Writes assets/challenge_cats/<name>/: f_NNN.webp (each frame cropped to the
cat, transparent around it) and clip.json (per frame: where the crop sits in
the clip and its size; for the whole clip: the frames where the whole cat is in
the picture, which are the ones shown, and the part it covers in them).
Cats use the clips in that folder in name order, one after the other.
Also writes assets/challenge_cats/clips.js, every clip for the OBS page
(obs/overlay.html loads it as a script: a page opened from a file can't
read the clip.json files). After deleting a clip, run it with no arguments
to write clips.js again.

    python tools/cat/make_challenge_cat.py "C:\\path\\clip.mp4" cat1
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_cat   # the green-screen cut (key, calibrate_green, keep_near_the_cat)

ROOT = Path(__file__).resolve().parents[2]
OUT_W = 480   # the clip is shrunk to this width. Shown over a board 215 reference px wide:
              # about 300 px even on a 2560-wide game, so this is sharp enough and light


# --glass N (a cat breaking through glass, user: keep the glass): for the
# first N frames everything stays (the shards fly across the picture), after
# that the cracks within GLASS_MARGIN of the cat. Where the cat is (start / end
# / span, and "cx" / "cw" per frame: the side it comes in or goes by) is still
# worked out from the cat alone.
#     python tools/cat/make_challenge_cat.py <glass.mp4> cat3 --glass 36
GLASS_MARGIN = 150   # px (at OUT_W) of cracks kept around the cat after the burst
GLASS_FADE = 16      # --glass-until F: the cracks fade out over the GLASS_FADE frames up to F


# --anchor bottom / top: a cat cut by the picture's bottom (peeking up) or top
# (hanging from a drone): kept to that edge of the screen, over the board
# (hud/challenge.py Clip.anchor). Given by hand: a cat standing on the
# picture's bottom edge looks the same to a measurement.


# --rare: not taken in turn, now and then instead (hud/challenge.py pick_clip; the shiba)


# --scale K: this cat K times the usual size (the drone cat: 0.7)


# --play-out: plays to the last frame with the whole cat and fades there,
# glass and all (no walking off: its hole in the glass would slide away)


# --glass-boost F: the glass's opacity times F, its color a little whiter


# --glass-plate: the glass cut out by how each frame differs from the clip's
# first frame (the bare green screen): what got less green or brighter is
# glass. Keeps the thin cracks and the see-through look that the green key
# lost (user: make the glass nicer); the cat itself is still the green key's.
PLATE_FLOOR, PLATE_GAIN = 14.0, 5.0   # difference that counts, and how fast it turns opaque


def glass_from_plate(frame, plate_hsv, size):
    """(BGRA glass layer at `size`): whitish, opacity from the difference."""
    h = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).astype(np.float32)
    d = np.maximum(0, plate_hsv[..., 1] - h[..., 1]) + np.maximum(0, h[..., 2] - plate_hsv[..., 2])
    d = cv2.GaussianBlur(d, (3, 3), 0)
    a = np.clip((d - PLATE_FLOOR) * PLATE_GAIN, 0, 255)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
    col = np.clip(gray * 0.5 + 255 * 0.55, 0, 255)
    a = cv2.resize(a, size, interpolation=cv2.INTER_AREA)
    col = cv2.resize(col, size, interpolation=cv2.INTER_AREA)
    out = np.zeros((size[1], size[0], 4), np.uint8)
    out[..., 0] = np.clip(col + 6, 0, 255)   # (a touch of blue: glass, not paper)
    out[..., 1] = np.clip(col + 2, 0, 255)
    out[..., 2] = col
    out[..., 3] = a
    return out


def over(top, bottom):
    """BGRA `top` over BGRA `bottom`."""
    ta = top[..., 3:4].astype(np.float32) / 255
    ba = bottom[..., 3:4].astype(np.float32) / 255
    oa = ta + ba * (1 - ta)
    rgb = (top[..., :3] * ta + bottom[..., :3] * ba * (1 - ta)) / np.maximum(oa, 1e-6)
    return np.dstack([np.clip(rgb, 0, 255), oa * 255]).astype(np.uint8)


def main(video, name, glass=0, anchor=None, rare=False, scale=1.0, glass_until=0, play_out=False, glass_boost=1.0,
         glass_plate=False):
    out = ROOT / "assets" / "challenge_cats" / name
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("f_*.webp"):
        old.unlink()
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    make_cat.SCALE = OUT_W / cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    ok, first = cap.read()
    make_cat.calibrate_green(first)
    plate_hsv = cv2.cvtColor(first, cv2.COLOR_BGR2HSV).astype(np.float32) if glass_plate else None
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    frames, size, k = [], None, 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        keyed = make_cat.key(f)
        cat_only = make_cat.keep_near_the_cat(keyed)
        if glass and k < glass:
            bgra = keyed if (cat_only[..., 3] > 8).any() else cat_only   # (nothing before the cat)
        elif glass:
            saved, make_cat.NEAR_MARGIN = make_cat.NEAR_MARGIN, GLASS_MARGIN
            bgra = make_cat.keep_near_the_cat(keyed)
            make_cat.NEAR_MARGIN = saved
            if glass_until:   # the cracks fade out before the cat walks off (they'd go along with it)
                saved, make_cat.NEAR_MARGIN = make_cat.NEAR_MARGIN, 4
                strict = make_cat.keep_near_the_cat(keyed)   # the cat and its sign alone
                make_cat.NEAR_MARGIN = saved
                fade = min(1.0, max(0.0, (glass_until - k) / GLASS_FADE))
                cracks = (bgra[..., 3] > 0) & (strict[..., 3] == 0)
                bgra = bgra.copy()
                bgra[..., 3] = np.where(cracks, (bgra[..., 3] * fade).astype(np.uint8), bgra[..., 3])
        else:
            bgra = cat_only
        if glass_plate:   # the cat (green key) over the glass (difference from the bare screen)
            saved, make_cat.NEAR_MARGIN = make_cat.NEAR_MARGIN, 4
            strict = make_cat.keep_near_the_cat(keyed)
            make_cat.NEAR_MARGIN = saved
            if (strict[..., 3] > 8).any():
                layer = glass_from_plate(f, plate_hsv, (keyed.shape[1], keyed.shape[0]))
                layer[..., 3] = np.where(strict[..., 3] > 0, 0, layer[..., 3])   # (the cat isn't glass)
                bgra = over(strict, layer)
            else:
                bgra = strict
        elif glass and glass_boost != 1.0:   # the glass stronger (thin, faint lines over a busy game: user)
            saved, make_cat.NEAR_MARGIN = make_cat.NEAR_MARGIN, 4
            strict = make_cat.keep_near_the_cat(keyed)
            make_cat.NEAR_MARGIN = saved
            g = (bgra[..., 3] > 0) & (strict[..., 3] == 0)
            bgra = bgra.copy()
            bgra[..., 3] = np.where(g, np.clip(bgra[..., 3].astype(np.float32) * glass_boost, 0, 255), bgra[..., 3]).astype(np.uint8)
            light = np.clip(bgra[..., :3].astype(np.float32) * 0.6 + 255 * 0.4, 0, 255).astype(np.uint8)
            bgra[..., :3] = np.where(g[..., None], light, bgra[..., :3])
        size = [bgra.shape[1], bgra.shape[0]]
        ys, xs = np.nonzero(bgra[..., 3] > 8)
        cys, cxs = np.nonzero(cat_only[..., 3] > 8)
        entry = {"file": None, "x": 0, "y": 0}
        if len(xs) > 60 and len(cxs) > 60:
            x1, x2, y1, y2 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
            fname = f"f_{k:03d}.webp"
            cv2.imwrite(str(out / fname), bgra[y1:y2, x1:x2], [cv2.IMWRITE_WEBP_QUALITY, 75])   # (75: looks the same, ~30% smaller)
            entry = {"file": fname, "x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1}
            if glass:   # where the cat alone is (the picture has glass around it)
                cx1, cx2 = int(cxs.min()), int(cxs.max()) + 1
                entry.update({"cx": cx1, "cw": cx2 - cx1, "cy": int(cys.min()), "ch": int(cys.max()) + 1 - int(cys.min())})
        frames.append(entry)
        k += 1
    # the whole cat in the picture: not cut by the clip's left or right edge
    def box(e):   # the cat alone
        return (e.get("cx", e["x"]), e.get("cy", e["y"]), e.get("cw", e.get("w", 0)), e.get("ch", e.get("h", 0)))
    whole = [i for i, e in enumerate(frames) if e["file"] and box(e)[0] > 1 and box(e)[0] + box(e)[2] < size[0] - 1]
    start, end = whole[0], whole[-1]
    shown = [box(e) for e in frames[start:end + 1] if e["file"]]
    span = [min(b[0] for b in shown), min(b[1] for b in shown),
            max(b[0] + b[2] for b in shown), max(b[1] + b[3] for b in shown)]
    data = {
        "_about": "A 縛りプレイ cat (hud/challenge.py): the user's green-screen clip, cut out by "
                  "tools/cat/make_challenge_cat.py.",
        "fps": fps, "size": size,
        # shown: start..end, where the whole cat is in the picture (it fades in and out)
        "start": start, "end": end,
        # what the cat covers in those frames; y2 (its feet at the lowest) is the floor
        "span": span,
        "anchor": anchor,
        "rare": rare,
        "scale": scale,
        "play_out": play_out,
        "frames": frames,
    }
    (out / "clip.json").write_text(json.dumps(data, indent=0), encoding="utf-8")
    total = sum(f.stat().st_size for f in out.glob("f_*.webp"))
    print(f"{len(frames)} frames, shown {start}-{end}, span {span}, anchor {anchor}, {total // 1024} KB")
    write_page_list()


def write_page_list():
    """assets/challenge_cats/clips.js: the clips in name order, as hud/challenge.py load_clips."""
    folder = ROOT / "assets" / "challenge_cats"
    clips = []
    for path in sorted(folder.glob("*/clip.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        data.pop("_about", None)
        clips.append({"name": path.parent.name, **data})
    (folder / "clips.js").write_text(
        "// 縛りプレイ's cats for obs/overlay.html, written by tools/cat/make_challenge_cat.py\n"
        "window.CHALLENGE_CATS = " + json.dumps(clips, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"clips.js: {len(clips)} clips")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        args = sys.argv[1:]
        glass = 0
        if "--glass" in args:
            i = args.index("--glass")
            glass = int(args[i + 1])
            del args[i:i + 2]
        anchor = None
        if "--anchor" in args:
            i = args.index("--anchor")
            anchor = args[i + 1]
            del args[i:i + 2]
        rare = "--rare" in args
        if rare:
            args.remove("--rare")
        scale = 1.0
        if "--scale" in args:
            i = args.index("--scale")
            scale = float(args[i + 1])
            del args[i:i + 2]
        glass_until = 0
        if "--glass-until" in args:
            i = args.index("--glass-until")
            glass_until = int(args[i + 1])
            del args[i:i + 2]
        play_out = "--play-out" in args
        if play_out:
            args.remove("--play-out")
        glass_boost = 1.0
        if "--glass-boost" in args:
            i = args.index("--glass-boost")
            glass_boost = float(args[i + 1])
            del args[i:i + 2]
        glass_plate = "--glass-plate" in args
        if glass_plate:
            args.remove("--glass-plate")
        main(args[0], args[1] if len(args) > 1 else "cat1", glass, anchor, rare, scale, glass_until, play_out, glass_boost,
             glass_plate)
    else:
        write_page_list()
