"""OpenCV image file helpers that handle Unicode paths on Windows."""
from pathlib import Path

import cv2
import numpy as np


def read_image(path, flags=cv2.IMREAD_COLOR):
    """Read an image through Python's Unicode-aware file APIs.

    OpenCV's filename-based imread may fail for non-ASCII Windows paths. Keep
    imread-like behavior by returning None when a file is absent or undecodable.
    """
    try:
        encoded = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if encoded.size == 0:
        return None
    try:
        return cv2.imdecode(encoded, flags)
    except cv2.error:
        return None


def write_image(path, image, params=()):
    """Write an image through Python's Unicode-aware file APIs."""
    suffix = Path(path).suffix
    if not suffix:
        raise ValueError(f"image path has no file extension: {path}")
    success, encoded = cv2.imencode(suffix, image, list(params))
    if not success:
        return False
    try:
        encoded.tofile(str(path))
    except OSError:
        return False
    return True
