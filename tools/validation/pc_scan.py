_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]   # the project folder
import sys, re, glob
sys.path.insert(0, str(_ROOT) + r"\scripts")
import cv2, numpy as np
from board_read import LEFT_BOX, RIGHT_BOX
from capture_profile import compute_profile, scale_box
fs = sorted(glob.glob(str(_ROOT) + r"\debug_frames\burst_pc\f_*.png"), key=lambda p: int(re.search(r"f_(\d+)_", p).group(1)))
print(len(fs), "frames")
prof = None
for f in fs:
    im = cv2.imread(f)
    if prof is None: prof = compute_profile(im.shape[1], im.shape[0])
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    out = []
    for name, box in (("L", LEFT_BOX), ("R", RIGHT_BOX)):
        x1, y1, x2, y2 = scale_box(box, prof)
        h = hsv[y1:y2, x1:x2]
        orange = ((h[..., 0] >= 5) & (h[..., 0] <= 20) & (h[..., 1] >= 150) & (h[..., 2] >= 180)).mean()
        out.append(orange)
    if max(out) > 0.04:
        print(re.search(r"f_\d+_t[\d.]+", f).group(0), " ".join(f"{n}={v:.3f}" for n, v in zip("LR", out)))
