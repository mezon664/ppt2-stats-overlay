"""Writes assets/app.ico (the desktop shortcut's icon) from the icon the app
draws itself (hud/overlay.py draw_app_icon), so the two never differ.

    python tools/make_icon.py
"""
import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hud"))

from PyQt6 import QtCore, QtWidgets  # noqa: E402

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
OUT = ROOT / "assets" / "app.ico"


def png_bytes(img):
    buf = QtCore.QBuffer()
    buf.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def write_ico(path, images):
    """An .ico holding one PNG per size (supported since Windows Vista)."""
    pngs = [(size, png_bytes(img)) for size, img in images]
    out = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    for size, data in pngs:
        dim = 0 if size >= 256 else size   # 0 means 256
        out += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    out += b"".join(data for _, data in pngs)
    Path(path).write_bytes(out)


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])   # noqa: F841 (Qt needs one)
    import overlay
    write_ico(OUT, [(size, overlay.icon_image(size)) for size in SIZES])
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB, sizes {', '.join(map(str, SIZES))})")


if __name__ == "__main__":
    main()
