"""What the recognition saw, kept for people whose numbers don't move.

Every few seconds the server writes logs/last_seen.jpg (the game picture as
it was read, with the recognition's state written on it) and
logs/last_status.txt. Someone with a problem sends these two plus
logs/server.log, and the cause shows (a covered window, a black capture, a
menu read as a match, an unusual window size...). Nothing leaves the PC by
itself; the tray menu just opens the folder.
"""
import time
from pathlib import Path

import cv2

from image_io import write_image
from version import VERSION

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
EVERY_S = 5.0


class Diagnostic:
    def __init__(self, log_dir=LOG_DIR, every_s=EVERY_S):
        self.log_dir = Path(log_dir)
        self.every_s = every_s
        self._last = 0.0

    def due(self, now=None):
        now = time.monotonic() if now is None else now
        if now - self._last < self.every_s:
            return False
        self._last = now
        return True

    def lines(self, status, pipeline=None, capture=None):
        try:
            return self._lines(status, pipeline, capture)
        except Exception:
            return [f"PPTetrics v{VERSION}", f"capture: {status.get('message')}"]

    def _lines(self, status, pipeline, capture):
        out = [time.strftime("%Y-%m-%d %H:%M:%S") + f"  PPTetrics v{VERSION}",
               f"capture: {status.get('message')}"]
        size = getattr(capture, "last_client_size", None)
        if size:
            out.append(f"game window (client): {size[0]}x{size[1]}")
        if pipeline is not None:
            gate = getattr(pipeline, "gameplay_gate", None)
            scores = getattr(gate, "last_scores", {}) or {}
            out.append("match screen: " + ("yes" if getattr(gate, "last_reason", "?") is None
                                           else str(getattr(gate, "last_reason", "?")))
                       + "  NEXT label " + " ".join(f"{k}={v:.2f}" for k, v in scores.items()))
            out.append(f"frozen={getattr(pipeline, '_frozen', '?')}  puyo={getattr(pipeline, 'puyo', '?')}"
                       f"  matches={getattr(pipeline, 'match_reset_count', '?')}")
        return out

    def write(self, frame, lines):
        """frame: BGR picture or None (nothing could be captured)."""
        try:
            self.log_dir.mkdir(exist_ok=True)
            (self.log_dir / "last_status.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
            if frame is None:
                return
            img = frame.copy()
            y = 22
            for line in lines:
                # ASCII only (cv2's font has no Japanese): the status message is in last_status.txt
                text = line.encode("ascii", "replace").decode()
                cv2.putText(img, text, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4, cv2.LINE_AA)
                cv2.putText(img, text, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1, cv2.LINE_AA)
                y += 22
            write_image(self.log_dir / "last_seen.jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        except Exception:
            pass   # a diagnostic must never stop recognition
