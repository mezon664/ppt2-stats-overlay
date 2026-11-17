import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import numpy as np

from diagnostic import Diagnostic


def test_writes_what_was_seen_and_the_status(tmp_path):
    d = Diagnostic(log_dir=tmp_path / "ログ フォルダ", every_s=5)
    assert d.due(100.0) and not d.due(102.0) and d.due(105.5)
    d.write(np.zeros((692, 1232, 3), np.uint8), ["line one", "capture: キャプチャ中"])
    assert (tmp_path / "ログ フォルダ" / "last_seen.jpg").stat().st_size > 0
    assert "キャプチャ中" in (tmp_path / "ログ フォルダ" / "last_status.txt").read_text(encoding="utf-8")
    d.write(None, ["no picture"])          # nothing captured: the status still updates
    assert "no picture" in (tmp_path / "ログ フォルダ" / "last_status.txt").read_text(encoding="utf-8")


def test_a_clean_small_picture_for_the_settings_window(tmp_path):
    """logs/preview.jpg: the picture alone, no notes written on it (the capture
    board card shows it; the yellow notes made a user ask if something was wrong)."""
    import cv2
    d = Diagnostic(log_dir=tmp_path, every_s=5)
    frame = np.full((692, 1232, 3), 90, np.uint8)
    d.write(frame, ["a long note line written in yellow"])
    small = cv2.imread(str(tmp_path / "preview.jpg"))
    assert small.shape[1] == 480
    assert int(np.abs(small.astype(int) - 90).max()) <= 3     # (nothing written on it)
