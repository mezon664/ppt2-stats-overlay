"""The developer's frame dumps are trimmed to this run's newest DEBUG_MAX_FILES,
quickly and without holding up the states sent to the HUD (user: a late
opener name showed only for a moment — the trimming stopped every send for
~5 s every ~38 s)."""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def test_only_this_runs_oldest_frames_go(tmp_path, monkeypatch):
    import data_server
    now = time.time()
    old = tmp_path / "flash_old.png"
    old.write_bytes(b"x")
    os.utime(old, (now - 7200, now - 7200))           # an earlier run's: kept
    (tmp_path / "burst").mkdir()
    (tmp_path / "burst" / "f_0000.png").write_bytes(b"x")   # a recording: kept
    for i in range(5):
        p = tmp_path / f"flash_{i}.png"
        p.write_bytes(b"x")
        os.utime(p, (now + i, now + i))
    monkeypatch.setattr(data_server, "DEBUG_DIR", tmp_path)
    monkeypatch.setattr(data_server, "DEBUG_DUMP_DIR", str(tmp_path))
    monkeypatch.setattr(data_server, "DEBUG_MAX_FILES", 3)
    monkeypatch.setattr(data_server, "RUN_STARTED", now - 60)
    data_server.prune_debug_frames()
    left = sorted(p.name for p in tmp_path.glob("*.png"))
    assert left == ["flash_2.png", "flash_3.png", "flash_4.png", "flash_old.png"]
    assert (tmp_path / "burst" / "f_0000.png").exists()


def test_the_sends_dont_wait_for_it():
    src = (Path(__file__).resolve().parent.parent / "scripts" / "data_server.py").read_text(encoding="utf-8")
    assert "await asyncio.get_running_loop().run_in_executor(None, prune_debug_frames)" not in src
