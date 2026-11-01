import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from image_io import read_image, write_image


class UnicodeImageIOTests(unittest.TestCase):
    def test_round_trip_under_unicode_and_space_path(self):
        source = np.zeros((12, 16, 3), dtype=np.uint8)
        source[:, :8] = (10, 120, 240)
        source[:, 8:] = (240, 120, 10)
        with tempfile.TemporaryDirectory(prefix="PPTetrics_日本語 folder ",
                                         dir=Path(__file__).resolve().parent) as directory:
            path = Path(directory) / "認識用画像 test.png"
            self.assertTrue(write_image(path, source))
            decoded = read_image(path)
            self.assertIsNotNone(decoded)
            np.testing.assert_array_equal(decoded, source)

    def test_missing_image_keeps_imread_style_none_result(self):
        with tempfile.TemporaryDirectory(prefix="PPTetrics_日本語 ",
                                         dir=Path(__file__).resolve().parent) as directory:
            self.assertIsNone(read_image(Path(directory) / "missing.png"))


if __name__ == "__main__":
    unittest.main()
