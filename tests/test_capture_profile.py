import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import numpy as np
from capture_profile import compute_profile, scale_box, scale_template, REFERENCE_W, REFERENCE_H


def test_reference_resolution_gives_identity_scale():
    p = compute_profile(REFERENCE_W, REFERENCE_H)
    assert p.ok
    assert p.scale_x == 1.0 and p.scale_y == 1.0


def test_proportionally_larger_window_scales_up():
    p = compute_profile(REFERENCE_W * 2, REFERENCE_H * 2)
    assert p.ok
    assert abs(p.scale_x - 2.0) < 1e-6


def test_proportionally_smaller_window_within_min_scale():
    p = compute_profile(int(REFERENCE_W * 0.6), int(REFERENCE_H * 0.6))
    assert p.ok
    assert abs(p.scale_x - 0.6) < 0.01


def test_too_small_window_rejected_not_guessed():
    p = compute_profile(int(REFERENCE_W * 0.3), int(REFERENCE_H * 0.3))
    assert not p.ok
    assert "対応範囲外" in p.reason


def test_wrong_aspect_ratio_rejected_not_guessed():
    # same width, much taller window (e.g. ultrawide-stretched or cropped capture)
    p = compute_profile(REFERENCE_W, REFERENCE_H * 2)
    assert not p.ok
    assert "アスペクト比" in p.reason


def test_zero_size_rejected():
    p = compute_profile(0, 0)
    assert not p.ok


def test_scale_box_applies_uniformly():
    p = compute_profile(REFERENCE_W * 2, REFERENCE_H * 2)
    box = (100, 50, 200, 150)
    assert scale_box(box, p) == (200, 100, 400, 300)


def test_scale_template_resizes_image():
    p = compute_profile(REFERENCE_W * 2, REFERENCE_H * 2)
    img = np.zeros((20, 40, 3), dtype=np.uint8)
    resized = scale_template(img, p)
    assert resized.shape[:2] == (40, 80)


def test_scale_template_identity_at_reference_returns_same_object():
    p = compute_profile(REFERENCE_W, REFERENCE_H)
    img = np.zeros((20, 40, 3), dtype=np.uint8)
    assert scale_template(img, p) is img


def test_scale_template_cache_not_fooled_by_id_reuse():
    """Regression test for a confirmed bug: caching solely by id(img) broke when a
    caller passed a temporary (e.g. straight from cv2.imread(...)) that got
    garbage-collected and had its id() reused by a later, unrelated image — the
    second call silently returned the FIRST image's cached resize. Different
    content + same scale must never collide, even if ids could coincide."""
    p = compute_profile(REFERENCE_W * 2, REFERENCE_H * 2)

    def make_and_scale(fill_value):
        # no persistent reference to the pre-scale image — mirrors the exact
        # pattern that triggered the bug (match_boundary.py's original code).
        img = np.full((20, 40, 3), fill_value, dtype=np.uint8)
        return scale_template(img, p)

    first = make_and_scale(10)
    second = make_and_scale(200)

    assert first.shape == second.shape == (40, 80, 3)
    assert (first == 10).all(), "first result was overwritten/aliased"
    assert (second == 200).all(), "second result returned the first image's cached data"
