"""camera_scan.py: a recording read as a capture board would give it.

The recording's frames go through scripts/live_capture.CameraCapture (a fake
camera device) after what a capture board / OBS's virtual camera does to a
picture: blown up to 1920x1080, video levels (16-235 instead of 0-255), and
lossy compression. The events recognized are printed next to the same
recording read plainly, so a difference shows.

  python tools/validation/camera_scan.py <video> [<video> ...]
"""
import logging
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import cv2
import numpy as np

import live_capture
from live_pipeline import MatchPipeline

READ_FPS = 15
EVENT = re.compile(r"\[(left|right)\] t=([\d.]+) (\w+) lines=(\d+)")


class Grab(logging.Handler):
    def __init__(self):
        super().__init__()
        self.events = []

    def emit(self, record):
        m = EVENT.search(record.getMessage())
        if m:
            self.events.append((m.group(1), round(float(m.group(2)), 1), m.group(3), int(m.group(4))))


def board_like(frame):
    """What a capture board gives: 1080p, video levels, compressed."""
    f = cv2.resize(frame, (1920, 1080), interpolation=cv2.INTER_CUBIC)
    f = (f.astype(np.float32) * (219 / 255) + 16).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


class FakeDevice:
    """A camera device that hands out the frame it's been given."""

    def __init__(self):
        self.frame = None

    def isOpened(self):
        return True

    def read(self):
        time.sleep(0.002)
        return (self.frame is not None), self.frame

    def release(self):
        pass


def run(path, camera):
    grab = Grab()
    logging.getLogger().addHandler(grab)
    logging.getLogger().setLevel(logging.INFO)
    pipe = MatchPipeline()
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 60
    step = max(1, round(fps / READ_FPS))
    dev = FakeDevice()
    cam = live_capture.CameraCapture(0, open_device=lambda i: dev) if camera else None
    if cam:
        live_capture.SIZE_SETTLE_S = 0.0
        cam._sizes = live_capture.SizeSettler(0.0)
    i, frames = 0, 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            t = i / fps
            if cam:
                dev.frame = board_like(frame)
                cam._latest, cam._latest_t = None, None
                deadline = time.monotonic() + 1.0
                if cam._dev is None:
                    cam._start()
                while cam._latest is None and time.monotonic() < deadline:
                    time.sleep(0.001)
                img, good, reason, profile = cam.grab()
            else:
                img, profile = live_capture.shrink_for_recognition(frame)
                good = True
            if good:
                pipe.rebuild_for_profile(profile)
                pipe.process_frame(img, t)
                frames += 1
        i += 1
    if cam:
        cam.close()
    logging.getLogger().removeHandler(grab)
    return grab.events, frames


if __name__ == "__main__":
    for path in sys.argv[1:]:
        plain, n1 = run(path, False)
        board, n2 = run(path, True)
        print(f"### {Path(path).name}  frames read: plain {n1}, board {n2}")
        kp = Counter((s, k) for s, _, k, _ in plain)
        kb = Counter((s, k) for s, _, k, _ in board)
        for key in sorted(set(kp) | set(kb)):
            mark = "" if kp[key] == kb[key] else "   <-- differs"
            print(f"  {key[0]:5} {key[1]:20} plain {kp[key]:3}  board {kb[key]:3}{mark}")
        sp = {(s, t, k) for s, t, k, _ in plain}
        sb = {(s, t, k) for s, t, k, _ in board}
        only_p = sorted(sp - sb)
        only_b = sorted(sb - sp)
        print(f"  only plain: {only_p[:8]}{' ...' if len(only_p) > 8 else ''}")
        print(f"  only board: {only_b[:8]}{' ...' if len(only_b) > 8 else ''}")
