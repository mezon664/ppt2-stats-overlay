"""Cuts a cat out of a green-screen clip for 縛りプレイ's cats (hud/challenge.py):
the cat comes in from the screen's edge on your side, does what the clip
shows and goes, again and again: a clip of a cat coming in by one side works
best (leaving by the other side, it fades out instead of being cut off).

Writes assets/challenge_cats/<name>/: f_NNN.webp (each frame cropped to the
cat, transparent around it) and clip.json (per frame: where the crop sits in
the clip and its size; for the whole clip: the frames where the whole cat is in
the picture, which are the ones shown, and the part it covers in them).
Cats use the clips in that folder in name order, one after the other.

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


def main(video, name):
    out = ROOT / "assets" / "challenge_cats" / name
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("f_*.webp"):
        old.unlink()
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    make_cat.SCALE = OUT_W / cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    ok, first = cap.read()
    make_cat.calibrate_green(first)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    frames, size, k = [], None, 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        bgra = make_cat.keep_near_the_cat(make_cat.key(f))
        size = [bgra.shape[1], bgra.shape[0]]
        ys, xs = np.nonzero(bgra[..., 3] > 8)
        entry = {"file": None, "x": 0, "y": 0}
        if len(xs) > 60:
            x1, x2, y1, y2 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
            fname = f"f_{k:03d}.webp"
            cv2.imwrite(str(out / fname), bgra[y1:y2, x1:x2], [cv2.IMWRITE_WEBP_QUALITY, 88])
            entry = {"file": fname, "x": x1, "y": y1, "w": x2 - x1, "h": y2 - y1}
        frames.append(entry)
        k += 1
    # the whole cat in the picture: not cut by the clip's left or right edge
    whole = [i for i, e in enumerate(frames) if e["file"] and e["x"] > 1 and e["x"] + e["w"] < size[0] - 1]
    start, end = whole[0], whole[-1]
    shown = [e for e in frames[start:end + 1] if e["file"]]
    span = [min(e["x"] for e in shown), min(e["y"] for e in shown),
            max(e["x"] + e["w"] for e in shown), max(e["y"] + e["h"] for e in shown)]
    data = {
        "_about": "A 縛りプレイ cat (hud/challenge.py): the user's green-screen clip, cut out by "
                  "tools/cat/make_challenge_cat.py.",
        "fps": fps, "size": size,
        # shown: start..end, where the whole cat is in the picture (it fades in and out)
        "start": start, "end": end,
        # what the cat covers in those frames; y2 (its feet at the lowest) is the floor
        "span": span,
        "frames": frames,
    }
    (out / "clip.json").write_text(json.dumps(data, indent=0), encoding="utf-8")
    total = sum(f.stat().st_size for f in out.glob("f_*.webp"))
    print(f"{len(frames)} frames, shown {start}-{end}, span {span}, {total // 1024} KB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "cat1")
