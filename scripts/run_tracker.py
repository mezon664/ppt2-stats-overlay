import sys
import glob
import cv2
from board_read import read_board, LEFT_BOX, RIGHT_BOX
from board_tracker import BoardTracker


def main():
    frame_dir, fps, side = sys.argv[1], float(sys.argv[2]), sys.argv[3]
    files = sorted(glob.glob(f"{frame_dir}/*.png"))
    box = LEFT_BOX if side == "left" else RIGHT_BOX
    tracker = BoardTracker(side)

    for i, f in enumerate(files):
        img = cv2.imread(f)
        t = i / fps
        raw = read_board(img, box)
        tracker.update(raw, t)

    print(f"=== {side} ({len(files)} frames, {len(files)/fps:.1f}s) ===")
    print(f"piece_count = {tracker.piece_count}")
    lock_events = [e for e in tracker.events if e[1] == "piece_lock"]
    garbage_events = [e for e in tracker.events if e[1] == "garbage_row_added"]
    clear_events = [e for e in tracker.events if e[1] == "line_clear"]
    print(f"lock events: {len(lock_events)}, garbage_row events: {len(garbage_events)}, line_clear events: {len(clear_events)}")
    print(f"unmatched (dropped) blobs: {len(tracker.unmatched_log)}")
    print()
    print("-- lock events (time, piece) --")
    for t, _, d in lock_events:
        print(f"  t={t:>6.2f}s  {d['piece']}  cells={d['cells']}")
    print()
    print("-- garbage/clear events --")
    for t, typ, d in garbage_events + clear_events:
        print(f"  t={t:>6.2f}s  {typ}  {d}")
    print()
    print(f"-- unmatched blob log (first 20 of {len(tracker.unmatched_log)}) --")
    for t, label, cells in tracker.unmatched_log[:20]:
        print(f"  t={t:>6.2f}s  label={label}  n_cells={len(cells)}")


if __name__ == "__main__":
    main()
