"""Saves a burst of raw live frames to disk for a fixed duration, so match-start
("GO!" disappearing) / match-end (loser's board collapsing) cues can be found and
inspected offline, the same way the T-SPIN template fix was found.
"""
import sys
import time
from pathlib import Path

from live_capture import GameWindowCapture
from image_io import write_image

FRAMES_DIR = Path(__file__).resolve().parent.parent / "debug_frames"


def main():
    # usage: capture_burst.py [seconds] [folder name under debug_frames]
    duration_s = float(sys.argv[1]) if len(sys.argv) > 1 else 40.0
    OUT_DIR = FRAMES_DIR / (sys.argv[2] if len(sys.argv) > 2 else "burst")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cap = GameWindowCapture()
    import cv2
    start = time.monotonic()
    i = 0
    while time.monotonic() - start < duration_s:
        frame, ok, reason, profile = cap.grab()
        if ok:
            t = time.monotonic() - start
            write_image(OUT_DIR / f"f_{i:04d}_t{t:.2f}.png", frame)
            i += 1
        time.sleep(0.1)  # ~10fps
    print(f"saved {i} frames to {OUT_DIR}")


if __name__ == "__main__":
    main()
