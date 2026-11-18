"""flash_rows_shift.py: the clear flashes' line counts when the picture sits
off the board's row bands (a capture board's picture can, user report: a
TETRIS read as 5 lit rows and dropped, T-SPIN Doubles as 3).

At each clear-flash edge in a recording, the lit rows are counted with the
old fixed bands (count_lit_bands) and with the lit height
(count_lit_rows), on the frame as it is and moved up/down by part of a row.

  python tools/validation/flash_rows_shift.py <video> [<video> ...]
"""
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import cv2
import numpy as np

import live_capture
import flash_clear_detector as fcd

READ_FPS = 15
SHIFTS = (-0.5, -0.25, 0.25, 0.5)   # of a row


def moved(img, dy):
    out = np.zeros_like(img)
    if dy > 0:
        out[dy:] = img[:-dy]
    elif dy < 0:
        out[:dy] = img[-dy:]
    else:
        out[:] = img
    return out


def scan(path):
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 60
    step = max(1, round(fps / READ_FPS))
    dets = {}
    table = Counter()     # (method, shift, plain count, count) -> n
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            img, profile = live_capture.shrink_for_recognition(frame)
            for side in ("left", "right"):
                d = dets.setdefault(side, fcd.FlashClearDetector(side, profile=profile))
                if not d.update(img, i / fps):
                    continue
                truth = fcd.count_lit_bands(img, d.box)
                if not 1 <= truth <= 4:
                    continue
                pitch = (d.box[3] - d.box[1]) / fcd.ROWS * fcd.ROW_PITCH_OF_BAND
                for shift in (0.0,) + SHIFTS:
                    m = moved(img, int(round(shift * pitch)))
                    table[("bands", shift, truth, fcd.count_lit_bands(m, d.box))] += 1
                    table[("height", shift, truth, fcd.count_lit_rows(m, d.box))] += 1
        i += 1
    return table


if __name__ == "__main__":
    total = Counter()
    for path in sys.argv[1:]:
        total.update(scan(path))
        print("read", Path(path).name, flush=True)
    for method in ("bands", "height"):
        for shift in (0.0,) + SHIFTS:
            rows = {k: n for k, n in total.items() if k[0] == method and k[1] == shift}
            good = sum(n for k, n in rows.items() if k[2] == k[3])
            bad = {f"{k[2]}->{k[3]}": n for k, n in sorted(rows.items()) if k[2] != k[3]}
            print(f"{method:6} shift {shift:+.2f} row: right {good}/{sum(rows.values())}  wrong {bad}")
