"""Mock-ups of where the recognized opener could be shown (2x2 sheet)."""
_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]   # the project folder
import sys
from PyQt6 import QtWidgets, QtGui, QtCore

app = QtWidgets.QApplication(sys.argv)
SRC = str(_ROOT) + r"\tests\fixtures\play_ice_stage.jpg"
OUT = sys.argv[1]
K = 1245 / 1232
NAVY = QtGui.QColor(12, 22, 60, 225)
BLUE = QtGui.QColor(59, 142, 234)
RED = QtGui.QColor(229, 72, 77)
LBLUE = QtGui.QColor(140, 200, 255)
LRED = QtGui.QColor(255, 154, 158)


def font(px, bold=True):
    f = QtGui.QFont("Yu Gothic UI")
    f.setPixelSize(int(px * K))
    f.setBold(bold)
    return f


def text(p, x, y, s, px, color, align=QtCore.Qt.AlignmentFlag.AlignLeft, w=400, h=None):
    p.setFont(font(px))
    p.setPen(color)
    h = h or px * 1.6
    p.drawText(QtCore.QRectF(x * K, y * K, w * K, h * K), int(align | QtCore.Qt.AlignmentFlag.AlignVCenter), s)


def box(p, x, y, w, h, color=NAVY, radius=6, accent=None):
    p.setPen(QtCore.Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawRoundedRect(QtCore.QRectF(x * K, y * K, w * K, h * K), radius * K, radius * K)
    if accent is not None:
        p.fillRect(QtCore.QRectF(x * K, y * K, 4 * K, h * K), accent)


def title(p, s):
    box(p, 8, 8, 470, 34, QtGui.QColor(0, 0, 0, 190), 6)
    text(p, 16, 10, s, 20, QtGui.QColor(255, 230, 120), w=460, h=30)


def panel(draw):
    img = QtGui.QImage(SRC)
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    draw(p)
    p.end()
    return img


C = QtCore.Qt.AlignmentFlag.AlignHCenter


def a(p):   # big banner over the player's own board (upper middle), a few seconds
    title(p, "A. 盤面の上に大きく（数秒）")
    for cx, name, acc, lab in ((313, "迷走砲", BLUE, LBLUE), (918, "合掌TSD", RED, LRED)):
        box(p, cx - 100, 150, 200, 64, NAVY, 10)
        p.fillRect(QtCore.QRectF((cx - 100) * K, 210 * K, 200 * K, 4 * K), acc)
        text(p, cx - 100, 154, "開幕", 13, lab, C, 200, 20)
        text(p, cx - 100, 172, name, 28, QtGui.QColor("white"), C, 200, 38)


def b(p):   # under the HOLD box, small, all match
    title(p, "B. HOLDの下に小さく（試合中ずっと）")
    for x, name, acc, lab in ((112, "迷走砲", BLUE, LBLUE), (722, "合掌TSD", RED, LRED)):
        box(p, x, 178, 82, 40, NAVY, 6, acc)
        text(p, x + 8, 180, "開幕", 10, lab, w=74, h=14)
        text(p, x + 8, 194, name, 15, QtGui.QColor("white"), w=78, h=22)


def c(p):   # on the player name bar, all match
    title(p, "C. 名前の帯の上に（試合中ずっと）")
    for x, name, acc, lab in ((165, "開幕：迷走砲", BLUE, LBLUE), (768, "開幕：合掌TSD", RED, LRED)):
        box(p, x, 602, 150, 26, NAVY, 13)
        p.setPen(QtGui.QPen(acc, 2 * K))
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QtCore.QRectF(x * K, 602 * K, 150 * K, 26 * K), 13 * K, 13 * K)
        text(p, x, 603, name, 15, QtGui.QColor("white"), C, 150, 24)


def d(p):   # top center, both players, all match
    title(p, "D. 上の中央に両者まとめて（試合中ずっと）")
    box(p, 470, 52, 294, 46, NAVY, 8)
    text(p, 470, 52, "開幕", 11, QtGui.QColor(220, 228, 245), C, 294, 16)
    text(p, 476, 66, "迷走砲", 18, LBLUE, QtCore.Qt.AlignmentFlag.AlignLeft, 130, 28)
    text(p, 470, 66, "vs", 13, QtGui.QColor(220, 228, 245), C, 294, 28)
    text(p, 628, 66, "合掌TSD", 18, LRED, QtCore.Qt.AlignmentFlag.AlignRight, 130, 28)


imgs = [panel(f) for f in (a, b, c, d)]
w, h = imgs[0].width(), imgs[0].height()
sheet = QtGui.QImage(w * 2, h * 2, QtGui.QImage.Format.Format_RGB32)
p = QtGui.QPainter(sheet)
for i, im in enumerate(imgs):
    p.drawImage((i % 2) * w, (i // 2) * h, im)
p.end()
sheet.scaled(int(w * 1.2), int(h * 1.2), QtCore.Qt.AspectRatioMode.KeepAspectRatio,
             QtCore.Qt.TransformationMode.SmoothTransformation).save(OUT)
