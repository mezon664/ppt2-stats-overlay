"""Core playfield reading: pixel -> cell label classification.

Calibrated against samples/overview/frame_010.png (1920x1080, see calibrate_grid.py).
"""
import cv2
import numpy as np
from image_io import read_image

COLS, ROWS = 10, 20
# Calibrated for samples/PuyoPuyoTetris2 2026-06-07 00-26-52.mp4 (1232x692).
# Previous recording (1920x1080) used LEFT_BOX=(305,149,668,876), RIGHT_BOX=(1252,149,1615,876) —
# kept here as a comment since resolution/theme changes require full recalibration, not scaling.
LEFT_BOX = (198, 92, 429, 563)
RIGHT_BOX = (803, 92, 1034, 563)

EMPTY = "."
GARBAGE = "#"
UNKNOWN = "?"

# Hue buckets (OpenCV H range 0-179) for the 7 standard piece colors, tuned by sampling.
# label: (hue_min, hue_max)
HUE_BUCKETS = [
    ("I", 85, 105),   # cyan
    ("J", 105, 130),  # blue
    ("O", 20, 35),    # yellow
    ("L", 8, 20),     # orange
    ("Z", 0, 8),       # red (low end)
    ("Z", 170, 180),   # red (wrap-around)
    ("S", 40, 85),     # green
    ("T", 130, 170),   # purple/magenta
]


def classify_cell(bgr_pixel):
    b, g, r = [int(v) for v in bgr_pixel]
    hsv = cv2.cvtColor(np.uint8([[[b, g, r]]]), cv2.COLOR_BGR2HSV)[0][0]
    h, s, v = int(hsv[0]), int(hsv[1]), int(hsv[2])

    if v < 55:
        return EMPTY
    if s < 45:
        return GARBAGE if v > 70 else EMPTY

    for label, lo, hi in HUE_BUCKETS:
        if lo <= h < hi:
            return label
    return UNKNOWN


def cell_center(box, col, row):
    x1, y1, x2, y2 = box
    w = (x2 - x1) / COLS
    h = (y2 - y1) / ROWS
    cx = int(x1 + (col + 0.5) * w)
    cy = int(y1 + (row + 0.5) * h)
    return cx, cy


def read_board(img, box):
    board = [[EMPTY for _ in range(COLS)] for _ in range(ROWS)]
    for row in range(ROWS):
        for col in range(COLS):
            cx, cy = cell_center(box, col, row)
            # average a small patch instead of a single pixel to reduce noise
            patch = img[cy - 3:cy + 3, cx - 3:cx + 3].reshape(-1, 3)
            mean_bgr = patch.mean(axis=0)
            board[row][col] = classify_cell(mean_bgr)
    return board


def board_to_str(board):
    return "\n".join("".join(row) for row in board)


def count_non_empty(board):
    return sum(1 for row in board for cell in row if cell != EMPTY)


def board_is_empty(board, tolerance=3):
    """True when (almost) every cell reads EMPTY — the signature of a just-started
    match (both boards reset simultaneously at match start, never mid-match).
    `tolerance` allows a handful of misclassified cells through: per-cell color
    classification has some live-capture noise (background bleed, compression-free
    raw pixels landing slightly differently than the recording this was calibrated
    against — the same class of issue found for the T-SPIN templates), so requiring
    literally zero non-empty cells across 200 cells turned out to never be
    satisfied in practice (confirmed: a live play session never triggered a single
    match reset). Not yet re-validated against a real match-boundary moment — see
    the diagnostic logging in live_pipeline._check_match_boundary."""
    return count_non_empty(board) <= tolerance


# A cell counts as "something there" for board_is_clear only if it is this
# bright (HSV V, 0-255). Placed blocks, garbage and the 1P/2P clouds read
# 150-255; the boards' own background art reads ~55-70 and, on some stages,
# brighter than read_board's V>=55 "non-empty" cut — which made read_board
# see blocks on an empty board and missed every match start on that stage
# (live, 2026-10-29). In all 8 recorded match starts both boards had 0 cells
# this bright within the 3s before GO!; the set-end screens had 33-171.
CLEAR_V_MIN = 120


def count_bright_cells(img, box, v_min=CLEAR_V_MIN):
    v = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 2]
    n = 0
    for row in range(ROWS):
        for col in range(COLS):
            cx, cy = cell_center(box, col, row)
            if v[cy - 3:cy + 3, cx - 3:cx + 3].mean() >= v_min:
                n += 1
    return n


def board_is_clear(img, box, tolerance=3):
    """True when the board shows (almost) nothing bright: no placed blocks,
    garbage, active piece or overlay text — whatever the stage's background
    art looks like. Used for match boundaries (both boards clear only
    between matches)."""
    return count_bright_cells(img, box) <= tolerance


if __name__ == "__main__":
    import sys
    img = read_image(sys.argv[1])
    print("LEFT:")
    print(board_to_str(read_board(img, LEFT_BOX)))
    print("\nRIGHT:")
    print(board_to_str(read_board(img, RIGHT_BOX)))
