_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]   # the project folder
import sys, re
from pathlib import Path
sys.path.insert(0, str(_ROOT) + r"\scripts")
import cv2, numpy as np
from match_boundary import MatchBoundaryDetector
from board_read import cell_center, LEFT_BOX, RIGHT_BOX, ROWS, COLS
from capture_profile import compute_profile, scale_box
root = Path(str(_ROOT) + r"\debug_frames")
TH = int(sys.argv[1]) if len(sys.argv) > 1 else 120

def bright_count(img, box):
    v = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 2]
    n = 0
    for r in range(ROWS):
        for c in range(COLS):
            cx, cy = cell_center(box, c, r)
            if v[cy-3:cy+3, cx-3:cx+3].mean() >= TH: n += 1
    return n

for name in ["burst", "burst2", "burst_ren", "burst_boundary", "burst_pc"]:
    files = sorted((root / name).glob("f_*.png"), key=lambda p: int(re.match(r"f_(\d+)_t", p.name).group(1)))
    if not files: continue
    f0 = cv2.imread(str(files[0])); prof = compute_profile(f0.shape[1], f0.shape[0])
    bd = MatchBoundaryDetector(profile=prof)
    lb, rb = scale_box(LEFT_BOX, prof), scale_box(RIGHT_BOX, prof)
    hist = []
    print("==", name)
    for f in files:
        t = float(re.match(r"f_\d+_t([\d.]+)\.png", f.name).group(1))
        im = cv2.imread(str(f))
        bl, br = bright_count(im, lb), bright_count(im, rb)
        hist.append((t, bl, br))
        vic, go = bd.update(im, t)
        if go:
            win = [(x, y) for tt, x, y in hist if t - 3.0 <= tt <= t]
            print(f"  GO t={t:.2f} now L={bl} R={br} | min max(L,R) in last 3s = {min(max(x,y) for x,y in win)}")
    allmax = [max(x, y) for _, x, y in hist]
    print(f"  frames with max(L,R)<=4: {sum(1 for m in allmax if m <= 4)} / {len(allmax)}")
for fx in ["setend_winner.jpg", "setend_menu.jpg", "pause_candy_stage.jpg", "play_ice_stage.jpg"]:
    im = cv2.imread(str(Path(str(_ROOT) + r"\tests\fixtures") / fx))
    prof = compute_profile(im.shape[1], im.shape[0])
    print(fx, bright_count(im, scale_box(LEFT_BOX, prof)), bright_count(im, scale_box(RIGHT_BOX, prof)))
