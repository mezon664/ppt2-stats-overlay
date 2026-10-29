_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]   # the project folder
import sys, re, logging
from pathlib import Path
sys.path.insert(0, str(_ROOT) + r"\scripts")
import cv2
logging.disable(logging.INFO)
import opener_detect
from live_pipeline import MatchPipeline
from capture_profile import compute_profile
S = Path(__file__).resolve().parent / "out"; S.mkdir(exist_ok=True)
orig = opener_detect.OpenerDetector.on_placements
def hooked(self, frame, count):
    name = orig(self, frame, count)
    if name:
        global _n; _n = globals().get("_n", 0) + 1
        out = S / f"opener_{sys.argv[1]}_{self.side}_{_n}.png"
        cv2.imwrite(str(out), frame); print("saved", out.name, name)
    return name
opener_detect.OpenerDetector.on_placements = hooked
files = sorted(Path(str(_ROOT) + r"\debug_frames", sys.argv[1]).glob("f_*.png"), key=lambda p: int(re.match(r"f_(\d+)_t", p.name).group(1)))
im0 = cv2.imread(str(files[0])); mp = MatchPipeline(profile=compute_profile(im0.shape[1], im0.shape[0]))
for f in files:
    mp.process_frame(cv2.imread(str(f)), float(re.match(r"f_\d+_t([\d.]+)\.png", f.name).group(1)))
