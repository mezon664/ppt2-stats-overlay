"""The set's win counter under the boards (「☆☆ WIN ☆☆」 / 「2★ WIN ★9」),
read to tell where a set (連戦) starts: the user's request was each player's
average APM / PPS over a set, so the set's averages start over when the
counter shows 0-0 at the start of a match.

The game shows it two ways (seen in every recording here):
  - stars: two slots a side, a won match lights one yellow (first to 2);
  - digits: one yellow star a side with the count in white next to it
    (longer sets).
Read from the screen only (the project's rule): yellow and white pixels in
each half of the counter, at reference coordinates scaled like the rest.

read(frame, profile) -> {"mode": "stars" | "digits", "left": n | None,
"right": n | None, "zero": bool} or None when no counter is seen. In digits
mode only 0 is told from the rest (a "0" is one glyph with one tall hole in
its middle): the count is 0 or None (some other number).
"""
import cv2
import numpy as np

from capture_profile import scale_box

# reference (1232x692) boxes of each side's half of the counter, WIN left out
LEFT_BOX = (500, 633, 586, 656)
RIGHT_BOX = (648, 633, 734, 656)
# yellow (a lit star): measured lit stars H 22-30, S 150+, V 200+
YELLOW_LO, YELLOW_HI = (18, 110, 170), (36, 255, 255)
# white (the digits): grey stars sit at V 120-200 with S under 40
WHITE_S_MAX, WHITE_V_MIN = 45, 222
# a star / digit covers at least this share of a reference-sized cell
MIN_BLOB = 18     # pixels at reference size
MIN_DIGIT = 25


def _blobs(mask, min_px):
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    return [stats[i] for i in range(1, n) if stats[i][cv2.CC_STAT_AREA] >= min_px]


def _is_zero(mask):
    """One white glyph with one hole, tall and in its middle: a "0"."""
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return False
    outer = [i for i, h in enumerate(hierarchy[0]) if h[3] < 0 and cv2.contourArea(contours[i]) >= 6]
    if len(outer) != 1:
        return False   # (two digits: 10, 20 ...)
    holes = [i for i, h in enumerate(hierarchy[0]) if h[3] == outer[0] and cv2.contourArea(contours[i]) >= 1]
    if len(holes) != 1:
        return False   # (8 has two, 1 2 3 5 7 none)
    _, gy, gw, gh = cv2.boundingRect(contours[outer[0]])
    _, hy, _, hh = cv2.boundingRect(contours[holes[0]])
    # a 0's hole runs nearly top to bottom: only a stroke above and below it.
    # A 9's (burst_break: hole 8 of 16 px, 7 px of stroke under it) or a 6's
    # leaves much more on one side.
    top_gap, bottom_gap = hy - gy, (gy + gh) - (hy + hh)
    return top_gap <= 0.3 * gh and bottom_gap <= 0.3 * gh and hh >= 0.45 * gh and gw <= 0.9 * gh


def _side(frame, box, scale):
    x1, y1, x2, y2 = box
    patch = frame[y1:y2, x1:x2]
    if patch.size == 0:
        return None
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    yellow = cv2.inRange(hsv, YELLOW_LO, YELLOW_HI)
    white = ((hsv[..., 1] <= WHITE_S_MAX) & (hsv[..., 2] >= WHITE_V_MIN)).astype(np.uint8) * 255
    # the stars' thin white outlines go, the digits' strokes (3 px) stay
    k = max(2, int(round(2 * scale)))
    white = cv2.morphologyEx(white, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    area = scale * scale
    stars = _blobs(yellow, MIN_BLOB * area)
    digits = _blobs(white, MIN_DIGIT * area)
    if digits:
        return {"mode": "digits", "count": 0 if _is_zero(white) else None, "stars": len(stars)}
    return {"mode": "stars", "count": len(stars), "stars": len(stars)}


def read(frame, profile):
    """See the module docstring."""
    if frame is None or not getattr(profile, "ok", False):
        return None
    scale = profile.scale_x
    left = _side(frame, scale_box(LEFT_BOX, profile), scale)
    right = _side(frame, scale_box(RIGHT_BOX, profile), scale)
    if left is None or right is None or left["mode"] != right["mode"]:
        return None
    mode = left["mode"]
    if mode == "digits" and not (left["stars"] == 1 and right["stars"] == 1):
        return None    # digits mode always has one star a side next to the count
    if mode == "stars" and (left["count"] > 2 or right["count"] > 2):
        return None
    return {"mode": mode, "left": left["count"], "right": right["count"],
            "zero": left["count"] == 0 and right["count"] == 0}
