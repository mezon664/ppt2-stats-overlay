"""開幕テンプレ練習 on the game screen: over your board, the opener's shape
(faint), where the next piece goes (in its color), and a line of words above
the board (scripts/opener_practice.py makes the state, the server sends it as
state["practice"]).

Drawn only where the HUD stays out of the recognition's screen captures, like
縛りプレイ: the recognition reads the board, and a piece drawn on it would be
read as a block (hud/overlay.py _place_practice)."""
from PyQt6 import QtCore, QtGui, QtWidgets

# the boards in reference px (scripts/board_read.py LEFT_BOX / RIGHT_BOX): the
# grid's top is 11 px down the box, rows 23.0 px apart; columns a tenth of it
BOXES = {"left": (198, 92, 429, 563), "right": (803, 92, 1034, 563)}
GRID_TOP, ROW_H = 11, 23.0
PIECE_COLORS = {"I": (40, 190, 235), "O": (245, 200, 30), "T": (165, 70, 200), "S": (110, 200, 60),
                "Z": (225, 55, 65), "J": (45, 95, 220), "L": (245, 135, 30)}
TEXT = {
    "ja": {"locked": "エンドレスをONにしてマラソンを始めると使えます", "can": "このミノ順で組めます", "wait": "ミノ順を読んでいます", "no": "このミノ順では組めません", "done": "完成！",
           "off": "置き場所がずれました", "maybe": "8個目のミノしだい", "next": "次：{}", "hold": "HOLD してから {}",
           "title": "練習：{}", "deck": "練習：デッキ", "left": "あと{}個"},
    "en": {"locked": "Start Marathon with Endless ON to use this", "can": "These pieces build it", "wait": "Reading the pieces", "no": "Can't be built with these pieces", "done": "Done!",
           "off": "Off the plan", "maybe": "Depends on the 8th piece", "next": "Next: {}", "hold": "HOLD, then {}",
           "title": "Practice: {}", "deck": "Practice: deck", "left": "{} to go"},
}


def cell_rect(side, x, y, s):
    """Cell (column x, row y up from the bottom) on that board, at scale s."""
    x1, y1, x2, _ = BOXES[side]
    w = (x2 - x1) / 10
    top = y1 + GRID_TOP + (19 - y) * ROW_H
    return QtCore.QRectF((x1 + x * w) * s, top * s, w * s, ROW_H * s)


class PracticeLayer(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.state, self.scale, self.language = None, 1.0, "ja"

    def show_state(self, state, scale, language):
        if (state, scale, language) != (self.state, self.scale, self.language):
            self.state, self.scale, self.language = state, scale, language
            self.update()

    def paintEvent(self, event):
        st = self.state
        if not st:
            return
        side, s = st.get("side", "left"), self.scale
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        status = st.get("status")
        if status in ("ok", "maybe", "off") and st.get("shape"):
            nxt = st.get("next") or {}
            next_cells = {tuple(c) for c in nxt.get("cells", [])}
            # the shape still to build, faint
            for x, y in map(tuple, st["shape"]):
                if (x, y) not in next_cells:
                    p.fillRect(cell_rect(side, x, y, s).adjusted(1, 1, -1, -1), QtGui.QColor(255, 255, 255, 70))
            # where the next piece goes, in its color
            if next_cells:
                col = QtGui.QColor(*PIECE_COLORS.get(nxt.get("piece"), (255, 255, 255)))
                for x, y in next_cells:
                    r = cell_rect(side, x, y, s).adjusted(1, 1, -1, -1)
                    fill = QtGui.QColor(col)
                    fill.setAlpha(200)
                    p.fillRect(r, fill)
                    p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 220), max(1.0, 1.5 * s)))
                    p.drawRect(r)
        # the words, over the board's top
        t = TEXT.get(self.language, TEXT["ja"])
        name = st.get("name")
        if name and st.get("form") and st["form"] != "Wiki":
            name += f"（{st['form']}）"
        lines = [t["title"].format(name) if name else t["deck"]]
        if status in ("ok", "maybe", "off") and st.get("next"):
            nxt = st["next"]
            lines.append((t["hold"] if nxt.get("hold") else t["next"]).format(nxt.get("piece", "")))
            if st.get("left"):
                lines[0] += "  " + t["left"].format(st["left"])
        if status in ("locked", "wait", "no", "done", "off", "maybe"):
            lines.append(t[status])
        elif status == "ok" and st.get("single"):
            lines.append(t["can"])
        x1, y1, x2, _ = BOXES[side]
        font = QtGui.QFont("Meiryo")
        font.setPixelSize(max(9, int(15 * s)))
        font.setBold(True)
        p.setFont(font)
        fm = QtGui.QFontMetricsF(font)
        y = (y1 + GRID_TOP + 6 * ROW_H) * s
        for line in lines:
            w = fm.horizontalAdvance(line)
            box = QtCore.QRectF((x1 + x2) / 2 * s - w / 2 - 8 * s, y - fm.ascent() - 3 * s, w + 16 * s, fm.height() + 6 * s)
            p.fillRect(box, QtGui.QColor(0, 0, 0, 170))
            p.setPen(QtGui.QColor(255, 220, 90) if line is not lines[0] else QtGui.QColor(255, 255, 255))
            p.drawText(QtCore.QPointF((x1 + x2) / 2 * s - w / 2, y), line)
            y += fm.height() + 8 * s
        p.end()
