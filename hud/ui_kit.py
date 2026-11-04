"""Building blocks of the settings window's look (user's request: easier to
follow, a fresh design — see the mockup decided on 2026-11-04): a navy menu
down the left, white cards, switches for on/off, rows of choice buttons.

Kept as plain Qt widgets with one style sheet, so the window costs nothing
while closed and opens as fast as before.
"""
from pathlib import Path

from PyQt6 import QtCore, QtGui, QtSvg, QtWidgets

ASSETS = (Path(__file__).resolve().parent.parent / "assets" / "ui").as_posix()

# Color themes (user: the navy looked too much like every AI-made app, other
# ideas?). Each sets the menu down the left, the page behind the cards and the
# accent; the cards stay white. Chosen on その他 (ui.theme in the settings).
THEMES = {
    # the first design (2026-11-04)
    "navy": {"nav": "#141a2e", "nav_selected": "#2a3558", "nav_hover": "#1e2742", "nav_text": "#c9d1e6",
             "nav_selected_text": "#ffffff", "nav_title": "#ffffff", "nav_version": "#8f98b3", "nav_bar": "transparent",
             "page": "#f3f4f8", "card_border": "#e1e4ee", "text": "#141a2e", "muted": "#4f5670",
             "accent": "#2f6fd6", "accent_hover": "#255bb4", "accent_soft": "#eaf1fd", "on_accent": "#ffffff",
             "line": "#c9cfdd", "radius": 12},
    # like Windows' own settings: a light menu, the selected row marked by a bar
    "light": {"nav": "#eef0f3", "nav_selected": "#dfe3e8", "nav_hover": "#e6e9ed", "nav_text": "#2b2f36",
              "nav_selected_text": "#111418", "nav_title": "#111418", "nav_version": "#6b7280", "nav_bar": "#0067c0",
              "page": "#f7f8fa", "card_border": "#e3e5e8", "text": "#1b1f24", "muted": "#555c66",
              "accent": "#0067c0", "accent_hover": "#00559e", "accent_soft": "#e6f0fa", "on_accent": "#ffffff",
              "line": "#cdd1d6", "radius": 8},
    # the game's own colors: warm charcoal, the orange of START!
    "game": {"nav": "#2a2420", "nav_selected": "#453a33", "nav_hover": "#352e29", "nav_text": "#e7ddd3",
             "nav_selected_text": "#ffffff", "nav_title": "#ffffff", "nav_version": "#a8998c", "nav_bar": "#f07c2c",
             "page": "#f7f3ee", "card_border": "#e9e1d7", "text": "#2a2420", "muted": "#5f554c",
             "accent": "#d9601a", "accent_hover": "#b94f12", "accent_soft": "#fdeee3", "on_accent": "#ffffff",
             "line": "#d8cfc4", "radius": 10},
    # black, white and grays only
    "mono": {"nav": "#18181b", "nav_selected": "#3a3a40", "nav_hover": "#26262b", "nav_text": "#d4d4d8",
             "nav_selected_text": "#ffffff", "nav_title": "#ffffff", "nav_version": "#8e8e96", "nav_bar": "transparent",
             "page": "#f4f4f5", "card_border": "#e4e4e7", "text": "#18181b", "muted": "#52525b",
             "accent": "#27272a", "accent_hover": "#000000", "accent_soft": "#ececee", "on_accent": "#ffffff",
             "line": "#d4d4d8", "radius": 6},
}
THEME_ORDER = ("navy", "light", "game", "mono")
# Sliders, switches and check boxes stay blue in every theme (user: as before)
CONTROL = "#2f6fd6"
DEFAULT_THEME = "mono"
T = dict(THEMES[DEFAULT_THEME])   # the theme in use (apply_theme)
ACCENT = T["accent"]              # (read by the rating chart when it paints)


def apply_theme(name):
    """Makes `name` the theme in use; returns the style sheet to set."""
    global ACCENT
    T.clear()
    T.update(THEMES.get(name, THEMES[DEFAULT_THEME]))
    ACCENT = T["accent"]
    return style_sheet()


def style_sheet():
    c = T
    r, r2 = c["radius"], max(4, c["radius"] - 4)
    return f"""
QWidget#settingsRoot {{ background: {c['page']}; }}
QWidget#settingsRoot, QWidget#settingsRoot QWidget {{ font-family: "Yu Gothic UI", "Meiryo UI", "Segoe UI"; font-size: 13px; color: {c['text']}; }}
QScrollArea#page, QScrollArea#page > QWidget > QWidget#pageInner {{ background: {c['page']}; border: none; }}
QFrame#card {{ background: #ffffff; border: 1px solid {c['card_border']}; border-radius: {r}px; }}
QFrame#card QLabel {{ background: transparent; }}
QWidget#settingsRoot QLabel#pageTitle {{ font-size: 20px; font-weight: 700; }}
QWidget#settingsRoot QLabel#cardTitle {{ font-size: 15px; font-weight: 700; }}
QWidget#settingsRoot QLabel#muted {{ color: {c['muted']}; font-size: 12px; }}
QPushButton {{ background: #ffffff; border: 1px solid {c['line']}; border-radius: {r2}px; padding: 6px 12px; }}
QPushButton:hover {{ border-color: {c['accent']}; }}
QPushButton:disabled {{ color: #9aa0b2; border-color: #e1e4ee; }}
QWidget#settingsRoot QPushButton#primary {{ background: {c['accent']}; border-color: {c['accent']}; color: {c['on_accent']}; font-weight: 700; }}
QWidget#settingsRoot QPushButton#primary:hover {{ background: {c['accent_hover']}; color: {c['on_accent']}; }}
QWidget#settingsRoot QPushButton#primary:checked {{ background: #16a34a; border-color: #16a34a; color: #ffffff; }}
QPushButton#cardReset {{ background: transparent; border: 1px solid transparent; border-radius: {r2}px; padding: 3px 8px; color: {c['muted']}; font-size: 12px; }}
QPushButton#cardReset:hover {{ border-color: {c['line']}; color: {c['text']}; background: {c['page']}; }}
QPushButton#cardReset:disabled {{ color: #b9bdc6; border-color: transparent; background: transparent; }}
QPushButton#seg {{ border: none; border-radius: {max(4, r2 - 1)}px; padding: 5px 12px; background: transparent; color: {c['muted']}; }}
QPushButton#seg:checked {{ background: #ffffff; color: {c['text']}; font-weight: 700; }}
QPushButton#seg:disabled {{ color: #9aa0b2; }}
QWidget#segBar {{ background: #e8ebf0; border-radius: {r2 + 1}px; }}
QComboBox, QSpinBox, QLineEdit {{ background: #ffffff; border: 1px solid {c['line']}; border-radius: {max(4, r2 - 1)}px; padding: 4px 8px; min-height: 20px; }}
QComboBox:focus, QSpinBox:focus, QLineEdit:focus {{ border-color: {c['accent']}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox::down-arrow {{ image: url({ASSETS}/chevron_down.svg); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: #ffffff; border: 1px solid {c['line']}; selection-background-color: {c['accent_soft']}; selection-color: {c['text']}; }}
QSpinBox {{ padding-right: 22px; }}
QSpinBox::up-button, QSpinBox::down-button {{ border: none; width: 20px; background: transparent; }}
QSpinBox::up-arrow {{ image: url({ASSETS}/chevron_up.svg); width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: url({ASSETS}/chevron_down.svg); width: 10px; height: 10px; }}
QCheckBox::indicator, QListWidget::indicator {{ width: 16px; height: 16px; border: 1.5px solid #9aa3b8; border-radius: 4px; background: #ffffff; }}
QCheckBox::indicator:checked, QListWidget::indicator:checked {{ background: {CONTROL}; border-color: {CONTROL}; image: url({ASSETS}/check.svg); }}
QCheckBox::indicator:disabled {{ background: #eef0f5; border-color: #d4d8e2; }}
QListWidget {{ background: #ffffff; border: 1px solid {c['card_border']}; border-radius: {r2}px; padding: 2px; }}
QListWidget::item {{ padding: 4px 6px; border-radius: {max(3, r2 - 2)}px; }}
QListWidget::item:selected {{ background: {c['accent_soft']}; color: {c['text']}; }}
QSlider::groove:horizontal {{ height: 6px; background: #dde1ea; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {CONTROL}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: #ffffff; border: 2px solid {CONTROL}; width: 14px; height: 14px; margin: -6px 0; border-radius: 9px; }}
QCheckBox {{ spacing: 8px; background: transparent; }}
QTableWidget {{ background: #ffffff; border: 1px solid {c['card_border']}; border-radius: {r2}px; gridline-color: #eceef4; }}
QHeaderView::section {{ background: #f6f7fa; border: none; border-bottom: 1px solid #eceef4; padding: 4px 6px; font-weight: 700; }}
QToolButton#designCard {{ background: #ffffff; border: 2px solid {c['card_border']}; border-radius: {max(4, r - 2)}px; padding: 4px; }}
QToolButton#designCard:hover {{ border-color: {c['line']}; }}
QToolButton#designCard:checked {{ background: {c['accent_soft']}; border-color: {c['accent']}; font-weight: 700; }}
QToolButton#pad {{ background: #ffffff; border: 1px solid {c['line']}; border-radius: {r2}px; font-size: 15px; }}
QToolButton#pad:hover {{ border-color: {c['accent']}; }}
QListWidget#nav {{ background: {c['nav']}; border: none; border-radius: 0; padding: 0; outline: none; }}
QListWidget#nav::item {{ color: {c['nav_text']}; padding: 9px 8px; margin: 1px 8px; border-radius: {r2}px; border-left: 3px solid transparent; }}
QListWidget#nav::item:selected {{ background: {c['nav_selected']}; color: {c['nav_selected_text']}; border-left: 3px solid {c['nav_bar']}; }}
QListWidget#nav::item:hover:!selected {{ background: {c['nav_hover']}; }}
QWidget#navPanel {{ background: {c['nav']}; }}
QWidget#navPanel QLabel {{ color: {c['nav_title']}; background: transparent; }}
QWidget#settingsRoot QLabel#navVersion {{ color: {c['nav_version']}; font-size: 11px; }}
QWidget#settingsRoot QWidget#navPanel QLabel {{ color: {c['nav_title']}; }}
"""


STYLE = style_sheet()


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


def icon(name, color=None, size=18):
    color = color or T["nav_text"]
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
        track = QtGui.QColor(CONTROL if on else "#c3c9d6")
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
            p.setPen(QtGui.QPen(QtGui.QColor(CONTROL), 1.5))
            p.drawRoundedRect(QtCore.QRectF(0, y - 1, self.W + 2, self.H + 2), self.H / 2 + 1, self.H / 2 + 1)
        if self.text():
            p.setPen(QtGui.QColor(T["text"] if enabled else "#9aa0b2"))
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
        outer.setContentsMargins(16, 14, 16, 14)
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
        self._head = head
        self.reset_button = None   # set_reset
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

    def set_reset(self, callback):
        """A small "back to the default" button at the top right (user: one
        for each item), left of the switch if there is one."""
        b = QtWidgets.QPushButton()
        b.setObjectName("cardReset")
        b.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(callback)
        at = self._head.count() - (1 if self.switch is not None else 0)
        self._head.insertWidget(at, b, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        self.reset_button = b
        return b

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
    lay.setContentsMargins(20, 18, 20, 18)
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
        self._icon_names = []
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        panel = QtWidgets.QWidget()
        panel.setObjectName("navPanel")
        panel.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        panel.setFixedWidth(186)
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

    def refresh_icons(self):
        """Redraws the menu icons in the theme's color (apply_theme)."""
        for i, name in enumerate(self._icon_names):
            if name:
                self.list.item(i).setIcon(icon(name))

    def addTab(self, widget, text, icon_name=None):
        it = QtWidgets.QListWidgetItem(text)
        self._icon_names.append(icon_name)
        if icon_name:
            it.setIcon(icon(icon_name))
        it.setSizeHint(QtCore.QSize(160, 40))
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
