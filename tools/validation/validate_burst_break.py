_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]   # the project folder
import sys
import re
from pathlib import Path

SCRIPTS_DIR = Path(str(_ROOT) + r"\scripts")
sys.path.insert(0, str(SCRIPTS_DIR))

import cv2
from live_pipeline import MatchPipeline
from capture_profile import compute_profile

BURST_DIR = Path(str(_ROOT) + r"\debug_frames\burst_break")

files = sorted(BURST_DIR.glob("f_*.png"),
                key=lambda p: int(re.match(r"f_(\d+)_t", p.name).group(1)))
print(f"{len(files)} frames")

first = cv2.imread(str(files[0]))
h, w = first.shape[:2]
profile = compute_profile(w, h)
print("profile:", profile)

pipeline = MatchPipeline(profile=profile)

prev_frozen = False
prev_left_n = 0
prev_right_n = 0
prev_resets = 0

for f in files:
    m = re.match(r"f_(\d+)_t([\d.]+)\.png", f.name)
    t = float(m.group(2))
    frame = cv2.imread(str(f))
    pipeline.process_frame(frame, t)
    if pipeline.match_reset_count != prev_resets:
        prev_left_n = 0
        prev_right_n = 0
        prev_resets = pipeline.match_reset_count
    if pipeline._frozen != prev_frozen:
        print(f"t={t:.2f} frozen -> {pipeline._frozen}")
        prev_frozen = pipeline._frozen
    if len(pipeline.left.event_log) != prev_left_n:
        print(f"t={t:.2f} LEFT new event: {pipeline.left.event_log[0]}")
        prev_left_n = len(pipeline.left.event_log)
    if len(pipeline.right.event_log) != prev_right_n:
        print(f"t={t:.2f} RIGHT new event: {pipeline.right.event_log[0]}")
        prev_right_n = len(pipeline.right.event_log)

print()
print("match_reset_count:", pipeline.match_reset_count)
