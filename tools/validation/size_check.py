"""Replays a recording resized to another window size and prints what the
pipeline recognized, for comparison with the native-size run."""
_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]   # the project folder
import sys, re, logging
from pathlib import Path
sys.path.insert(0, str(_ROOT) + r"\scripts")
import cv2
logging.disable(logging.INFO)
from live_pipeline import MatchPipeline
from capture_profile import compute_profile

name, W, H = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
files = sorted(Path(str(_ROOT) + r"\debug_frames", name).glob("f_*.png"),
               key=lambda p: int(re.match(r"f_(\d+)_t", p.name).group(1)))
prof = compute_profile(W, H)
mp = MatchPipeline(profile=prof)
starts, events, seen = [], [], {"left": 0, "right": 0}
resets = 0
for f in files:
    t = float(re.match(r"f_\d+_t([\d.]+)\.png", f.name).group(1))
    im = cv2.imread(str(f))
    if (im.shape[1], im.shape[0]) != (W, H):
        im = cv2.resize(im, (W, H), interpolation=cv2.INTER_AREA if W < im.shape[1] else cv2.INTER_LINEAR)
    mp.process_frame(im, t)
    if mp.match_reset_count != resets:
        resets = mp.match_reset_count
        starts.append(round(mp.start_t, 2) if mp.start_t is not None else None)
        seen = {"left": 0, "right": 0}
    for side in ("left", "right"):
        log = getattr(mp, side).event_log
        if len(log) > seen[side]:
            for e in reversed(log[: len(log) - seen[side]]):
                events.append(f"{side[0].upper()}:{e['label']}+{e['lines']}")
            seen[side] = len(log)
print(f"{name} @ {W}x{H} (scale {prof.scale:.2f}) starts={starts}")
print("  events:", " ".join(events))
