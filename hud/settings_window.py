"""Display settings window (opened from the HUD's tray icon -> 表示設定 / Display settings).

Edits the "display" block of config/overlay_settings.json. Every change is
shown on the HUD at once and saved a moment later; the server picks up the
saved file and passes it on to the OBS overlay, so both follow the same
settings without a restart.

Position adjustment: APM・PPS / match time / event history, each moved on its own.

Opens by itself when the HUD starts (so a first-time user finds it); closing
it keeps the HUD running, and the tray icon opens it again.

Its own text follows display.language (日本語 / English), switching at once.

Can also be run on its own (python settings_window.py) to edit the file —
then the HUD and OBS follow through the server.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from config_store import (load_settings, save_settings, display_settings,
                          DISPLAY_DEFAULTS, DISPLAY_RANGES)

from PyQt6 import QtCore, QtWidgets


NUDGE_STEP = 2   # reference px per arrow click (held down: repeats)

WDA_EXCLUDEFROMCAPTURE = 0x11


def exclude_from_capture(widget):
    """Recognition reads the game from a screen capture of the game window's
    area, so any window on top of the game gets read as part of it. Live:
    this window sat over the right player's NEXT queue, its slots read as "I"
    and that player's placements (PPS) weren't counted. Excluded windows stay
    visible on the monitor but the capture sees what's behind them."""
    try:
        import ctypes
        ctypes.windll.user32.SetWindowDisplayAffinity(int(widget.winId()), WDA_EXCLUDEFROMCAPTURE)
    except Exception:
        pass  # not on Windows (e.g. tests)


# What the position controls can move, and the display keys each one owns
# (same as hud/overlay.py OFFSET_KEYS).
TARGET_KEYS = {
    "stats": ("offset_x", "offset_y"),
    "clock": ("clock_offset_x", "clock_offset_y"),
    "event": ("event_offset_x", "event_offset_y"),
    "summary": ("summary_offset_x", "summary_offset_y"),
}
TARGET_ORDER = ("stats", "clock", "event", "summary")
STYLE_ORDER = ("band", "pop", "gauge", "text", "versus")
OPENER_DISPLAY_ORDER = ("board", "hold", "namebar", "top")
TEXT_WEIGHT_ORDER = ("normal", "bold", "extra_bold")

TEXT = {
    "title": {"ja": "PPT2 Stats Overlay - 表示設定", "en": "PPT2 Stats Overlay - Display settings"},
    "language": {"ja": "言語 / Language", "en": "言語 / Language"},
    "design": {"ja": "デザイン", "en": "Design"},
    "style.band": {"ja": "帯", "en": "Band"},
    "style.pop": {"ja": "ポップ", "en": "Pop"},
    "style.gauge": {"ja": "ミニゲージ", "en": "Mini gauge"},
    "style.text": {"ja": "文字だけ", "en": "Text only"},
    "style.versus": {"ja": "中央VSバー", "en": "Center VS bar"},
    "position": {"ja": "表示位置", "en": "Placement"},
    "pos.left": {"ja": "盤面の左下", "en": "Lower left of each board"},
    "pos.right": {"ja": "盤面の右下", "en": "Lower right of each board"},
    "size": {"ja": "サイズ", "en": "Size"},
    "opacity": {"ja": "背景の濃さ", "en": "Background"},
    "text_weight": {"ja": "文字の太さ", "en": "Text weight"},
    "tw.normal": {"ja": "ふつう", "en": "Normal"},
    "tw.bold": {"ja": "太い", "en": "Bold"},
    "tw.extra_bold": {"ja": "とても太い", "en": "Extra bold"},
    "show_apm": {"ja": "APM を表示", "en": "Show APM"},
    "show_pps": {"ja": "PPS を表示", "en": "Show PPS"},
    "show_app": {"ja": "APP を表示（1ミノあたりの火力）", "en": "Show APP (attack per piece)"},
    "show_clock": {"ja": "試合時間を表示", "en": "Show match time"},
    "show_event_log": {"ja": "イベント履歴を表示（TETRIS / REN など）", "en": "Show event history (TETRIS, REN, ...)"},
    "event_log_count": {"ja": "イベント履歴の件数", "en": "Events shown"},
    "count_suffix": {"ja": " 件", "en": ""},
    "adjust": {"ja": "位置の調整", "en": "Position"},
    "move_what": {"ja": "動かすもの", "en": "Move"},
    "target.stats": {"ja": "APM・PPS", "en": "APM / PPS"},
    "target.clock": {"ja": "試合時間", "en": "Match time"},
    "target.event": {"ja": "イベント履歴", "en": "Event history"},
    "target.summary": {"ja": "試合結果", "en": "Summary"},
    "show_opener": {"ja": "開幕テンプレ名を表示（認識できたとき）", "en": "Show the opener name (when recognized)"},
    "opener_display": {"ja": "開幕テンプレの表示", "en": "Opener display"},
    "od.board": {"ja": "A 盤面の上に大きく（数秒）", "en": "A  Big over the board (a few seconds)"},
    "od.hold": {"ja": "B HOLDの下に小さく（試合中ずっと）", "en": "B  Small under HOLD (whole match)"},
    "od.namebar": {"ja": "C 名前の帯の上（試合中ずっと）", "en": "C  On the name bar (whole match)"},
    "od.top": {"ja": "D 上の中央に両者まとめて（試合中ずっと）", "en": "D  Both at the top center (whole match)"},
    "show_summary": {"ja": "試合が終わったら試合結果（まとめ）を表示", "en": "Show a match summary when a match ends"},
    "up": {"ja": "上へ", "en": "Up"}, "down": {"ja": "下へ", "en": "Down"},
    "left": {"ja": "左へ", "en": "Left"}, "right": {"ja": "右へ", "en": "Right"},
    "reset_pos": {"ja": "初期位置に戻す", "en": "Back to default position"},
    "drag": {"ja": "ゲーム画面上でドラッグして動かす", "en": "Drag on the game screen"},
    "drag_done": {"ja": "完了（ドラッグでの調整を終わる）", "en": "Done (stop dragging)"},
    "hint": {"ja": "矢印は押し続けると連続で動きます。●で初期位置に戻ります。",
             "en": "Hold an arrow to keep moving. ● returns to the default position."},
    "hint_drag": {"ja": "ドラッグ中は、どの枠もそのままつかんで動かせます。",
                  "en": " While dragging is on, grab any box on the game screen to move it."},
    "at_default": {"ja": "初期位置", "en": "Default position"},
    "from_default": {"ja": "初期位置から ", "en": "From default: "},
    "note": {"ja": "変更はすぐに HUD と OBS の表示に反映され、自動で保存されます。",
             "en": "Changes show on the HUD and in OBS right away and are saved automatically."},
    "reset_all": {"ja": "初期設定に戻す", "en": "Reset to defaults"},
    "close": {"ja": "閉じる", "en": "Close"},
}


class SettingsWindow(QtWidgets.QWidget):
    display_changed = QtCore.pyqtSignal(dict)
    edit_mode_changed = QtCore.pyqtSignal(bool)   # drag-to-move mode on the HUD

    def __init__(self, drag_available=False):
        """drag_available: the HUD runs in this same process, so its parts can
        be dragged directly (not when this window is run on its own)."""
        super().__init__()
        self.lang = "ja"
        self._drag_available = drag_available
        self._offsets = {key: [0, 0] for key in TARGET_ORDER}
        self._target = "stats"
        self.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self._loading = False
        self._save_timer = QtCore.QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)  # don't write the file on every slider step
        self._save_timer.timeout.connect(self._save)

        form = QtWidgets.QFormLayout()
        self._row_labels = {}

        def row(key, widget):
            lab = QtWidgets.QLabel()
            self._row_labels[key] = lab
            form.addRow(lab, widget)

        self.language = QtWidgets.QComboBox()
        self.language.addItem("日本語", "ja")
        self.language.addItem("English", "en")
        row("language", self.language)

        self.style = QtWidgets.QComboBox()
        for key in STYLE_ORDER:
            self.style.addItem("", key)
        row("design", self.style)

        self.position = QtWidgets.QComboBox()
        self.position.addItem("", "left")
        self.position.addItem("", "right")
        row("position", self.position)

        self.scale = self._spin(50, 200, "%", step=5)
        row("size", self.scale)

        self.opacity = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.opacity.setRange(0, 100)
        row("opacity", self.opacity)

        self.text_weight = QtWidgets.QComboBox()
        for key in TEXT_WEIGHT_ORDER:
            self.text_weight.addItem("", key)
        row("text_weight", self.text_weight)

        self.show_apm = QtWidgets.QCheckBox()
        self.show_pps = QtWidgets.QCheckBox()
        self.show_app = QtWidgets.QCheckBox()
        self.show_clock = QtWidgets.QCheckBox()
        self.show_event_log = QtWidgets.QCheckBox()
        self.show_summary = QtWidgets.QCheckBox()
        self.show_opener = QtWidgets.QCheckBox()
        for cb in (self.show_apm, self.show_pps, self.show_app, self.show_clock, self.show_event_log,
                   self.show_opener, self.show_summary):
            form.addRow("", cb)
        lo, hi = DISPLAY_RANGES["event_log_count"]
        self.event_log_count = self._spin(lo, hi, "")
        row("event_log_count", self.event_log_count)

        self.opener_display = QtWidgets.QComboBox()
        for key in OPENER_DISPLAY_ORDER:
            self.opener_display.addItem("", key)
        row("opener_display", self.opener_display)

        self.position_section = self._build_offset_controls(drag_available)

        self.reset_button = QtWidgets.QPushButton()
        self.reset_button.clicked.connect(self._reset)
        self.close_button = QtWidgets.QPushButton()
        self.close_button.clicked.connect(self.close)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(self.reset_button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)

        self.note = QtWidgets.QLabel()
        self.note.setStyleSheet("color:#71717a;")
        self.note.setWordWrap(True)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.position_section)
        lay.addWidget(self.note)
        lay.addLayout(buttons)

        self.language.currentIndexChanged.connect(self._language_changed)
        self.position.currentIndexChanged.connect(self._changed)
        self.style.currentIndexChanged.connect(self._changed)
        self.opener_display.currentIndexChanged.connect(self._changed)
        self.text_weight.currentIndexChanged.connect(self._changed)
        for w in (self.scale, self.event_log_count):
            w.valueChanged.connect(self._changed)
        self.opacity.valueChanged.connect(self._changed)
        for cb in (self.show_apm, self.show_pps, self.show_app, self.show_clock, self.show_event_log,
                   self.show_opener, self.show_summary):
            cb.toggled.connect(self._changed)
        self.retranslate()

    def tr_(self, key):
        return TEXT[key][self.lang]

    def retranslate(self):
        """Sets every visible string for the current language."""
        t = self.tr_
        self.setWindowTitle(t("title"))
        for key, lab in self._row_labels.items():
            lab.setText(t(key))
        for i, key in enumerate(STYLE_ORDER):
            self.style.setItemText(i, t("style." + key))
        for i, key in enumerate(TEXT_WEIGHT_ORDER):
            self.text_weight.setItemText(i, t("tw." + key))
        self.position.setItemText(0, t("pos.left"))
        self.position.setItemText(1, t("pos.right"))
        self.show_apm.setText(t("show_apm"))
        self.show_pps.setText(t("show_pps"))
        self.show_app.setText(t("show_app"))
        self.show_clock.setText(t("show_clock"))
        self.show_event_log.setText(t("show_event_log"))
        self.show_summary.setText(t("show_summary"))
        self.show_opener.setText(t("show_opener"))
        for i, key in enumerate(OPENER_DISPLAY_ORDER):
            self.opener_display.setItemText(i, t("od." + key))
        self.event_log_count.setSuffix(t("count_suffix"))
        self.position_section.setTitle(t("adjust"))
        self.move_label.setText(t("move_what"))
        for i, key in enumerate(TARGET_ORDER):
            self.target_group.button(i).setText(t("target." + key))
        for b, key in self.arrow_buttons:
            b.setToolTip(t(key))
        self.center_button.setToolTip(t("reset_pos"))
        self.drag_button.setText(t("drag_done") if self.drag_button.isChecked() else t("drag"))
        self.hint.setText(t("hint") + (t("hint_drag") if self._drag_available else ""))
        self.note.setText(t("note"))
        self.reset_button.setText(t("reset_all"))
        self.close_button.setText(t("close"))
        self._update_offset_label()
        self.adjustSize()

    def _language_changed(self, *_):
        self.lang = self.language.currentData()
        self.retranslate()
        self._changed()

    # --- position section ---
    def _build_offset_controls(self, drag_available):
        """Which part to move, an arrow pad (click or hold; both boards move
        together), a reset, the current shift in words, and — when the HUD is
        in this process — a button to drag the parts on the game screen."""
        box = QtWidgets.QGroupBox()
        outer = QtWidgets.QVBoxLayout(box)

        targets = QtWidgets.QHBoxLayout()
        self.move_label = QtWidgets.QLabel()
        targets.addWidget(self.move_label)
        self.target_group = QtWidgets.QButtonGroup(self)
        for i, key in enumerate(TARGET_ORDER):
            rb = QtWidgets.QRadioButton()
            rb.setProperty("target", key)
            rb.setChecked(key == self._target)
            self.target_group.addButton(rb, i)
            targets.addWidget(rb)
        targets.addStretch(1)
        self.target_group.buttonToggled.connect(self._target_changed)
        outer.addLayout(targets)

        pad = QtWidgets.QGridLayout()
        pad.setSpacing(2)
        self.arrow_buttons = []

        def arrow(text, dx, dy, tip_key):
            b = QtWidgets.QToolButton()
            b.setText(text)
            b.setFixedSize(32, 28)
            b.setAutoRepeat(True)          # hold to keep moving
            b.setAutoRepeatDelay(350)
            b.setAutoRepeatInterval(60)
            b.clicked.connect(lambda: self._nudge(dx, dy))
            self.arrow_buttons.append((b, tip_key))
            return b

        pad.addWidget(arrow("↑", 0, -NUDGE_STEP, "up"), 0, 1)
        pad.addWidget(arrow("←", -NUDGE_STEP, 0, "left"), 1, 0)
        self.center_button = QtWidgets.QToolButton()
        self.center_button.setText("●")
        self.center_button.setFixedSize(32, 28)
        self.center_button.clicked.connect(self._reset_offset)
        pad.addWidget(self.center_button, 1, 1)
        pad.addWidget(arrow("→", NUDGE_STEP, 0, "right"), 1, 2)
        pad.addWidget(arrow("↓", 0, NUDGE_STEP, "down"), 2, 1)

        row = QtWidgets.QHBoxLayout()
        row.addLayout(pad)
        self.offset_label = QtWidgets.QLabel()
        self.offset_label.setWordWrap(True)
        self.offset_label.setMinimumWidth(170)
        row.addWidget(self.offset_label, 1)
        outer.addLayout(row)

        self.drag_button = QtWidgets.QPushButton()
        self.drag_button.setCheckable(True)
        self.drag_button.toggled.connect(self._drag_toggled)
        self.drag_button.setVisible(drag_available)
        outer.addWidget(self.drag_button)
        self.hint = QtWidgets.QLabel()
        self.hint.setStyleSheet("color:#71717a;")
        self.hint.setWordWrap(True)
        outer.addWidget(self.hint)
        return box

    def _target_changed(self, button, checked):
        if checked:
            self._target = button.property("target")
            self._update_offset_label()

    def _update_offset_label(self):
        x, y = self._offsets[self._target]
        en = self.lang == "en"
        parts = []
        if x:
            parts.append(f"{self.tr_('right' if x > 0 else 'left')}{' ' if en else 'へ '}{abs(x)}")
        if y:
            parts.append(f"{self.tr_('down' if y > 0 else 'up')}{' ' if en else 'へ '}{abs(y)}")
        name = self.tr_("target." + self._target)
        where = self.tr_("at_default") if not parts else self.tr_("from_default") + (", " if en else "・").join(parts)
        self.offset_label.setText(f"{name}{': ' if en else '：'}{where}")

    def _set_offset(self, target, x, y):
        kx, ky = TARGET_KEYS[target]
        lo_x, hi_x = DISPLAY_RANGES[kx]
        lo_y, hi_y = DISPLAY_RANGES[ky]
        self._offsets[target] = [int(min(max(x, lo_x), hi_x)), int(min(max(y, lo_y), hi_y))]
        if target == self._target:
            self._update_offset_label()

    def _nudge(self, dx, dy):
        x, y = self._offsets[self._target]
        self._set_offset(self._target, x + dx, y + dy)
        self._changed()

    def _reset_offset(self):
        self._set_offset(self._target, 0, 0)
        self._changed()

    def _drag_toggled(self, on):
        self.drag_button.setText(self.tr_("drag_done") if on else self.tr_("drag"))
        self.edit_mode_changed.emit(on)

    def set_offset_from_hud(self, target, x, y, finished):
        """The user dragged a part on the HUD (already moved there): show it
        as the part being adjusted, and save once the drag ends."""
        if target != self._target:
            self.target_group.button(TARGET_ORDER.index(target)).setChecked(True)
        self._set_offset(target, x, y)
        if finished:
            self._save_timer.start()

    # --- values ---
    @staticmethod
    def _spin(lo, hi, suffix, step=1):
        sb = QtWidgets.QSpinBox()
        sb.setRange(int(lo), int(hi))
        sb.setSingleStep(step)
        sb.setSuffix(suffix)
        return sb

    def open(self):
        """Shows the window with the values currently in the file."""
        self._show_values(display_settings(load_settings()))
        self.show()
        exclude_from_capture(self)
        self.raise_()
        self.activateWindow()

    def _show_values(self, d):
        self._loading = True
        self.language.setCurrentIndex(self.language.findData(d["language"]))
        self.lang = d["language"]
        self.style.setCurrentIndex(self.style.findData(d["style"]))
        self.position.setCurrentIndex(self.position.findData(d["stats_position"]))
        self.scale.setValue(int(round(d["scale"] * 100)))
        for key, (kx, ky) in TARGET_KEYS.items():
            self._set_offset(key, d[kx], d[ky])
        self.opacity.setValue(int(round(d["background_opacity"] * 100)))
        self.text_weight.setCurrentIndex(self.text_weight.findData(d["text_weight"]))
        self.show_apm.setChecked(d["show_apm"])
        self.show_pps.setChecked(d["show_pps"])
        self.show_app.setChecked(d["show_app"])
        self.show_clock.setChecked(d["show_clock"])
        self.show_event_log.setChecked(d["show_event_log"])
        self.show_summary.setChecked(d["show_summary"])
        self.show_opener.setChecked(d["show_opener"])
        self.opener_display.setCurrentIndex(self.opener_display.findData(d["opener_display"]))
        self.opener_display.setEnabled(d["show_opener"])
        self.event_log_count.setValue(d["event_log_count"])
        self.event_log_count.setEnabled(d["show_event_log"])
        self.retranslate()
        self._loading = False

    def values(self):
        d = {
            "language": self.language.currentData(),
            "style": self.style.currentData(),
            "stats_position": self.position.currentData(),
            "scale": self.scale.value() / 100,
            "background_opacity": self.opacity.value() / 100,
            "text_weight": self.text_weight.currentData(),
            "show_apm": self.show_apm.isChecked(),
            "show_pps": self.show_pps.isChecked(),
            "show_app": self.show_app.isChecked(),
            "show_clock": self.show_clock.isChecked(),
            "show_event_log": self.show_event_log.isChecked(),
            "show_summary": self.show_summary.isChecked(),
            "show_opener": self.show_opener.isChecked(),
            "opener_display": self.opener_display.currentData(),
            "event_log_count": self.event_log_count.value(),
        }
        for key, (kx, ky) in TARGET_KEYS.items():
            d[kx], d[ky] = self._offsets[key]
        return display_settings({"display": d})

    def _changed(self, *_):
        if self._loading:
            return
        self.event_log_count.setEnabled(self.show_event_log.isChecked())
        self.opener_display.setEnabled(self.show_opener.isChecked())
        self.display_changed.emit(self.values())
        self._save_timer.start()

    def _reset(self):
        # keep the chosen language: resetting the display shouldn't switch it
        self._show_values(display_settings({"display": {**DISPLAY_DEFAULTS, "language": self.lang}}))
        self._changed()

    def _save(self):
        settings = load_settings()  # keep everything else in the file as it is
        settings["display"] = self.values()
        save_settings(settings)

    def closeEvent(self, event):
        self.drag_button.setChecked(False)  # leave drag mode with the window
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    w = SettingsWindow()
    w.open()
    sys.exit(app.exec())
