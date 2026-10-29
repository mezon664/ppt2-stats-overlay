"""Resolution/window-size independence for all hardcoded recognition coordinates.

Every box and template window in board_read.py / banner_detect.py was calibrated
against one specific recording: samples/PuyoPuyoTetris2 2026-06-07 00-26-52.mp4,
whose CLIENT area (not the outer window rect — see live_capture.py) is 1232x692.
That is the reference resolution. A live game window will usually be a different
pixel size (the player can resize it), so every coordinate and every template image
must be scaled by the ratio between the live client size and this reference before
they're usable — otherwise live capture would silently search the wrong pixels.

This does NOT make recognition resolution-*independent* in the sense of working at
any arbitrary size with full confidence — it only corrects for uniform scaling at
the SAME aspect ratio as the reference. A different aspect ratio shifts where the UI
elements actually are relative to each other (not just their size), which this
cannot correct for; see ASPECT_TOLERANCE below.
"""
from dataclasses import dataclass

import cv2
import numpy as np

REFERENCE_W, REFERENCE_H = 1232, 692
REFERENCE_ASPECT = REFERENCE_W / REFERENCE_H

# How far the live window's aspect ratio may drift from the reference before we
# refuse to guess. Not derived from measurement (no off-aspect footage exists to
# test against) — picked conservatively. See phase3 capture notes.
ASPECT_TOLERANCE = 0.03

# Below this fraction of the reference size, template matching on resized (shrunk)
# templates becomes unreliable in practice (features blur away); also not measured
# against real footage at small sizes — flagged as an assumption, not validated.
MIN_SCALE = 0.5
MAX_SCALE = 3.0


@dataclass
class CaptureProfile:
    ok: bool
    reason: str
    scale_x: float = 1.0
    scale_y: float = 1.0
    client_w: int = REFERENCE_W
    client_h: int = REFERENCE_H

    @property
    def scale(self):
        # uniform scale (scale_x == scale_y when ok, by construction below)
        return self.scale_x


def _compute_reference_profile():
    return CaptureProfile(ok=True, reason="ok", scale_x=1.0, scale_y=1.0,
                           client_w=REFERENCE_W, client_h=REFERENCE_H)


REFERENCE_PROFILE = _compute_reference_profile()  # identity scale, always ok — the default everywhere a live profile isn't supplied


def compute_profile(client_w, client_h):
    if client_w <= 0 or client_h <= 0:
        return CaptureProfile(ok=False, reason="ウインドウサイズを取得できません")

    aspect = client_w / client_h
    aspect_err = abs(aspect - REFERENCE_ASPECT) / REFERENCE_ASPECT
    if aspect_err > ASPECT_TOLERANCE:
        return CaptureProfile(
            ok=False,
            reason=(
                f"ウインドウのアスペクト比が未対応です (検出: {client_w}x{client_h}, "
                f"想定: {REFERENCE_W}x{REFERENCE_H}相当)。再キャリブレーションが必要です。"
            ),
            client_w=client_w, client_h=client_h,
        )

    scale = client_w / REFERENCE_W
    if not (MIN_SCALE <= scale <= MAX_SCALE):
        return CaptureProfile(
            ok=False,
            reason=f"ウインドウサイズが対応範囲外です (倍率 {scale:.2f}x, 対応: {MIN_SCALE}x-{MAX_SCALE}x)",
            client_w=client_w, client_h=client_h,
        )

    return CaptureProfile(ok=True, reason="ok", scale_x=scale, scale_y=scale,
                           client_w=client_w, client_h=client_h)


def scale_box(box, profile):
    x1, y1, x2, y2 = box
    return (
        int(round(x1 * profile.scale_x)),
        int(round(y1 * profile.scale_y)),
        int(round(x2 * profile.scale_x)),
        int(round(y2 * profile.scale_y)),
    )


_template_cache = {}  # (id(img), scale) -> resized image


def scale_template(img, profile):
    """Cached by image content + scale, NOT by id(img) — an earlier version keyed
    on id() alone and broke in practice: a temporary passed inline (straight from
    cv2.imread(...), no persistent reference) gets garbage-collected right after
    the call, and Python is then free to reuse that exact id() for the NEXT,
    unrelated image, which silently returned the FIRST image's cached resize
    instead of actually resizing the new one. hash(img.tobytes()) makes the key
    depend on what's actually in the array, so this can't happen regardless of
    how long the caller keeps `img` alive. These are small template images (at
    most a few hundred pixels), so the hashing cost is negligible even called
    once per frame."""
    if profile.scale_x == 1.0 and profile.scale_y == 1.0:
        return img
    key = (img.shape, hash(img.tobytes()), round(profile.scale_x, 4), round(profile.scale_y, 4))
    cached = _template_cache.get(key)
    if cached is not None:
        return cached
    h, w = img.shape[:2]
    new_w = max(1, int(round(w * profile.scale_x)))
    new_h = max(1, int(round(h * profile.scale_y)))
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    _template_cache[key] = resized
    return resized
