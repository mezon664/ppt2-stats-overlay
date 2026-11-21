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
           "form_name": "派生の名前（理想形など）", "form_fumen": "テト譜（v115@…）", "delete": "削除",
           "paint_how": "盤面で作る：色を選んで左ドラッグで塗り、右ドラッグで消します。灰色はどのミノでも入る場所です。",
           "paint_add": "塗った形を追加", "paint_clear": "全部消す", "paint_copy": "選んだ派生を写す", "gray": "灰", "erase": "消",
           "p_empty": "盤面にミノを塗ってください。", "p_count": "マスの数が合いません（偶数にしてください）。",
           "p_shape": "色を塗ったマスがミノの形になっていません。",
           "bad_fumen": "このテト譜は読めませんでした（テト譜の v115@ から後ろを貼ってください）。",
           "no_shape": "この形は 4 の倍数のマスでないか、置けない形でした。",
           "routes": "2巡目以降の派生：{}", "routes_none": "2巡目以降の派生",
           "routes_desc": "テンプレを組んだあとの案内です。最初は、次のミノ順を最少の個数で覆う「最少パターン」だけオンです。理想形や準理想形などは、テト譜か"
                          "盤面の色塗りで自分で追加できます。上の派生ほど優先し、チェックを外した派生は使いません。",
           "mine": "★ {}", "own_name": "自分の派生", "paint_base": "テンプレの形を写す", "p_far": "このテンプレの形から続く盤面になっていません。",
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
           "form_name": "Route name", "form_fumen": "Fumen (v115@…)", "delete": "Delete",
           "paint_how": "Paint it: pick a color, drag with the left button to paint, the right to erase. Gray: any piece.",
           "paint_add": "Add this shape", "paint_clear": "Clear", "paint_copy": "Copy the selected route", "gray": "Any",
           "erase": "Erase",
           "p_empty": "Paint some pieces on the board.", "p_count": "The number of cells doesn't add up (it must be even).",
           "p_shape": "The colored cells don't make pieces.",
           "bad_fumen": "This fumen couldn't be read (paste from v115@ on).",
           "no_shape": "This shape isn't whole pieces, or can't be built.",
           "routes": "Routes after the opener: {}", "routes_none": "Routes after the opener",
           "routes_desc": "What's guided after the opener. At first only the fewest boards covering the next bag are on. Add your own "
                          "(ideal, near-ideal…) by fumen or by painting. Top first; unticked ones aren't used.",
           "mine": "★ {}", "own_name": "My route", "paint_base": "Copy the opener", "p_far": "This board doesn't go on from the opener.",
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
    ROWS, CELL = 14, 22

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
        self.deck_list.currentRowChanged.connect(self._fill_routes)
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

        self.route_card = ui.Card()
        self.route_list = QtWidgets.QListWidget()
        self.route_list.setMinimumHeight(170)
        self.route_list.itemChanged.connect(self._route_ticked)
        self.route_list.currentRowChanged.connect(self._show_route)
        self.route_pic = QtWidgets.QLabel()
        self.route_pic.setFixedSize(180, 120)
        rtop = QtWidgets.QHBoxLayout()
        rtop.addWidget(self.route_list, 1)
        rtop.addWidget(self.route_pic, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        self.r_up, self.r_down, self.r_delete = QtWidgets.QPushButton(), QtWidgets.QPushButton(), QtWidgets.QPushButton()
        self.r_up.clicked.connect(lambda: self._move_route(-1))
        self.r_down.clicked.connect(lambda: self._move_route(1))
        self.r_delete.clicked.connect(self._delete_route)
        rrow = QtWidgets.QHBoxLayout()
        for b in (self.r_up, self.r_down, self.r_delete):
            rrow.addWidget(b)
        rrow.addStretch(1)
        self.form_name = QtWidgets.QLineEdit()
        self.form_fumen = QtWidgets.QLineEdit()
        self.f_add = QtWidgets.QPushButton()
        self.f_add.clicked.connect(self._add_fumen)
        fadd = QtWidgets.QHBoxLayout()
        fadd.addWidget(self.form_name, 1)
        fadd.addWidget(self.form_fumen, 2)
        fadd.addWidget(self.f_add)
        self.form_error = ui.muted()
        self.form_error.setStyleSheet("color:#b42318;")
        self.form_error.setWordWrap(True)
        self.form_error.setVisible(False)
        self.paint_how = ui.muted()
        self.paint_how.setWordWrap(True)
        self.painter = BoardPainter()
        self.paint_group = QtWidgets.QButtonGroup(self.route_card)
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
        self.p_add, self.p_clear, self.p_copy, self.p_base = (QtWidgets.QPushButton(), QtWidgets.QPushButton(),
                                                              QtWidgets.QPushButton(), QtWidgets.QPushButton())
        self.p_add.clicked.connect(self._add_painted)
        self.p_clear.clicked.connect(lambda: self.painter.set_cells({}))
        self.p_copy.clicked.connect(self._copy_route)
        self.p_base.clicked.connect(self._copy_opener)
        side = QtWidgets.QVBoxLayout()
        side.addLayout(palette)
        side.addSpacing(6)
        for b in (self.p_base, self.p_copy, self.p_clear, self.p_add):
            side.addWidget(b)
        side.addStretch(1)
        paint_row = QtWidgets.QHBoxLayout()
        paint_row.addWidget(self.painter, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        paint_row.addSpacing(12)
        paint_row.addLayout(side)
        paint_row.addStretch(1)
        self.route_card.add(rtop)
        self.route_card.add(rrow)
        self.route_card.add(fadd)
        self.route_card.add(self.paint_how)
        self.route_card.add(paint_row)
        self.route_card.add(self.form_error)

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
        self.cards = (self.deck_card, self.route_card, self.rate_card)

    def retranslate(self, lang):
        self.lang = lang if lang in TEXT else "ja"
        t = TEXT[self.lang]
        self.mode_label.setText(t["mode"])
        self.mode.setItemText(0, t["mode_deck"])
        self.mode.setItemText(1, t["mode_single"])
        for b, k in ((self.b_up, "up"), (self.b_down, "down"), (self.b_remove, "remove"),
                     (self.f_add, "add"), (self.r_up, "up"), (self.r_down, "down"), (self.r_delete, "delete"),
                     (self.b_calc, "calc")):
            b.setText(t[k])
        self.pick.lineEdit().setPlaceholderText(t["pick"])
        self.mirror.setText(t["mirror"])
        self.form_name.setPlaceholderText(t["form_name"])
        self.form_fumen.setPlaceholderText(t["form_fumen"])
        self.paint_how.setText(t["paint_how"])
        self.paint_buttons["X"].setText(t["gray"])
        self.paint_buttons[None].setText(t["erase"])
        self.p_add.setText(t["paint_add"])
        self.p_clear.setText(t["paint_clear"])
        self.p_copy.setText(t["paint_copy"])
        self.p_base.setText(t["paint_base"])
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
        self._fill_routes()

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

    # --- the routes of the opener picked: the wiki's and your own ---
    def _fill_routes(self, row=0):
        row = row if isinstance(row, int) and row >= 0 else 0
        e = self._current()
        t = TEXT[self.lang]
        self.route_card.setTitle(t["routes"].format(e["name"]) if e else t["routes_none"])
        routes = op.entry_routes(e) if e else []
        self.route_list.blockSignals(True)
        self.route_list.clear()
        for r in routes:
            item = QtWidgets.QListWidgetItem(t["mine"].format(r["name"]) if r.get("own") else r["name"])
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
        for w in (self.r_up, self.r_down, self.p_copy):
            w.setEnabled(bool(routes))
        for w in (self.form_name, self.form_fumen, self.f_add, self.p_add, self.p_base):
            w.setEnabled(e is not None)
        self._show_route()

    def _route_at(self):
        e = self._current()
        routes = op.entry_routes(e) if e else []
        r = self.route_list.currentRow()
        return e, routes, r if 0 <= r < len(routes) else None

    def _show_route(self, *_):
        e, routes, r = self._route_at()
        target = None
        if r is not None:
            try:
                ts = op.route_targets(routes[r])
                target = ts[-1] if ts else None
            except Exception:
                target = None
        self.r_delete.setEnabled(r is not None and bool(routes[r].get("own")))
        self.route_pic.setPixmap(draw_targets(target, 180, 120))

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
        e, routes, r = self._route_at()
        if r is not None and 0 <= r + d < len(routes):
            routes[r], routes[r + d] = routes[r + d], routes[r]
            self._store_routes(e, routes)
            self._fill_routes(r + d)

    def _delete_route(self):
        e, routes, r = self._route_at()
        if r is None or not routes[r].get("own"):
            return
        name = routes[r]["name"]
        e["own_routes"] = [x for x in e.get("own_routes", []) if x["name"] != name]
        self._store_routes(e, routes[:r] + routes[r + 1:])
        self._fill_routes(r)

    def _error(self, key):
        self.form_error.setText(TEXT[self.lang][key])
        self.form_error.setVisible(True)

    def _add_route(self, e, data, targets):
        """A route of yours, on top of the list (its name kept unique)."""
        why = op.route_problem(e["name"], targets)
        if why:
            self._error("p_" + why)
            return False
        self.form_error.setVisible(False)
        routes = op.entry_routes(e)
        taken = {r["name"] for r in routes}
        base = self.form_name.text().strip() or TEXT[self.lang]["own_name"]
        name, k = base, 2
        while name in taken:
            name, k = f"{base} {k}", k + 1
        e.setdefault("own_routes", []).append(dict(data, name=name))
        self._store_routes(e, [dict(data, name=name, on=True, own=True)] + routes)
        self._fill_routes(0)
        self.form_name.clear()
        return True

    def _add_fumen(self):
        e = self._current()
        if not e:
            return
        fumen = self.form_fumen.text().strip()
        if "?" in fumen and "@" in fumen:
            fumen = fumen[fumen.index("?") + 1:]   # a whole fumen.zui.jp link
        try:
            targets = op.route_points(fumen)
        except Exception:
            self._error("bad_fumen")
            return
        if self._add_route(e, {"fumen": fumen}, targets):
            self.form_fumen.clear()

    def _add_painted(self):
        e = self._current()
        if not e:
            return
        rows = op.paint_rows(self.painter.cells)
        self._add_route(e, {"paint": rows}, op.route_targets({"paint": rows}) if rows else [])

    def _copy_opener(self):
        """The opener as it stands after its T-spin, in gray, to build on."""
        e = self._current()
        if not e:
            return
        shapes = op.opener_shapes(e["name"])
        if shapes:
            self.painter.set_cells({c: "X" for c in op.after_clear(shapes[0]) or shapes[0]})

    def _copy_route(self):
        """The selected route's last board, to make another from it."""
        e, routes, r = self._route_at()
        if r is None:
            return
        ts = op.route_targets(routes[r])
        if ts:
            colors = ts[-1].colors or {}
            self.painter.set_cells({c: colors.get(c, "X") for c in ts[-1].cells})

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
