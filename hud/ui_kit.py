"""Building blocks of the settings window's look (user's request: easier to
follow, a fresh design — see the mockup decided on 2026-11-04): a navy menu
down the left, white cards, switches for on/off, rows of choice buttons.

Kept as plain Qt widgets with one style sheet, so the window costs nothing
while closed and opens as fast as before.
"""
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtSvg, QtWidgets

ASSETS = (Path(__file__).resolve().parent.parent / "assets" / "ui").as_posix()

NAVY = "#141a2e"
NAVY_SELECTED = "#2a3558"
NAV_TEXT = "#c9d1e6"
PAGE_BG = "#f3f4f8"
CARD_BORDER = "#e1e4ee"
TEXT = "#141a2e"
MUTED = "#4f5670"     # 4.5:1 or more on white and on the page background
ACCENT = "#2f6fd6"
ACCENT_SOFT = "#eaf1fd"
LINE = "#c9cfdd"

STYLE = f"""
QWidget#settingsRoot {{ background: {PAGE_BG}; }}
QWidget#settingsRoot, QWidget#settingsRoot QWidget {{ font-family: "Yu Gothic UI", "Meiryo UI", "Segoe UI"; font-size: 13px; color: {TEXT}; }}
QScrollArea#page, QScrollArea#page > QWidget > QWidget#pageInner {{ background: {PAGE_BG}; border: none; }}
QFrame#card {{ background: #ffffff; border: 1px solid {CARD_BORDER}; border-radius: 12px; }}
QFrame#card QLabel {{ background: transparent; }}
QWidget#settingsRoot QLabel#pageTitle {{ font-size: 20px; font-weight: 700; }}
QWidget#settingsRoot QLabel#cardTitle {{ font-size: 15px; font-weight: 700; }}
QWidget#settingsRoot QLabel#muted {{ color: {MUTED}; font-size: 12px; }}
QPushButton {{ background: #ffffff; border: 1px solid {LINE}; border-radius: 8px; padding: 6px 12px; }}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: #9aa0b2; border-color: #e1e4ee; }}
QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT}; color: #ffffff; font-weight: 700; }}
QPushButton#primary:hover {{ background: #255bb4; }}
QPushButton#primary:checked {{ background: #16a34a; border-color: #16a34a; }}
QPushButton#seg {{ border: none; border-radius: 7px; padding: 5px 12px; background: transparent; color: {MUTED}; }}
QPushButton#seg:checked {{ background: #ffffff; color: {TEXT}; font-weight: 700; }}
QPushButton#seg:disabled {{ color: #9aa0b2; }}
QWidget#segBar {{ background: #e8ebf2; border-radius: 9px; }}
QComboBox, QSpinBox, QLineEdit {{ background: #ffffff; border: 1px solid {LINE}; border-radius: 7px; padding: 4px 8px; min-height: 20px; }}
QComboBox:focus, QSpinBox:focus, QLineEdit:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url({ASSETS}/chevron_down.svg); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: #ffffff; border: 1px solid {LINE}; selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT}; }}
QSpinBox {{ padding-right: 22px; }}
QSpinBox::up-button, QSpinBox::down-button {{ border: none; width: 20px; background: transparent; }}
QSpinBox::up-arrow {{ image: url({ASSETS}/chevron_up.svg); width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: url({ASSETS}/chevron_down.svg); width: 10px; height: 10px; }}
QCheckBox::indicator, QListWidget::indicator {{ width: 16px; height: 16px; border: 1.5px solid #9aa3b8; border-radius: 4px; background: #ffffff; }}
QCheckBox::indicator:checked, QListWidget::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url({ASSETS}/check.svg); }}
QCheckBox::indicator:disabled {{ background: #eef0f5; border-color: #d4d8e2; }}
QListWidget {{ background: #ffffff; border: 1px solid {CARD_BORDER}; border-radius: 8px; padding: 2px; }}
QListWidget::item {{ padding: 4px 6px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {ACCENT_SOFT}; color: {TEXT}; }}
QSlider::groove:horizontal {{ height: 6px; background: #dde1ea; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: #ffffff; border: 2px solid {ACCENT}; width: 14px; height: 14px; margin: -6px 0; border-radius: 9px; }}
QCheckBox {{ spacing: 8px; background: transparent; }}
QTableWidget {{ background: #ffffff; border: 1px solid {CARD_BORDER}; border-radius: 8px; gridline-color: #eceef4; }}
QHeaderView::section {{ background: #f6f7fa; border: none; border-bottom: 1px solid #eceef4; padding: 4px 6px; font-weight: 700; }}
QToolButton#designCard {{ background: #ffffff; border: 2px solid {CARD_BORDER}; border-radius: 10px; padding: 4px; }}
QToolButton#designCard:hover {{ border-color: #9dbbec; }}
QToolButton#designCard:checked {{ background: {ACCENT_SOFT}; border-color: {ACCENT}; font-weight: 700; }}
QToolButton#pad {{ background: #ffffff; border: 1px solid {LINE}; border-radius: 8px; font-size: 15px; }}
QToolButton#pad:hover {{ border-color: {ACCENT}; }}
QListWidget#nav {{ background: {NAVY}; border: none; border-radius: 0; padding: 0; outline: none; }}
QListWidget#nav::item {{ color: {NAV_TEXT}; padding: 9px 10px; margin: 1px 10px; border-radius: 8px; }}
QListWidget#nav::item:selected {{ background: {NAVY_SELECTED}; color: #ffffff; }}
QListWidget#nav::item:hover:!selected {{ background: #1e2742; }}
QWidget#navPanel {{ background: {NAVY}; }}
QWidget#navPanel QLabel {{ color: #ffffff; background: transparent; }}
QWidget#settingsRoot QLabel#navVersion {{ color: #8f98b3; font-size: 11px; }}
QWidget#settingsRoot QWidget#navPanel QLabel {{ color: #ffffff; }}
"""

# menu icons: outline drawings, white-ish on the navy menu
_ICONS = {
    "home": '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/>',
    "items": '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="9" cy="6" r="1.5" fill="C"/>'
             '<circle cx="15" cy="12" r="1.5" fill="C"/><circle cx="7" cy="18" r="1.5" fill="C"/>',
    "look": '<circle cx="12" cy="12" r="9"/><circle cx="8" cy="10" r="1.3" fill="C"/><circle cx="12" cy="7.5" r="1.3" fill="C"/>'
            '<circle cx="16" cy="10" r="1.3" fill="C"/><path d="M12 21c-1.5 0-2-1-2-2s1-2 2.5-2H15"/>',
    "place": '<path d="M12 3v18M3 12h18M12 3l-3 3M12 3l3 3M12 21l-3-3M12 21l3-3M3 12l3-3M3 12l3 3M21 12l-3-3M21 12l-3 3"/>',
    "stats": '<path d="M12 3a9 9 0 1 0 9 9h-9z"/><path d="M15 3.5A9 9 0 0 1 20.5 9H15z"/>',
    "obs": '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3"/>',
    "other": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>',
    "rating": '<path d="M3 17l5-5 4 3 8-8"/><path d="M15 7h5v5"/>',
}


def icon(name, color=NAV_TEXT, size=18):
    body = _ICONS[name].replace('"C"', f'"{color}"')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{body}</svg>')
    renderer = QtSvg.QSvgRenderer(QtCore.QByteArray(svg.encode()))
    ratio = 2
    img = QtGui.QImage(size * ratio, size * ratio, QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QtCore.Qt.GlobalColor.transparent)
    p = QtGui.QPainter(img)
    renderer.render(p)
    p.end()
    pm = QtGui.QPixmap.fromImage(img)
    pm.setDevicePixelRatio(ratio)
    return QtGui.QIcon(pm)


def muted(text=""):
    lab = QtWidgets.QLabel(text)
    lab.setObjectName("muted")
    lab.setWordWrap(True)
    return lab


class Switch(QtWidgets.QCheckBox):
    """An on/off switch (a QCheckBox underneath, so isChecked / setChecked /
    toggled work as before), drawn as a pill with a knob."""

    W, H = 40, 22

    def sizeHint(self):
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self.text()) + 10 if self.text() else 0
        return QtCore.QSize(self.W + text_w + 2, max(self.H + 2, fm.height() + 4))

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        enabled = self.isEnabled()
        y = (self.height() - self.H) / 2
        track = QtGui.QColor(ACCENT if on else "#c3c9d6")
        if not enabled:
            track.setAlphaF(0.45)
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QtCore.QRectF(1, y, self.W, self.H), self.H / 2, self.H / 2)
        knob = self.H - 6
        x = 1 + (self.W - knob - 3 if on else 3)
        p.setBrush(QtGui.QColor("#ffffff"))
        p.drawEllipse(QtCore.QRectF(x, y + 3, knob, knob))
        if self.hasFocus():
            p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            p.setPen(QtGui.QPen(QtGui.QColor(ACCENT), 1.5))
            p.drawRoundedRect(QtCore.QRectF(0, y - 1, self.W + 2, self.H + 2), self.H / 2 + 1, self.H / 2 + 1)
        if self.text():
            p.setPen(QtGui.QColor(TEXT if enabled else "#9aa0b2"))
            p.drawText(QtCore.QRectF(self.W + 10, 0, self.width() - self.W - 10, self.height()),
                       QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft, self.text())


class Segmented(QtWidgets.QWidget):
    """A row of choice buttons, one picked. Answers like a QComboBox
    (addItem / setItemText / findData / currentData / setCurrentIndex /
    currentIndex / count / currentIndexChanged), so the code using the old
    dropdowns works unchanged."""

    currentIndexChanged = QtCore.pyqtSignal(int)

    def __init__(self, parent=None, wrap=False):
        super().__init__(parent)
        self.setObjectName("segBar")
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self._box = QtWidgets.QHBoxLayout(self)
        self._box.setContentsMargins(3, 3, 3, 3)
        self._box.setSpacing(2)
        self._group = QtWidgets.QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.idClicked.connect(self._clicked)
        self._data = []
        self._index = -1
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Fixed)

    def addItem(self, text, data=None):
        b = QtWidgets.QPushButton(text)
        b.setObjectName("seg")
        b.setCheckable(True)
        b.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._group.addButton(b, len(self._data))
        self._box.addWidget(b)
        self._data.append(data)
        if self._index < 0:
            self._set(0, emit=False)

    def setItemText(self, i, text):
        self._group.button(i).setText(text)

    def itemText(self, i):
        return self._group.button(i).text()

    def count(self):
        return len(self._data)

    def findData(self, data):
        try:
            return self._data.index(data)
        except ValueError:
            return -1

    def currentData(self):
        return self._data[self._index] if 0 <= self._index < len(self._data) else None

    def currentIndex(self):
        return self._index

    def setCurrentIndex(self, i):
        self._set(i, emit=True)

    def _set(self, i, emit):
        if not 0 <= i < len(self._data):
            return
        self._group.button(i).setChecked(True)
        if i != self._index:
            self._index = i
            if emit:
                self.currentIndexChanged.emit(i)

    def _clicked(self, i):
        self._set(i, emit=True)


class Card(QtWidgets.QFrame):
    """A white card: a title (and a line under it), an optional switch on the
    right of the title, and a body that's hidden while the switch is off."""

    def __init__(self, switch=None, collapse=True):
        super().__init__()
        self.setObjectName("card")
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(10)
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(12)
        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(2)
        self.title = QtWidgets.QLabel()
        self.title.setObjectName("cardTitle")
        self.title.setVisible(False)   # until it gets a title
        self.desc = muted()
        self.desc.setVisible(False)
        titles.addWidget(self.title)
        titles.addWidget(self.desc)
        head.addLayout(titles, 1)
        self.switch = switch
        if switch is not None:
            head.addWidget(switch, 0, QtCore.Qt.AlignmentFlag.AlignTop)
            if collapse:
                switch.toggled.connect(self._fold)
        outer.addLayout(head)
        self.body = QtWidgets.QWidget()
        self.body.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.body_layout = QtWidgets.QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(10)
        outer.addWidget(self.body)
        self._collapse = collapse and switch is not None

    def setTitle(self, text):      # (named as a QGroupBox's, which these cards replace)
        self.title.setText(text)
        self.title.setVisible(bool(text))

    def setDescription(self, text):
        self.desc.setText(text)
        self.desc.setVisible(bool(text))

    def add(self, widget_or_layout, stretch=0):
        if isinstance(widget_or_layout, QtWidgets.QLayout):
            self.body_layout.addLayout(widget_or_layout, stretch)
        else:
            self.body_layout.addWidget(widget_or_layout, stretch)
        return widget_or_layout

    def sync(self):
        if self._collapse:
            self._fold(self.switch.isChecked())

    def _fold(self, on):
        self.body.setVisible(bool(on) and self.body_layout.count() > 0)


def row(label_widget, field, label_w=110):
    """A label on the left (fixed width) and its control on the right."""
    box = QtWidgets.QHBoxLayout()
    box.setSpacing(12)
    label_widget.setFixedWidth(label_w)
    box.addWidget(label_widget)
    if isinstance(field, QtWidgets.QLayout):
        box.addLayout(field, 1)
    else:
        box.addWidget(field, 1)
    return box


def page(title_label, *cards):
    """One page: its title and its cards, scrolling when taller than the window."""
    inner = QtWidgets.QWidget()
    inner.setObjectName("pageInner")
    lay = QtWidgets.QVBoxLayout(inner)
    lay.setContentsMargins(24, 20, 24, 20)
    lay.setSpacing(14)
    title_label.setObjectName("pageTitle")
    lay.addWidget(title_label)
    for c in cards:
        lay.addWidget(c)
    lay.addStretch(1)
    area = QtWidgets.QScrollArea()
    area.setObjectName("page")
    area.setWidgetResizable(True)
    area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(inner)
    return area


class SideNav(QtWidgets.QWidget):
    """The navy menu down the left and the page beside it. Answers like the
    QTabWidget it replaces (addTab / setTabText / setCurrentIndex / count /
    widget / currentIndex)."""

    currentChanged = QtCore.pyqtSignal(int)

    def __init__(self, brand, version_text=""):
        super().__init__()
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        panel = QtWidgets.QWidget()
        panel.setObjectName("navPanel")
        panel.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        panel.setFixedWidth(200)
        pl = QtWidgets.QVBoxLayout(panel)
        pl.setContentsMargins(0, 16, 0, 12)
        pl.setSpacing(8)
        head = QtWidgets.QHBoxLayout()
        head.setContentsMargins(18, 0, 12, 8)
        logo = QtWidgets.QLabel()
        logo.setPixmap(brand.pixmap(28, 28))
        name = QtWidgets.QLabel("PPTetrics")
        name.setStyleSheet("font-size: 16px; font-weight: 700;")
        head.addWidget(logo)
        head.addWidget(name, 1)
        pl.addLayout(head)
        self.list = QtWidgets.QListWidget()
        self.list.setObjectName("nav")
        self.list.setIconSize(QtCore.QSize(18, 18))
        self.list.setFocusPolicy(QtCore.Qt.FocusPolicy.TabFocus)
        self.list.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.currentRowChanged.connect(self._row_changed)
        pl.addWidget(self.list, 1)
        self.version = QtWidgets.QLabel(version_text)
        self.version.setObjectName("navVersion")
        self.version.setContentsMargins(22, 0, 0, 0)
        pl.addWidget(self.version)
        lay.addWidget(panel)
        right = QtWidgets.QWidget()
        self._right = QtWidgets.QVBoxLayout(right)
        self._right.setContentsMargins(0, 0, 0, 0)
        self._right.setSpacing(0)
        self.stack = QtWidgets.QStackedWidget()
        self._right.addWidget(self.stack, 1)
        lay.addWidget(right, 1)

    def set_footer(self, widget):
        """A bar under every page (the note, reset, close)."""
        self._right.addWidget(widget)

    def addTab(self, widget, text, icon_name=None):
        it = QtWidgets.QListWidgetItem(text)
        if icon_name:
            it.setIcon(icon(icon_name))
        it.setSizeHint(QtCore.QSize(180, 40))
        self.list.addItem(it)
        self.stack.addWidget(widget)
        if self.list.currentRow() < 0:
            self.list.setCurrentRow(0)
        return self.stack.count() - 1

    def setTabText(self, i, text):
        self.list.item(i).setText(text)

    def tabText(self, i):
        return self.list.item(i).text()

    def setCurrentIndex(self, i):
        self.list.setCurrentRow(i)

    def currentIndex(self):
        return self.list.currentRow()

    def count(self):
        return self.stack.count()

    def widget(self, i):
        return self.stack.widget(i)

    def _row_changed(self, i):
        self.stack.setCurrentIndex(i)
        self.currentChanged.emit(i)
