_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]   # the project folder
import sys, re
from pathlib import Path
sys.path.insert(0, str(_ROOT) + r"\scripts")
import cv2
from match_boundary import MatchBoundaryDetector
from board_read import read_board, board_is_empty, LEFT_BOX, RIGHT_BOX
from capture_profile import compute_profile, scale_box
from gameplay_gate import GameplayGate
root = Path(str(_ROOT) + r"\debug_frames")
for name in ["burst", "burst2", "burst_ren", "burst_break", "burst_boundary"]:
    files = sorted((root / name).glob("f_*.png"), key=lambda p: int(re.match(r"f_(\d+)_t", p.name).group(1)))
    f0 = cv2.imread(str(files[0])); prof = compute_profile(f0.shape[1], f0.shape[0])
    bd = MatchBoundaryDetector(profile=prof); gate = GameplayGate(profile=prof)
    lb, rb = scale_box(LEFT_BOX, prof), scale_box(RIGHT_BOX, prof)
    last_empty = None; empties = []
    print("==", name, len(files))
    for f in files:
        t = float(re.match(r"f_\d+_t([\d.]+)\.png", f.name).group(1))
        fr = cv2.imread(str(f))
        le = board_is_empty(read_board(fr, lb)); re_ = board_is_empty(read_board(fr, rb))
        if le and re_: last_empty = t
        vic, go = bd.update(fr, t)
        if vic: print(f"  t={t:.2f} victory")
        if go:
            print(f"  t={t:.2f} GO-gone  since_both_empty={None if last_empty is None else round(t-last_empty,2)}  now L_empty={le} R_empty={re_} gate={gate.update(fr)}")
