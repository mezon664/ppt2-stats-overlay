"""A 縛りプレイ cat from the 「猫」 opener display's cat (assets/cat/), with
「がんばれ」 written on its paper (user: let it turn up now and then).

Writes assets/challenge_cats/rare_ganbare/: each frame shrunk to the challenge
clips' width (make_challenge_cat.OUT_W) with the words drawn on the paper
(following its corners, as hud/overlay.py CatPopup draws a name), and
clip.json with "rare": true — rare clips aren't taken in turn but now and
then (hud/challenge.py RARE_CHANCE). Then clips.js again.

    python tools/cat/make_ganbare_cat.py [text]
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PyQt6 import QtCore, QtGui

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_challenge_cat

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "assets" / "cat"
NAME = "rare_ganbare"


def to_qimage(bgra):
    h, w = bgra.shape[:2]
    return QtGui.QImage(np.ascontiguousarray(bgra).data, w, h, 4 * w, QtGui.QImage.Format.Format_ARGB32).copy()


def to_array(img):
    img = img.convertToFormat(QtGui.QImage.Format.Format_ARGB32)
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    return np.frombuffer(ptr, np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)[:, :img.width()].copy()


def write_on_paper(bgra, quad, text):
    """The words on the paper (quad: its corners in this image's px)."""
    img = to_qimage(bgra)
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing)
    r = QtCore.QRectF(0, 0, 200, 140)   # the paper's box, as CatPopup
    t = QtGui.QTransform()
    QtGui.QTransform.quadToQuad(QtGui.QPolygonF([r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]),
                                QtGui.QPolygonF([QtCore.QPointF(*pt) for pt in quad]), t)
    p.setTransform(t)
    font = QtGui.QFont("Yu Gothic UI")
    font.setBold(True)
    size = 100
    font.setPixelSize(size)
    while size > 10 and QtGui.QFontMetricsF(font).horizontalAdvance(text) > 156:
        size -= 2
        font.setPixelSize(size)
    p.setFont(font)
    p.setPen(QtGui.QColor(25, 25, 30))
    p.drawText(r, QtCore.Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    return to_array(img)


def main(text="がんばれ"):
    src = json.loads((SRC / "cat.json").read_text(encoding="utf-8"))
    out = ROOT / "assets" / "challenge_cats" / NAME
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("f_*.webp"):
        old.unlink()
    k = make_challenge_cat.OUT_W / src["size"][0]
    size = [int(round(src["size"][0] * k)), int(round(src["size"][1] * k))]
    frames = []
    for i, f in enumerate(src["frames"]):
        if not f.get("file"):
            frames.append({"file": None, "x": 0, "y": 0})
            continue
        bgra = cv2.imread(str(SRC / f["file"]), cv2.IMREAD_UNCHANGED)
        if f.get("paper"):
            quad = [(x - f["x"], y - f["y"]) for x, y in f["paper"]]
            bgra = write_on_paper(bgra, quad, text)
        h, w = bgra.shape[:2]
        small = cv2.resize(bgra, (max(1, int(round(w * k))), max(1, int(round(h * k)))), interpolation=cv2.INTER_AREA)
        name = f"f_{i:03d}.webp"
        cv2.imwrite(str(out / name), small, [cv2.IMWRITE_WEBP_QUALITY, 88])
        frames.append({"file": name, "x": int(round(f["x"] * k)), "y": int(round(f["y"] * k)),
                       "w": small.shape[1], "h": small.shape[0]})
    whole = [i for i, e in enumerate(frames) if e["file"] and e["x"] > 1 and e["x"] + e["w"] < size[0] - 1]
    start, end = whole[0], whole[-1]
    shown = [e for e in frames[start:end + 1] if e["file"]]
    span = [min(e["x"] for e in shown), min(e["y"] for e in shown),
            max(e["x"] + e["w"] for e in shown), max(e["y"] + e["h"] for e in shown)]
    data = {"_about": "A rare 縛りプレイ cat: the 「猫」 opener display's cat with words on its paper "
                      "(tools/cat/make_ganbare_cat.py).",
            "fps": src["fps"], "size": size, "start": start, "end": end, "span": span, "anchor": None,
            "rare": True, "mirror": False,   # (the words would read backwards)
            "frames": frames}
    (out / "clip.json").write_text(json.dumps(data, indent=0), encoding="utf-8")
    total = sum(p.stat().st_size for p in out.glob("f_*.webp"))
    print(f"{len(frames)} frames, shown {start}-{end}, span {span}, {total // 1024} KB")
    make_challenge_cat.write_page_list()


if __name__ == "__main__":
    app = QtGui.QGuiApplication(sys.argv)   # (fonts: a real platform, not offscreen)
    main(*(sys.argv[1:2] or []))
