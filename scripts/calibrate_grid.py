"""Visual calibration helper: draws a candidate playfield grid over a frame so we can
eyeball-align it before hardcoding coordinates into the real detector.

Usage: python calibrate_grid.py <input_png> <output_png>
Edit LEFT_BOX / RIGHT_BOX below and re-run until the grid lines sit exactly on the
cell boundaries in the saved output image.
"""
import sys
import cv2
from image_io import read_image, write_image

COLS, ROWS = 10, 20

# (x1, y1, x2, y2) of the playfield's inner play area.
# Set A: 1920x1080 recording (samples/Replay 2025-04-25 ...mkv)
# LEFT_BOX = (305, 149, 668, 876)
# RIGHT_BOX = (1252, 149, 1615, 876)
# Set B: 1232x692 recording (samples/PuyoPuyoTetris2 2026-06-07 ...mp4)
LEFT_BOX = (198, 92, 429, 563)
RIGHT_BOX = (803, 92, 1034, 563)


def draw_grid(img, box, color):
    x1, y1, x2, y2 = box
    w = (x2 - x1) / COLS
    h = (y2 - y1) / ROWS
    for c in range(COLS + 1):
        x = int(x1 + c * w)
        cv2.line(img, (x, y1), (x, y2), color, 1)
    for r in range(ROWS + 1):
        y = int(y1 + r * h)
        cv2.line(img, (x1, y), (x2, y), color, 1)
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    img = read_image(src)
    draw_grid(img, LEFT_BOX, (0, 255, 0))
    draw_grid(img, RIGHT_BOX, (0, 255, 255))
    write_image(dst, img)
    print(f"wrote {dst}")


if __name__ == "__main__":
    main()
