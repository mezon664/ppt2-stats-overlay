_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]   # the project folder
import sys, re, logging
from pathlib import Path
sys.path.insert(0, str(_ROOT) + r"\scripts")
import cv2
from queue_tracker import NextQueueTracker, count_advances
from capture_profile import compute_profile
logging.disable(logging.INFO)
name = sys.argv[1]
t0, t1 = float(sys.argv[2]), float(sys.argv[3])
files = sorted(Path(str(_ROOT) + r"\debug_frames", name).glob("f_*.png"),
               key=lambda p: int(re.match(r"f_(\d+)_t", p.name).group(1)))
prof = None; trk = {}; rebase = {"left": 0, "right": 0}; reads = {"left": [], "right": []}
for f in files:
    t = float(re.match(r"f_\d+_t([\d.]+)\.png", f.name).group(1))
    if not (t0 <= t <= t1): continue
    im = cv2.imread(str(f))
    if prof is None:
        prof = compute_profile(im.shape[1], im.shape[0])
        trk = {s: NextQueueTracker(s, prof) for s in ("left", "right")}
    for s, q in trk.items():
        before = q.stable
        q.update(im, t)
        reads[s].append((t, q.last_reading))
        if before is not None and q.stable != before and count_advances(before, q.stable) is None:
            rebase[s] += 1
for s in ("left", "right"):
    # slot-1 change count over smoothed (2-in-a-row) readings, an independent rough estimate
    prev = None; cand = None; n = 0; changes = 0
    for t, r in reads[s]:
        if not r or "." in r or "?" in r: cand = None; continue
        if r[0] == cand: n += 1
        else: cand, n = r[0], 1
        if n == 2:
            if prev is not None and cand != prev: changes += 1
            prev = cand
    print(f"{name} {s}: tracker pieces={trk[s].pieces_placed} rebaselines={rebase[s]} slot1-changes={changes}")
