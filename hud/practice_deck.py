"""The settings window's 開幕テンプレ練習 deck: the openers in order, each
one's forms (形: the wiki's shapes, or your own テト譜), mirrored or not, and
the setup rates of the whole deck (scripts/opener_practice.py).

The deck is saved to config/practice_deck.json as it's changed (the server
reads it from there); the rates worked out for a form are kept in
config/practice_rates/ so changing the order is instant."""
import hashlib
import json
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtWidgets

import ui_kit as ui
import opener_practice as op

ROOT = Path(__file__).resolve().parent.parent
RATES_DIR = ROOT / "config" / "practice_rates"
WIKI_RATES = ROOT / "assets" / "opener_rates.json"
PIECE_COLORS = {"I": (40, 190, 235), "O": (245, 200, 30), "T": (165, 70, 200), "S": (110, 200, 60),
                "Z": (225, 55, 65), "J": (45, 95, 220), "L": (245, 135, 30)}

TEXT = {
    "ja": {"mode": "練習のしかた", "mode_deck": "デッキ全体", "mode_single": "テンプレ単体",
           "single": "テンプレ単体",
           "single_desc": "選んだテンプレだけを練習します。試合では、このミノ順で組めるかを判定して、組めるならガイドします。",
           "single_now": "練習するテンプレ：{}", "single_none": "練習するテンプレを選んでください", "use": "これにする",
           "total_single": "このテンプレ：{:.2f}%　組めない：{:.2f}%",
           "deck": "デッキ（上ほど優先）",
           "deck_desc": "試合では、ミノ順で組めるもののうち一番上のテンプレ（その中では上の形から）を選んでガイドします。",
           "up": "上へ", "down": "下へ", "remove": "外す", "add": "追加", "pick": "テンプレを選ぶ（名前で絞り込み）",
           "mirror": "左右反転した形も使う", "empty": "（テンプレを追加してください）",
           "forms": "形：{}", "forms_none": "形", "forms_desc": "上の形ほど優先します。チェックを外した形は使いません。"
                                              "テト譜でミノに色を付けると、その色どおりのミノで組む形になります（灰色はどのミノでも）。",
           "form_name": "形の名前（理想形など）", "form_fumen": "テト譜（v115@…）", "delete": "削除",
           "paint_how": "盤面で作る：色を選んで左ドラッグで塗り、右ドラッグで消します。灰色はどのミノでも入る場所です。",
           "paint_add": "塗った形を追加", "paint_clear": "全部消す", "paint_copy": "選んだ形を写す", "gray": "灰", "erase": "消",
           "p_empty": "盤面にミノを塗ってください。", "p_count": "塗ったマスの数が 4 の倍数ではありません。",
           "p_big": "1巡目と次の 1 個（8 ミノ、32 マス）までの形にしてください。",
           "p_shape": "この塗り方ではミノの形になりません（段が埋まる形は、Tスピンで消す形だけ使えます）。",
           "bad_fumen": "このテト譜は読めませんでした（テト譜の v115@ から後ろを貼ってください）。",
           "no_shape": "この形は 4 の倍数のマスでないか、置けない形でした。",
           "routes": "2巡目以降の派生：{}", "routes_none": "2巡目以降の派生",
           "routes_desc": "テンプレを組んだあと、Wikiに載っている派生へ案内します。上の派生ほど優先し、チェックを外した派生は使いません。"
                          "Wikiに形が載っていない部分は案内しません。",
           "routes_empty": "（このテンプレには、案内できる派生がWikiにありません）",
           "rates": "セットアップ率",
           "rates_desc": "1巡目の 5040 通りと 2巡目の最初の 1 個（7 通り）のすべてで、デッキのどれが組めるかを数えます。"
                         "ホールドあり。T スピンで段を消す形は、T を入れる直前の形までで数えます（テトリステンプレ整理Wiki の"
                         "1巡目テンプレの数字と同じ数え方です）。",
           "calc": "計算する", "calcing": "計算中…", "total": "デッキ全体：{:.2f}%　どれも組めない：{:.2f}%",
           "row": "{}位　{}（{}）：選ばれる {:.2f}%　単独で組める {:.2f}%", "wiki": "（Wiki：片側 {} / 反転込み {}）",
           "stale": "デッキを変えたので、もう一度計算してください。", "failed": "計算できませんでした。"},
    "en": {"mode": "Practice", "mode_deck": "Whole deck", "mode_single": "One opener",
           "single": "One opener",
           "single_desc": "Practise only the opener you pick. In a game it works out whether these pieces build it, "
                          "and guides you if they do.",
           "single_now": "Opener: {}", "single_none": "Pick an opener", "use": "Use this",
           "total_single": "This opener: {:.2f}%   not: {:.2f}%",
           "deck": "Deck (top first)",
           "deck_desc": "In a match, the topmost opener (and its topmost form) the pieces build is the one guided.",
           "up": "Up", "down": "Down", "remove": "Remove", "add": "Add", "pick": "Pick an opener (type to filter)",
           "mirror": "Use the mirrored shapes too", "empty": "(Add openers)",
           "forms": "Forms: {}", "forms_none": "Forms", "forms_desc": "Top first; unticked ones aren't used. Colored "
                                                                   "pieces in a fumen must be those pieces (gray: any).",
           "form_name": "Form name", "form_fumen": "Fumen (v115@…)", "delete": "Delete",
           "paint_how": "Paint it: pick a color, drag with the left button to paint, the right to erase. Gray: any piece.",
           "paint_add": "Add this shape", "paint_clear": "Clear", "paint_copy": "Copy the selected form", "gray": "Any",
           "erase": "Erase",
           "p_empty": "Paint some pieces on the board.", "p_count": "The painted cells aren't a multiple of 4.",
           "p_big": "Keep it to the first bag and one more piece (8 pieces, 32 cells).",
           "p_shape": "These colors don't make pieces (full rows only work as a T-spin).",
           "bad_fumen": "This fumen couldn't be read (paste from v115@ on).",
           "no_shape": "This shape isn't whole pieces, or can't be built.",
           "routes": "Routes after the opener: {}", "routes_none": "Routes after the opener",
           "routes_desc": "After the opener, guides you along the routes on the wiki. Top first; unticked ones aren't "
                          "used. Parts the wiki doesn't draw aren't guided.",
           "routes_empty": "(The wiki has no route to guide for this opener)",
           "rates": "Setup rates",
           "rates_desc": "Counts which of the deck builds for each of the 5040 first bags and the 7 next pieces, with "
                         "HOLD. Shapes clearing rows with a T-spin count up to just before the T.",
           "calc": "Work out", "calcing": "Working…", "total": "Whole deck: {:.2f}%   none: {:.2f}%",
           "row": "{}. {} ({}): picked {:.2f}%  alone {:.2f}%", "wiki": " (wiki: one side {} / mirrored {})",
           "stale": "The deck changed: work it out again.", "failed": "It couldn't be worked out."},
}


def _cache_path(targets):
    key = json.dumps([[list(map(list, c)), sorted(col) if col else None] for c, col in (t.key() for t in targets)])
    return RATES_DIR / (hashlib.sha1(key.encode("utf-8")).hexdigest() + ".json")


def masks_for(targets, progress=None):
    """form_masks, kept in config/practice_rates/ by the targets."""
    path = _cache_path(targets)
    try:
        masks = json.loads(path.read_text(encoding="utf-8"))
        if len(masks) == len(op.all_bags()):
            return masks
    except (OSError, ValueError):
        pass
    try:
        masks = op.form_masks(targets, progress=progress)
    except Exception:   # no worker processes here: one by one
        bags = op.all_bags()
        masks = []
        for k, b in enumerate(bags):
            masks.append(op.bag_mask(targets, b))
            if progress and k % 60 == 0:
                progress(k, len(bags))
    RATES_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(masks), encoding="utf-8")
    return masks


class RateWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(int, int)
    finished_rates = QtCore.pyqtSignal(object)

    def __init__(self, cands):
        super().__init__()
        self.cands = cands

    def run(self):
        try:
            n = len(self.cands)
            out = []
            for k, (o, f, ts) in enumerate(self.cands):
                masks = masks_for(ts, lambda d, t, k=k: self.progress.emit(k * t + d, n * t))
                out.append((o, f, masks))
            self.finished_rates.emit(op.deck_rates(out))
        except Exception:
            import logging
            logging.getLogger("hud").exception("setup rates failed")
            self.finished_rates.emit(None)


def draw_targets(target, w=180, h=90):
    """A small picture of one target (its colors if it has them)."""
    pm = QtGui.QPixmap(w, h)
    pm.fill(QtGui.QColor(28, 30, 38))
    if target is None:
        return pm
    top = max((y for _, y in target.cells), default=0) + 1
    rows = max(4, top)
    cell = min(w / 10, h / rows)
    x0, y0 = (w - cell * 10) / 2, h - cell * rows
    p = QtGui.QPainter(pm)
    for x, y in target.cells:
        piece = (target.colors or {}).get((x, y))
        col = QtGui.QColor(*PIECE_COLORS[piece]) if piece else QtGui.QColor(150, 150, 160)
        p.fillRect(QtCore.QRectF(x0 + x * cell + 0.5, y0 + (rows - 1 - y) * cell + 0.5, cell - 1, cell - 1), col)
    p.end()
    return pm


class BoardPainter(QtWidgets.QWidget):
    """A board to paint a form on: the left button paints the chosen color,
    the right one erases. cells: {(x, y up): piece or "X"}."""
    ROWS, CELL = 10, 22

    def __init__(self):
        super().__init__()
        self.cells = {}
        self.color = "T"
        self._mode = None
        self.setFixedSize(self.CELL * 10 + 1, self.CELL * self.ROWS + 1)
        self.setCursor(QtCore.Qt.CursorShape.CrossCursor)

    def set_cells(self, cells):
        self.cells = {c: v for c, v in cells.items() if c[1] < self.ROWS}
        self.update()

    def _at(self, pos):
        x, y = int(pos.x() // self.CELL), self.ROWS - 1 - int(pos.y() // self.CELL)
        return (x, y) if 0 <= x < 10 and 0 <= y < self.ROWS else None

    def _apply(self, pos):
        c = self._at(pos)
        if c is None:
            return
        if self._mode == "paint" and self.color:
            self.cells[c] = self.color
        else:
            self.cells.pop(c, None)
        self.update()

    def mousePressEvent(self, e):
        right = e.button() == QtCore.Qt.MouseButton.RightButton
        self._mode = "erase" if right or self.color is None else "paint"
        self._apply(e.position())

    def mouseMoveEvent(self, e):
        if self._mode:
            self._apply(e.position())

    def mouseReleaseEvent(self, e):
        self._mode = None

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor(20, 22, 28))
        p.setPen(QtGui.QColor(58, 62, 72))
        for k in range(11):
            p.drawLine(k * self.CELL, 0, k * self.CELL, self.height())
        for k in range(self.ROWS + 1):
            p.drawLine(0, k * self.CELL, self.width(), k * self.CELL)
        for (x, y), v in self.cells.items():
            col = QtGui.QColor(*PIECE_COLORS[v]) if v in PIECE_COLORS else QtGui.QColor(150, 150, 160)
            p.fillRect(x * self.CELL + 1, (self.ROWS - 1 - y) * self.CELL + 1, self.CELL - 1, self.CELL - 1, col)
        p.end()


class DeckEditor:
    """Builds the deck's cards (cards) and keeps config/practice_deck.json."""

    def __init__(self, names):
        self.lang = "ja"
        self.deck = op.load_deck()
        self.names = names
        try:
            self.wiki = json.loads(WIKI_RATES.read_text(encoding="utf-8"))["rates"]
        except (OSError, ValueError, KeyError):
            self.wiki = {}
        self.worker = None
        self._build()
        self._fill_deck()

    # --- building ---
    def _build(self):
        self.deck_card = ui.Card()
        self.mode_label = QtWidgets.QLabel()
        self.mode = QtWidgets.QComboBox()
        self.mode.addItem("", "deck")
        self.mode.addItem("", "single")
        self.mode.setCurrentIndex(max(0, self.mode.findData(self.deck.get("mode", "deck"))))
        self.mode.currentIndexChanged.connect(self._mode_changed)
        mode_row = QtWidgets.QHBoxLayout()
        mode_row.addWidget(self.mode_label)
        mode_row.addWidget(self.mode)
        mode_row.addStretch(1)
        self.single_now = QtWidgets.QLabel()
        self.single_now.setWordWrap(True)
        self.deck_list = QtWidgets.QListWidget()
        self.deck_list.setMinimumHeight(150)
        self.deck_list.currentRowChanged.connect(self._fill_forms)
        self.b_up, self.b_down, self.b_remove = QtWidgets.QPushButton(), QtWidgets.QPushButton(), QtWidgets.QPushButton()
        self.b_up.clicked.connect(lambda: self._move_opener(-1))
        self.b_down.clicked.connect(lambda: self._move_opener(1))
        self.b_remove.clicked.connect(self._remove_opener)
        self.deck_buttons = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(self.deck_buttons)
        row.setContentsMargins(0, 0, 0, 0)
        for b in (self.b_up, self.b_down, self.b_remove):
            row.addWidget(b)
        row.addStretch(1)
        self.pick = QtWidgets.QComboBox()
        self.pick.setEditable(True)
        self.pick.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        self.pick.setMaxVisibleItems(20)
        for n in self.names:
            self.pick.addItem(n, n)
        self.pick.setCurrentIndex(-1)
        comp = QtWidgets.QCompleter(self.pick.model(), self.pick)
        comp.setFilterMode(QtCore.Qt.MatchFlag.MatchContains)
        comp.setCaseSensitivity(QtCore.Qt.CaseSensitivity.CaseInsensitive)
        self.pick.setCompleter(comp)
        self.b_add = QtWidgets.QPushButton()
        self.b_add.clicked.connect(self._add_opener)
        add = QtWidgets.QHBoxLayout()
        add.addWidget(self.pick, 1)
        add.addWidget(self.b_add)
        self.mirror = QtWidgets.QCheckBox()
        self.mirror.setChecked(bool(self.deck.get("mirror", True)))
        self.mirror.toggled.connect(self._mirror_toggled)
        self.deck_card.add(mode_row)
        self.deck_card.add(self.single_now)
        self.deck_card.add(self.deck_list)
        self.deck_card.add(self.deck_buttons)
        self.deck_card.add(add)
        self.deck_card.add(self.mirror)

        self.form_card = ui.Card()
        self.form_list = QtWidgets.QListWidget()
        self.form_list.setMinimumHeight(110)
        self.form_list.itemChanged.connect(self._form_ticked)
        self.form_list.currentRowChanged.connect(self._show_form)
        self.f_up, self.f_down, self.f_delete = QtWidgets.QPushButton(), QtWidgets.QPushButton(), QtWidgets.QPushButton()
        self.f_up.clicked.connect(lambda: self._move_form(-1))
        self.f_down.clicked.connect(lambda: self._move_form(1))
        self.f_delete.clicked.connect(self._delete_form)
        frow = QtWidgets.QHBoxLayout()
        for b in (self.f_up, self.f_down, self.f_delete):
            frow.addWidget(b)
        frow.addStretch(1)
        self.form_pic = QtWidgets.QLabel()
        self.form_pic.setFixedSize(180, 90)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(self.form_list, 1)
        top.addWidget(self.form_pic, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        self.form_name = QtWidgets.QLineEdit()
        self.form_fumen = QtWidgets.QLineEdit()
        self.f_add = QtWidgets.QPushButton()
        self.f_add.clicked.connect(self._add_form)
        fadd = QtWidgets.QHBoxLayout()
        fadd.addWidget(self.form_name, 1)
        fadd.addWidget(self.form_fumen, 2)
        fadd.addWidget(self.f_add)
        self.form_error = ui.muted()
        self.form_error.setStyleSheet("color:#b42318;")
        self.form_error.setWordWrap(True)
        self.form_error.setVisible(False)
        self.form_card.add(top)
        self.form_card.add(frow)
        self.form_card.add(fadd)
        self.paint_how = ui.muted()
        self.paint_how.setWordWrap(True)
        self.painter = BoardPainter()
        self.paint_group = QtWidgets.QButtonGroup(self.form_card)
        self.paint_group.setExclusive(True)
        palette = QtWidgets.QGridLayout()
        palette.setSpacing(4)
        self.paint_buttons = {}
        for k, v in enumerate(("I", "O", "T", "S", "Z", "J", "L", "X", None)):
            b = QtWidgets.QPushButton(v or "")
            b.setCheckable(True)
            b.setFixedSize(46, 30)
            rgb = PIECE_COLORS.get(v, (150, 150, 160)) if v else (245, 245, 247)
            ink = "#111" if v != "J" and v != "T" else "#fff"
            b.setStyleSheet(f"QPushButton{{background:rgb{rgb};color:{ink};font-weight:700;border:2px solid transparent;"
                            "border-radius:5px;padding:0;}QPushButton:checked{border:2px solid #111;}")
            b.clicked.connect(lambda _=False, c=v: setattr(self.painter, "color", c))
            self.paint_group.addButton(b)
            self.paint_buttons[v] = b
            palette.addWidget(b, k // 3, k % 3)
        self.paint_buttons["T"].setChecked(True)
        self.p_add, self.p_clear, self.p_copy = QtWidgets.QPushButton(), QtWidgets.QPushButton(), QtWidgets.QPushButton()
        self.p_add.clicked.connect(self._add_painted)
        self.p_clear.clicked.connect(lambda: self.painter.set_cells({}))
        self.p_copy.clicked.connect(self._copy_form)
        side = QtWidgets.QVBoxLayout()
        side.addLayout(palette)
        side.addSpacing(6)
        for b in (self.p_copy, self.p_clear, self.p_add):
            side.addWidget(b)
        side.addStretch(1)
        paint_row = QtWidgets.QHBoxLayout()
        paint_row.addWidget(self.painter, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        paint_row.addSpacing(12)
        paint_row.addLayout(side)
        paint_row.addStretch(1)
        self.form_card.add(self.paint_how)
        self.form_card.add(paint_row)
        self.form_card.add(self.form_error)

        self.route_card = ui.Card()
        self.route_list = QtWidgets.QListWidget()
        self.route_list.setMinimumHeight(130)
        self.route_list.itemChanged.connect(self._route_ticked)
        self.r_up, self.r_down = QtWidgets.QPushButton(), QtWidgets.QPushButton()
        self.r_up.clicked.connect(lambda: self._move_route(-1))
        self.r_down.clicked.connect(lambda: self._move_route(1))
        rrow = QtWidgets.QHBoxLayout()
        rrow.addWidget(self.r_up)
        rrow.addWidget(self.r_down)
        rrow.addStretch(1)
        self.route_card.add(self.route_list)
        self.route_card.add(rrow)

        self.rate_card = ui.Card()
        self.b_calc = QtWidgets.QPushButton()
        self.b_calc.clicked.connect(self._calc)
        self.bar = QtWidgets.QProgressBar()
        self.bar.setVisible(False)
        self.result = QtWidgets.QLabel()
        self.result.setWordWrap(True)
        self.result.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        crow = QtWidgets.QHBoxLayout()
        crow.addWidget(self.b_calc)
        crow.addWidget(self.bar, 1)
        self.rate_card.add(crow)
        self.rate_card.add(self.result)
        self.cards = (self.deck_card, self.form_card, self.route_card, self.rate_card)

    def retranslate(self, lang):
        self.lang = lang if lang in TEXT else "ja"
        t = TEXT[self.lang]
        self.mode_label.setText(t["mode"])
        self.mode.setItemText(0, t["mode_deck"])
        self.mode.setItemText(1, t["mode_single"])
        for b, k in ((self.b_up, "up"), (self.b_down, "down"), (self.b_remove, "remove"),
                     (self.f_up, "up"), (self.f_down, "down"), (self.f_delete, "delete"), (self.f_add, "add"),
                     (self.r_up, "up"), (self.r_down, "down"),
                     (self.b_calc, "calc")):
            b.setText(t[k])
        self.pick.lineEdit().setPlaceholderText(t["pick"])
        self.mirror.setText(t["mirror"])
        self.form_card.setDescription(t["forms_desc"])
        self.form_name.setPlaceholderText(t["form_name"])
        self.form_fumen.setPlaceholderText(t["form_fumen"])
        self.paint_how.setText(t["paint_how"])
        self.paint_buttons["X"].setText(t["gray"])
        self.paint_buttons[None].setText(t["erase"])
        self.p_add.setText(t["paint_add"])
        self.p_clear.setText(t["paint_clear"])
        self.p_copy.setText(t["paint_copy"])
        self.route_card.setDescription(t["routes_desc"])
        self.rate_card.setTitle(t["rates"])
        self.rate_card.setDescription(t["rates_desc"])
        self._fill_deck(keep=True)

    # --- the deck ---
    def _save(self):
        op.save_deck(self.deck)
        if self.result.text() and not self.result.property("stale"):
            self.result.setText(TEXT[self.lang]["stale"])
            self.result.setProperty("stale", True)

    def _single(self):
        return self.deck.get("mode") == "single"

    def _mode_changed(self, *_):
        self.deck["mode"] = self.mode.currentData()
        self._save()
        self._fill_deck(keep=True)

    def _show_mode(self):
        t = TEXT[self.lang]
        single = self._single()
        self.deck_card.setTitle(t["single"] if single else t["deck"])
        self.deck_card.setDescription(t["single_desc"] if single else t["deck_desc"])
        self.b_add.setText(t["use"] if single else t["add"])
        self.deck_list.setVisible(not single)
        self.deck_buttons.setVisible(not single)
        self.single_now.setVisible(single)
        name = self.deck.get("single")
        self.single_now.setText(t["single_now"].format(name) if name else t["single_none"])

    def _fill_deck(self, keep=False):
        self._show_mode()
        row = self.deck_list.currentRow() if keep else 0
        self.deck_list.blockSignals(True)
        self.deck_list.clear()
        for k, e in enumerate(self.deck["openers"]):
            self.deck_list.addItem(f"{k + 1}. {e['name']}")
        if not self.deck["openers"]:
            item = QtWidgets.QListWidgetItem(TEXT[self.lang]["empty"])
            item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
            self.deck_list.addItem(item)
        self.deck_list.blockSignals(False)
        if self.deck["openers"]:
            self.deck_list.setCurrentRow(max(0, min(row, len(self.deck["openers"]) - 1)))
        self._fill_forms()

    def _current(self):
        if self._single():
            return op.single_entry(self.deck, keep=True)
        r = self.deck_list.currentRow()
        return self.deck["openers"][r] if 0 <= r < len(self.deck["openers"]) else None

    def _add_opener(self):
        name = self.pick.currentText().strip()
        if name not in self.names:
            return
        if self._single():
            self.deck["single"] = name
            self._save()
            self._fill_deck()
        else:
            if any(e["name"] == name for e in self.deck["openers"]):
                return
            # (forms it was given as テンプレ単体 come along)
            self.deck["openers"].append(self.deck.get("single_forms", {}).pop(name, None) or op.new_entry(name))
            self._save()
            self._fill_deck()
            self.deck_list.setCurrentRow(len(self.deck["openers"]) - 1)
        self.pick.setCurrentIndex(-1)
        self.pick.setEditText("")

    def _move_opener(self, d):
        r = self.deck_list.currentRow()
        o = self.deck["openers"]
        if 0 <= r < len(o) and 0 <= r + d < len(o):
            o[r], o[r + d] = o[r + d], o[r]
            self._save()
            self._fill_deck()
            self.deck_list.setCurrentRow(r + d)

    def _remove_opener(self):
        r = self.deck_list.currentRow()
        if 0 <= r < len(self.deck["openers"]):
            gone = self.deck["openers"].pop(r)
            if gone["name"] == self.deck.get("single"):     # still the one of テンプレ単体
                self.deck.setdefault("single_forms", {})[gone["name"]] = gone
            self._save()
            self._fill_deck()

    def _mirror_toggled(self, on):
        self.deck["mirror"] = bool(on)
        self._save()
        self._show_form()

    # --- the forms of the opener picked ---
    def _fill_forms(self, *_):
        e = self._current()
        t = TEXT[self.lang]
        self.form_card.setTitle(t["forms"].format(e["name"]) if e else t["forms_none"])
        self.form_list.blockSignals(True)
        self.form_list.clear()
        for f in (e["forms"] if e else []):
            item = QtWidgets.QListWidgetItem(f.get("name") or "")
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Checked if f.get("on", True) else QtCore.Qt.CheckState.Unchecked)
            self.form_list.addItem(item)
        self.form_list.blockSignals(False)
        for w in (self.form_list, self.f_up, self.f_down, self.f_delete, self.form_name, self.form_fumen, self.f_add,
                  self.p_add, self.p_copy):
            w.setEnabled(e is not None)
        if e:
            self.form_list.setCurrentRow(0)
        self._show_form()
        self._fill_routes()

    # --- the wiki's routes of the opener picked ---
    def _fill_routes(self, row=0):
        e = self._current()
        t = TEXT[self.lang]
        self.route_card.setTitle(t["routes"].format(e["name"]) if e else t["routes_none"])
        routes = op.entry_routes(e) if e else []
        self.route_list.blockSignals(True)
        self.route_list.clear()
        for r in routes:
            item = QtWidgets.QListWidgetItem(r["name"])
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Checked if r["on"] else QtCore.Qt.CheckState.Unchecked)
            self.route_list.addItem(item)
        if e and not routes:
            item = QtWidgets.QListWidgetItem(t["routes_empty"])
            item.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
            self.route_list.addItem(item)
        self.route_list.blockSignals(False)
        if routes:
            self.route_list.setCurrentRow(max(0, min(row, len(routes) - 1)))
        for w in (self.r_up, self.r_down):
            w.setEnabled(bool(routes))

    def _store_routes(self, e, routes):
        e["routes"] = [{"name": r["name"], "on": r["on"]} for r in routes]
        self._save()

    def _route_ticked(self, item):
        e = self._current()
        r = self.route_list.row(item)
        routes = op.entry_routes(e) if e else []
        if 0 <= r < len(routes):
            routes[r]["on"] = item.checkState() == QtCore.Qt.CheckState.Checked
            self._store_routes(e, routes)

    def _move_route(self, d):
        e = self._current()
        r = self.route_list.currentRow()
        routes = op.entry_routes(e) if e else []
        if 0 <= r < len(routes) and 0 <= r + d < len(routes):
            routes[r], routes[r + d] = routes[r + d], routes[r]
            self._store_routes(e, routes)
            self._fill_routes(r + d)

    def _show_form(self, *_):
        e = self._current()
        r = self.form_list.currentRow()
        target = None
        if e and 0 <= r < len(e["forms"]):
            ts = op.form_targets(e["name"], e["forms"][r], False)
            target = ts[0] if ts else None
            self.f_delete.setEnabled(e["forms"][r].get("source") != op.WIKI_FORM)
        self.form_pic.setPixmap(draw_targets(target))

    def _form_ticked(self, item):
        e = self._current()
        r = self.form_list.row(item)
        if e and 0 <= r < len(e["forms"]):
            e["forms"][r]["on"] = item.checkState() == QtCore.Qt.CheckState.Checked
            self._save()

    def _move_form(self, d):
        e = self._current()
        r = self.form_list.currentRow()
        if e and 0 <= r < len(e["forms"]) and 0 <= r + d < len(e["forms"]):
            f = e["forms"]
            f[r], f[r + d] = f[r + d], f[r]
            self._save()
            self._fill_forms()
            self.form_list.setCurrentRow(r + d)

    def _delete_form(self):
        e = self._current()
        r = self.form_list.currentRow()
        if e and 0 <= r < len(e["forms"]) and e["forms"][r].get("source") != op.WIKI_FORM:
            del e["forms"][r]
            self._save()
            self._fill_forms()

    def _add_form(self):
        e = self._current()
        t = TEXT[self.lang]
        fumen = self.form_fumen.text().strip()
        if "?" in fumen and "@" in fumen:
            fumen = fumen[fumen.index("?") + 1:]   # a whole fumen.zui.jp link
        try:
            ts = op.fumen_targets(fumen)
        except Exception:
            ts = None
        if ts is None:
            self.form_error.setText(t["bad_fumen"])
            self.form_error.setVisible(True)
            return
        if not ts or any(len(x.cells) % 4 for x in ts):
            self.form_error.setText(t["no_shape"])
            self.form_error.setVisible(True)
            return
        self.form_error.setVisible(False)
        e["forms"].append({"name": self.form_name.text().strip() or f"#{len(e['forms']) + 1}", "fumen": fumen,
                           "on": True})
        self._save()
        self._fill_forms()
        self.form_list.setCurrentRow(len(e["forms"]) - 1)
        self.form_name.clear()
        self.form_fumen.clear()

    def _add_painted(self):
        e = self._current()
        if not e:
            return
        rows = op.paint_rows(self.painter.cells)
        why = op.paint_problem(rows)
        if why:
            self.form_error.setText(TEXT[self.lang]["p_" + why])
            self.form_error.setVisible(True)
            return
        self.form_error.setVisible(False)
        e["forms"].append({"name": self.form_name.text().strip() or f"#{len(e['forms']) + 1}", "paint": rows, "on": True})
        self._save()
        self._fill_forms()
        self.form_list.setCurrentRow(len(e["forms"]) - 1)
        self.form_name.clear()

    def _copy_form(self):
        """The selected form onto the board, to make another from it."""
        e = self._current()
        r = self.form_list.currentRow()
        if not e or not 0 <= r < len(e["forms"]):
            return
        form = e["forms"][r]
        if form.get("paint"):
            self.painter.set_cells(op.paint_cells(form["paint"]))
            return
        ts = op.form_targets(e["name"], form, False)
        if ts:
            colors = ts[0].colors or {}
            self.painter.set_cells({c: colors.get(c, "X") for c in ts[0].cells})

    # --- rates ---
    def _calc(self):
        if self.worker is not None and self.worker.isRunning():
            return
        cands = op.candidates(self.deck)
        if not cands:
            return
        self.b_calc.setEnabled(False)
        self.b_calc.setText(TEXT[self.lang]["calcing"])
        self.bar.setVisible(True)
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.worker = RateWorker(cands)
        self.worker.progress.connect(lambda d, n: self.bar.setValue(int(100 * d / max(1, n))))
        self.worker.finished_rates.connect(self._show_rates)
        self.worker.start()

    def _show_rates(self, r):
        t = TEXT[self.lang]
        self.b_calc.setEnabled(True)
        self.b_calc.setText(t["calc"])
        self.bar.setVisible(False)
        self.result.setProperty("stale", False)
        if r is None:
            self.result.setText(t["failed"])
            return
        lines = [t["total_single" if self._single() else "total"].format(r["total"] * 100, r["none"] * 100)]
        for k, (o, f, picked, alone) in enumerate(r["by"]):
            line = t["row"].format(k + 1, o, f, picked * 100, alone * 100)
            w = self.wiki.get(o)
            if w and f == "Wiki":
                line += t["wiki"].format(f"{w[0]:.2f}%", f"{w[1]:.2f}%" if w[1] is not None else "-")
            lines.append(line)
        self.result.setText("\n".join(lines))

    def stop(self):
        if self.worker is not None:
            self.worker.wait(100)
