"""Phase-1 feasibility test: replay a dense frame sequence through board_read and
report piece-lock events and garbage-row events with simple temporal stabilization.

Usage: python detect_events.py <frames_glob_dir> <fps> <side: left|right|both>
"""
import sys
import glob
import cv2
from board_read import read_board, LEFT_BOX, RIGHT_BOX, EMPTY, GARBAGE, COLS, ROWS

STABLE_FRAMES = 3  # a cell reading must repeat this many consecutive samples to be "confirmed"


def board_filled_count(board):
    return sum(1 for row in board for c in row if c != EMPTY)


def row_is_full_garbage(row):
    non_empty = [c for c in row if c != EMPTY]
    garbage_like = [c for c in row if c == GARBAGE]
    # allow one empty "hole" cell, rest must be garbage
    return len(garbage_like) >= COLS - 1 and len(non_empty) >= COLS - 1


def count_garbage_rows(board):
    return sum(1 for row in board if row_is_full_garbage(row))


def main():
    frame_dir, fps, side = sys.argv[1], float(sys.argv[2]), sys.argv[3]
    files = sorted(glob.glob(f"{frame_dir}/*.png"))
    box = LEFT_BOX if side == "left" else RIGHT_BOX

    history = []  # list of raw boards
    confirmed_prev = None
    prev_garbage_rows = None
    prev_filled = None
    events = []

    for i, f in enumerate(files):
        img = cv2.imread(f)
        t = i / fps
        raw = read_board(img, box)
        history.append(raw)
        if len(history) < STABLE_FRAMES:
            continue
        recent = history[-STABLE_FRAMES:]
        confirmed = [
            [
                recent[-1][r][c] if all(recent[k][r][c] == recent[-1][r][c] for k in range(STABLE_FRAMES)) else "?"
                for c in range(COLS)
            ]
            for r in range(ROWS)
        ]

        filled = board_filled_count(confirmed)
        garbage_rows = count_garbage_rows(confirmed)

        if confirmed_prev is not None:
            filled_prev = board_filled_count(confirmed_prev)
            if garbage_rows > (prev_garbage_rows or 0):
                events.append((round(t, 2), "garbage_added", garbage_rows - prev_garbage_rows))
            elif filled > filled_prev and filled - filled_prev <= 4 and garbage_rows == prev_garbage_rows:
                # modest growth with no new garbage row -> likely a piece lock (coarse heuristic)
                events.append((round(t, 2), "piece_lock_candidate", filled - filled_prev))
            elif filled < filled_prev:
                events.append((round(t, 2), "line_clear_or_shift", filled_prev - filled))

        confirmed_prev = confirmed
        prev_garbage_rows = garbage_rows
        prev_filled = filled

    for e in events:
        print(e)
    print(f"\ntotal frames analyzed: {len(files)}, events: {len(events)}")


if __name__ == "__main__":
    main()
