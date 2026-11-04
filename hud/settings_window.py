"""Display settings window (opened from the HUD's tray icon -> 表示設定 / Display settings).

Edits the "display" block of config/overlay_settings.json. Every change is
shown on the HUD at once and saved a moment later; the server picks up the
saved file and passes it on to the OBS overlay, so both follow the same
settings without a restart.

Three tabs: what is shown (stat rows and their order, label wording, the other
parts), how it looks (presets, design, text, colors / size / background for
everything at once or for one part, player colors), and where it sits.

Opens by itself when the HUD starts (so a first-time user finds it); closing
it keeps the HUD running, and the tray icon opens it again.

Its own text follows display.language (日本語 / English), switching at once.

Can also be run on its own (python settings_window.py) to edit the file —
then the HUD and OBS follow through the server.
"""
import json
import math
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from config_store import (load_settings, save_settings, display_settings, preset_of, preset_file,
                          read_preset_file, part_value, DISPLAY_DEFAULTS, DISPLAY_RANGES, STAT_ITEMS, PARTS,
                          SUMMARY_ITEMS, OPENER_LANGUAGES)

from PyQt6 import QtCore, QtGui, QtWidgets


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
    "stats_left": ("stats_left_offset_x", "stats_left_offset_y"),
    "stats_right": ("stats_right_offset_x", "stats_right_offset_y"),
    "opener": ("opener_offset_x", "opener_offset_y"),
    "opener_left": ("opener_left_offset_x", "opener_left_offset_y"),
    "opener_right": ("opener_right_offset_x", "opener_right_offset_y"),
}
TARGET_ORDER = ("stats", "stats_left", "stats_right", "opener", "opener_left", "opener_right",
                "clock", "event", "summary")
# simplest first (user's request)
STYLE_ORDER = ("text", "minimal", "simple", "band", "frame", "slash", "pop",
               "gauge", "trend", "tower", "meter", "hex", "versus")
ROOT = Path(__file__).resolve().parent.parent
USER_FONTS = ROOT / "assets" / "user_fonts"
OBS_PAGE = ROOT / "obs" / "overlay.html"   # what an OBS browser source loads
OPENER_DISPLAY_ORDER = ("board", "hold", "namebar", "top", "cat")
PLAYER_ORDER = ("both", "left", "right")
# "Look" target: everything at once ("all"), or one part (display.parts)
LOOK_TARGETS = ("all",) + PARTS
LOOK_KEYS = ("scale", "background_opacity", "bg_color", "text_color", "line_color")
COLOR_KEYS = ("bg_color", "text_color", "line_color")   # what 全体をこの色に合わせる copies
DEFAULT_LABELS = {"apm": "APM", "pps": "PPS", "app": "APP", "attack": "ATK",
                  "pieces": "PIECES", "ren": "REN", "b2b": "B2B"}   # same as hud/overlay.py
DEFAULT_LABELS_EN = {**DEFAULT_LABELS, "ren": "COMBO"}   # English: the game says "Combo"

TEXT = {
    "title": {"ja": "PPTetrics - 表示設定", "en": "PPTetrics - Display settings"},
    "tab.show": {"ja": "表示", "en": "Show"},
    "tab.look": {"ja": "デザイン", "en": "Look"},
    "tab.place": {"ja": "位置", "en": "Position"},
    "tab.obs": {"ja": "OBSに映す", "en": "Show in OBS"},
    "tab.update": {"ja": "アップデート", "en": "Updates"},
    "enabled_on": {"ja": "● 表示オン（クリックでオフ）", "en": "● Overlay ON (click to turn off)"},
    "enabled_off": {"ja": "○ 表示オフ（クリックでオン）", "en": "○ Overlay OFF (click to turn on)"},
    "enabled_away": {"ja": "◐ 表示オン：試合画面ではないので隠れています（クリックで表示）",
                     "en": "◐ Overlay ON: hidden off the match screen (click to show it)"},
    "enabled_forced": {"ja": "● 表示オン：試合画面の外でも表示中（クリックでオフ）",
                       "en": "● Overlay ON: shown off the match screen too (click to turn off)"},
    "up.current": {"ja": "今の版: v{}　　作者: めぞん、Claude", "en": "This version: v{}    Made by めぞん (mezon) and Claude"},
    "up.check_on_start": {"ja": "起動したときに新しい版があるか確認する", "en": "Look for a new version when the app starts"},
    "up.check": {"ja": "今すぐ確認", "en": "Check now"},
    "up.checking": {"ja": "確認しています…", "en": "Checking…"},
    "up.latest": {"ja": "最新の版です。", "en": "You have the latest version."},
    "up.found": {"ja": "新しい版 v{} があります。", "en": "Version v{} is available."},
    "up.failed": {"ja": "確認できませんでした（インターネットにつながっているか確認してください）。",
                  "en": "Couldn't check (is the internet connection up?)."},
    "up.install": {"ja": "更新して再起動", "en": "Update and restart"},
    "up.confirm": {"ja": "v{} に更新して、アプリを再起動します。よろしいですか？\n（設定や読み込んだフォントはそのまま残ります）",
                   "en": "Update to v{} and restart the app?\n(Your settings and loaded fonts are kept.)"},
    "up.downloading": {"ja": "ダウンロードしています… {}", "en": "Downloading… {}"},
    "up.install_failed": {"ja": "更新できませんでした: {}", "en": "Couldn't update: {}"},
    "up.notes": {"ja": "この版の変更点", "en": "What's new"},
    "up.note": {"ja": "更新しても、設定・読み込んだフォント・プリセットはそのまま残ります。勝手に更新されることはありません。\n\n"
                      "PPTetrics は非公式のファンツールです。セガ・The Tetris Company とは関係ありません。\n"
                      "開幕テンプレのデータ: テトリステンプレ整理Wiki（https://w.atwiki.jp/sasasa123/）",
                "en": "Updating keeps your settings, loaded fonts and presets. Nothing updates without you pressing the button.\n\n"
                      "PPTetrics is an unofficial fan tool, not affiliated with SEGA or The Tetris Company.\n"
                      "Opener data: テトリステンプレ整理Wiki (https://w.atwiki.jp/sasasa123/)"},
    "obs_title": {"ja": "OBS にこの表示を重ねる手順", "en": "Putting this display on top of the game in OBS"},
    "obs_steps": {
        "ja": "<ol style='margin-left:-20px'>"
              "<li>このアプリは起動したままにします（数字はここから OBS に届きます）。</li>"
              "<li>OBS の「ソース」の <b>＋</b> → <b>ブラウザ</b> → 名前を付けて OK。</li>"
              "<li><b>ローカルファイル</b> にチェックを入れ、下の <b>場所をコピー</b> を押して、OBS のファイル欄に貼り付けます"
              "（「参照」から選んでも同じです）。</li>"
              "<li><b>幅・高さ</b> は OBS の画面（キャンバス）と同じにします。ふつうは <b>1920 × 1080</b>。OK で閉じます。</li>"
              "<li>ソース一覧で、このブラウザソースを <b>ゲームの映像より上</b> に置きます。"
              "ゲームの映像が画面いっぱいなら、右クリック → 変換 → <b>画面に合わせる</b>。"
              "そうでなければ、ゲームの映像と同じ位置・大きさに重ねます。</li>"
              "</ol>",
        "en": "<ol style='margin-left:-20px'>"
              "<li>Keep this app running (the numbers reach OBS from it).</li>"
              "<li>In OBS, Sources <b>+</b> → <b>Browser</b> → name it, OK.</li>"
              "<li>Tick <b>Local file</b>, press <b>Copy location</b> below and paste it into OBS's file box "
              "(or pick it with Browse).</li>"
              "<li>Set <b>Width / Height</b> to your OBS canvas, usually <b>1920 × 1080</b>. OK.</li>"
              "<li>In the source list put it <b>above the game</b>. If the game fills the screen: right-click → "
              "Transform → <b>Fit to screen</b>; otherwise give it the game's position and size.</li>"
              "</ol>"},
    "obs_copy": {"ja": "場所をコピー", "en": "Copy location"},
    "obs_copied": {"ja": "コピーしました", "en": "Copied"},
    "obs_open": {"ja": "ブラウザで開いて確認", "en": "Preview in a browser"},
    "obs_note": {"ja": "設定を変えると OBS にもすぐ反映されます。表示が古いままのときは、OBS でそのソースを右クリック → "
                       "「現在のページのキャッシュを更新」。HUD（この PC の画面に出る表示）は OBS のウインドウキャプチャには写りません。",
                 "en": "Setting changes reach OBS right away. If it still shows an old look, right-click the source in OBS → "
                       "\"Refresh cache of current page\". The HUD on this PC's screen doesn't show up in OBS window captures."},
    "language": {"ja": "言語 / Language", "en": "言語 / Language"},
    "design": {"ja": "デザイン", "en": "Design"},
    "design_pick": {"ja": "デザイン（クリックで切り替え）", "en": "Design (click to switch)"},
    "style.band": {"ja": "帯", "en": "Band"},
    "style.pop": {"ja": "ポップ", "en": "Pop"},
    "style.gauge": {"ja": "ミニゲージ", "en": "Mini gauge"},
    "style.text": {"ja": "文字だけ", "en": "Text only"},
    "style.versus": {"ja": "中央VSバー", "en": "Center VS bar"},
    "style.simple": {"ja": "シンプル（四角）", "en": "Simple (square)"},
    "style.frame": {"ja": "カラー枠", "en": "Color frame"},
    "style.slash": {"ja": "スラッシュ", "en": "Slash"},
    "style.hex": {"ja": "六角形", "en": "Hexagons"},
    "style.meter": {"ja": "円形メーター", "en": "Round meter"},
    "style.tower": {"ja": "縦メーター", "en": "Bar towers"},
    "style.minimal": {"ja": "ミニマル線", "en": "Minimal lines"},
    "style.trend": {"ja": "推移グラフ", "en": "Trend lines"},
    "items": {"ja": "表示する数値（上から順）", "en": "Numbers shown (top to bottom)"},
    "items_hint": {"ja": "チェックで表示、▲▼で並べ替え", "en": "Tick to show, ▲▼ to reorder"},
    "item.apm": {"ja": "APM（1分あたりの火力）", "en": "APM (attack per minute)"},
    "item.pps": {"ja": "PPS（1秒あたりのミノ数）", "en": "PPS (pieces per second)"},
    "item.app": {"ja": "APP（1ミノあたりの火力）", "en": "APP (attack per piece)"},
    "item.attack": {"ja": "攻撃の合計（送った段数）", "en": "Attack (lines sent)"},
    "item.pieces": {"ja": "置いたミノ数", "en": "Pieces placed"},
    "item.ren": {"ja": "今のREN", "en": "Current combo"},
    "item.b2b": {"ja": "B2B（続いている回数）", "en": "Back-to-Back chain"},
    "move_up": {"ja": "▲", "en": "▲"}, "move_down": {"ja": "▼", "en": "▼"},
    "labels": {"ja": "ラベルの文言（空欄＝標準）", "en": "Label wording (blank = default)"},
    "parts_shown": {"ja": "ほかの表示", "en": "Other parts"},
    "always_show": {"ja": "ホーム画面やメニューでも常に表示する（オフ＝試合画面のときだけ表示）",
                    "en": "Always show, also on the home screen and menus (off = only on the match screen)"},
    "players": {"ja": "表示するプレイヤー", "en": "Players shown"},
    "pl.both": {"ja": "両方（1P と 2P）", "en": "Both (1P and 2P)"},
    "pl.left": {"ja": "1P だけ", "en": "1P only"},
    "pl.right": {"ja": "2P だけ", "en": "2P only"},
    "opener_seconds": {"ja": "開幕テンプレ名を出しておく時間", "en": "Opener name shown for"},
    "os.forever": {"ja": "試合が終わるまで", "en": "Until the match ends"},
    "opener_language": {"ja": "開幕テンプレ名の言語", "en": "Opener name language"},
    "ol.auto": {"ja": "表示の言語と同じ", "en": "Same as the display language"},
    "ol.ja": {"ja": "日本語", "en": "Japanese"},
    "ol.en": {"ja": "英語（英語名がなければ日本語）", "en": "English (Japanese where there's no English name)"},
    "os.seconds": {"ja": "{} 秒", "en": "{} s"},
    "show_clock": {"ja": "試合時間を表示", "en": "Show match time"},
    "show_event_log": {"ja": "イベント履歴を表示（TETRIS / REN など）", "en": "Show event history (TETRIS, combos, ...)"},
    "event_log_count": {"ja": "イベント履歴の件数", "en": "Events shown"},
    "count_suffix": {"ja": " 件", "en": ""},
    "show_opener": {"ja": "開幕テンプレ名を表示（認識できたとき）", "en": "Show the opener name (when recognized)"},
    "opener_display": {"ja": "開幕テンプレの表示", "en": "Opener display"},
    "od.board": {"ja": "A 盤面の上に大きく（数秒）", "en": "A  Big over the board (a few seconds)"},
    "od.hold": {"ja": "B HOLDの下に小さく（数秒）", "en": "B  Small under HOLD (a few seconds)"},
    "od.namebar": {"ja": "C 名前の帯の上（数秒）", "en": "C  On the name bar (a few seconds)"},
    "od.top": {"ja": "D 上の中央に両者まとめて（数秒）", "en": "D  Both at the top center (a few seconds)"},
    "od.cat": {"ja": "E 猫",
               "en": "E  Cat"},
    "show_summary": {"ja": "試合が終わったら試合結果（まとめ）を表示", "en": "Show a match summary when a match ends"},
    "summary_items": {"ja": "試合結果に出す項目", "en": "Summary rows"},
    "sum.opener": {"ja": "開幕テンプレ", "en": "Opener"},
    "sum.apm": {"ja": "APM", "en": "APM"}, "sum.pps": {"ja": "PPS", "en": "PPS"}, "sum.app": {"ja": "APP", "en": "APP"},
    "sum.lines_sent": {"ja": "送った段数", "en": "Lines sent"},
    "sum.pieces": {"ja": "置いたミノ", "en": "Pieces"},
    "sum.max_ren": {"ja": "最大REN", "en": "Max combo"},
    "sum.tetris": {"ja": "TETRIS の回数", "en": "TETRIS count"},
    "sum.tspin": {"ja": "T-SPIN の回数（全部まとめて）", "en": "T-SPIN count (all kinds)"},
    "sum.tspin_single": {"ja": "T-SPIN Single の回数", "en": "T-SPIN Single count"},
    "sum.tspin_double": {"ja": "T-SPIN Double の回数", "en": "T-SPIN Double count"},
    "sum.tspin_triple": {"ja": "T-SPIN Triple の回数", "en": "T-SPIN Triple count"},
    "sum.tspin_mini": {"ja": "T-SPIN Mini の回数", "en": "T-SPIN Mini count"},
    "sum.perfect_clear": {"ja": "パーフェクトクリアの回数", "en": "Perfect clear count"},
    "presets": {"ja": "プリセット", "en": "Presets"},
    "preset_pick": {"ja": "（選ぶと切り替わります）", "en": "(pick one to switch to it)"},
    "preset_save": {"ja": "今の見た目を保存…", "en": "Save current look…"},
    "preset_delete": {"ja": "削除", "en": "Delete"},
    "preset_export": {"ja": "ファイルに書き出す…", "en": "Export to file…"},
    "preset_import": {"ja": "ファイルから読み込む…", "en": "Import from file…"},
    "preset_name": {"ja": "プリセットの名前", "en": "Preset name"},
    "preset_bad": {"ja": "このファイルはプリセットとして読み込めませんでした。",
                   "en": "This file couldn't be read as a preset."},
    "text_group": {"ja": "文字", "en": "Text"},
    "text_weight": {"ja": "文字の太さ", "en": "Text weight"},
    "tw.thin": {"ja": "細い", "en": "Thin"},
    "tw.thick": {"ja": "太い", "en": "Thick"},
    "text_outline": {"ja": "文字に縁をつける", "en": "Outline the text"},
    "font": {"ja": "フォント", "en": "Font"},
    "font_default": {"ja": "標準", "en": "Default"},
    "font_load": {"ja": "ファイルから読み込む…", "en": "Load from file…"},
    "font_load_title": {"ja": "フォントファイルを選ぶ", "en": "Choose a font file"},
    "font_load_failed": {"ja": "このファイルはフォントとして読み込めませんでした。",
                         "en": "This file couldn't be loaded as a font."},
    "look_group": {"ja": "大きさ・色・背景", "en": "Size, colors, background"},
    "look_target": {"ja": "対象", "en": "Applies to"},
    "lt.all": {"ja": "全体（全部まとめて）", "en": "Everything at once"},
    "lt.stats": {"ja": "数値", "en": "Numbers"},
    "lt.clock": {"ja": "試合時間", "en": "Match time"},
    "lt.events": {"ja": "イベント履歴", "en": "Event history"},
    "lt.summary": {"ja": "試合結果", "en": "Summary"},
    "lt.opener": {"ja": "開幕テンプレ名", "en": "Opener name"},
    "size": {"ja": "大きさ", "en": "Size"},
    "opacity": {"ja": "背景の濃さ", "en": "Background"},
    "bg_color": {"ja": "背景の色", "en": "Background color"},
    "line_color": {"ja": "背景（線）の色", "en": "Background (line) color"},
    "text_color": {"ja": "文字の色", "en": "Text color"},
    "part_to_all": {"ja": "全体をこの色に合わせる", "en": "Give everything these colors"},
    "player_colors": {"ja": "プレイヤーの色", "en": "Player colors"},
    "player_color_left": {"ja": "1P", "en": "1P"},
    "player_color_right": {"ja": "2P", "en": "2P"},
    "color_reset": {"ja": "元に戻す", "en": "Reset"},
    "position": {"ja": "表示位置", "en": "Placement"},
    "pos.left": {"ja": "盤面の左下", "en": "Lower left of each board"},
    "pos.right": {"ja": "盤面の右下", "en": "Lower right of each board"},
    "adjust": {"ja": "位置の調整", "en": "Position"},
    "move_what": {"ja": "動かすもの", "en": "Move"},
    "target.stats": {"ja": "数値（1P と 2P 一緒に）", "en": "Numbers (1P and 2P together)"},
    "target.stats_left": {"ja": "1P の数値", "en": "1P numbers"},
    "target.stats_right": {"ja": "2P の数値", "en": "2P numbers"},
    "target.opener": {"ja": "テンプレ名（1P と 2P 一緒に）", "en": "Opener names (1P and 2P together)"},
    "drag_each_side": {"ja": "ゲーム画面でドラッグするとき 1P と 2P を別々に動かす（オフ＝一緒に）",
                       "en": "Dragging on the game screen moves 1P and 2P separately (off = together)"},
    "target.clock": {"ja": "試合時間", "en": "Match time"},
    "target.event": {"ja": "イベント履歴", "en": "Event history"},
    "target.summary": {"ja": "試合結果", "en": "Summary"},
    "target.opener_left": {"ja": "1P のテンプレ名", "en": "1P opener"},
    "target.opener_right": {"ja": "2P のテンプレ名", "en": "2P opener"},
    "up": {"ja": "上へ", "en": "Up"}, "down": {"ja": "下へ", "en": "Down"},
    "left": {"ja": "左へ", "en": "Left"}, "right": {"ja": "右へ", "en": "Right"},
    "reset_pos": {"ja": "初期位置に戻す", "en": "Back to default position"},
    "drag": {"ja": "ゲーム画面上でドラッグして動かす", "en": "Drag on the game screen"},
    "drag_done": {"ja": "完了（ドラッグでの調整を終わる）", "en": "Done (stop dragging)"},
    "hint": {"ja": "矢印は押し続けると連続で動きます。●で初期位置に戻ります。",
             "en": "Hold an arrow to keep moving. ● returns to the default position."},
    "hint_drag": {"ja": "ドラッグ中は、どの枠もそのままつかんで動かせます。枠の上でマウスホイールを回すと大きさが変わります。",
                  "en": " While dragging is on, grab any box on the game screen to move it; turn the mouse wheel over it to resize it."},
    "at_default": {"ja": "初期位置", "en": "Default position"},
    "from_default": {"ja": "初期位置から ", "en": "From default: "},
    "note": {"ja": "変更はすぐに HUD と OBS の表示に反映され、自動で保存されます。",
             "en": "Changes show on the HUD and in OBS right away and are saved automatically."},
    "reset_all": {"ja": "初期設定に戻す", "en": "Reset to defaults"},
    "close": {"ja": "閉じる", "en": "Close"},
    "settings_on_top": {"ja": "設定画面を常に最前面に表示", "en": "Keep the settings window on top"},
    "show_on_hud": {"ja": "ゲーム画面に表示", "en": "On the game screen"},
    "show_on_obs": {"ja": "OBS に表示", "en": "In OBS"},
    "show_on_tip": {"ja": "表示オンのとき、どこに出すか（片方だけにもできます）",
                    "en": "Where it shows while on (either one alone is fine)"},
    "confirm_title": {"ja": "確認", "en": "Confirm"},
    "reset_confirm": {"ja": "表示設定を初期設定に戻します。よろしいですか？",
                       "en": "Reset the display settings to their defaults?"},
    "delete_confirm": {"ja": "プリセット「{}」を削除します。よろしいですか？",
                       "en": "Delete the preset “{}”?"},
}


PREVIEW_W, PREVIEW_H = 150, 92
SAMPLE_LEFT = {"apm": {"apm": 77.8}, "pps": 2.09, "app": 0.62, "attack": 112, "pieces": 181, "ren": 3, "b2b": 2}
SAMPLE_RIGHT = {"apm": {"apm": 43.2}, "pps": 1.74, "app": 0.41, "attack": 62, "pieces": 151, "ren": 0, "b2b": 0}


def render_style_preview(style, d):
    """A small picture of the stat block in `style`, drawn by the HUD's own
    code with the current colors, font and rows (None if the HUD code can't
    be loaded) — so the design choice is something you can see, not a name."""
    try:
        import overlay
    except Exception:
        return None
    overlay.set_text_style(d["text_weight"], d["text_outline"])
    overlay.set_font(d["font_family"], d["font_file"])
    overlay.set_labels(d["labels"])
    overlay.set_player_colors(d["player_color_left"], d["player_color_right"])
    items = d["stat_items"][:3] or ["apm", "pps", "app"]   # three rows are enough to show the look
    if style == "versus":
        w = overlay.VersusBlock(None)
        w.configure(items, 0.6)
        w.update_sides(SAMPLE_LEFT, SAMPLE_RIGHT)
    else:
        w = overlay.StatBlock(None, "left")
        w.update_side(SAMPLE_LEFT)
        if style == "trend":   # a made-up last minute, so the little charts show
            for i, k in enumerate(w.KEYS):
                v = overlay.side_values(SAMPLE_LEFT)[k]
                w.history[k].extend(v * (0.85 + 0.12 * math.sin(j / 3 + i) + j * 0.004) for j in range(30))
        w.configure(style, "left", items, 0.85)
    w.colors = (part_value(d, "stats", "bg_color"), part_value(d, "stats", "text_color"),
                part_value(d, "stats", "line_color"))
    w.opacity = part_value(d, "stats", "background_opacity")
    w.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
    shot = w.grab()
    pm = QtGui.QPixmap(PREVIEW_W, PREVIEW_H)
    p = QtGui.QPainter(pm)
    g = QtGui.QLinearGradient(0, 0, PREVIEW_W, PREVIEW_H)   # a game-ish backdrop, light and dark parts
    g.setColorAt(0.0, QtGui.QColor(150, 186, 214))
    g.setColorAt(1.0, QtGui.QColor(92, 74, 64))
    p.fillRect(pm.rect(), g)
    if shot.width() > PREVIEW_W - 8 or shot.height() > PREVIEW_H - 8:
        shot = shot.scaled(PREVIEW_W - 8, PREVIEW_H - 8, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                           QtCore.Qt.TransformationMode.SmoothTransformation)
    p.drawPixmap((PREVIEW_W - shot.width()) // 2, (PREVIEW_H - shot.height()) // 2, shot)
    p.end()
    w.deleteLater()
    return pm


def _form():
    f = QtWidgets.QFormLayout()
    f.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    return f


def _hbox(*widgets, stretch=True):
    holder = QtWidgets.QWidget()
    box = QtWidgets.QHBoxLayout(holder)
    box.setContentsMargins(0, 0, 0, 0)
    for w in widgets:
        box.addWidget(w)
    if stretch:
        box.addStretch(1)
    return holder


class SettingsWindow(QtWidgets.QWidget):
    # (info or None, error text or ""): a check for a newer version finished
    update_checked = QtCore.pyqtSignal(object, str)
    # (command or None, error text): the new version is downloaded and ready
    update_prepared = QtCore.pyqtSignal(object, str)
    update_progress = QtCore.pyqtSignal(int, int)
    update_available = QtCore.pyqtSignal(dict)   # found on the start-up check (the tray says so)
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
        # overall look values and per-part overrides (display.parts), edited
        # through one set of controls according to self._look_target
        self._overall = {k: DISPLAY_DEFAULTS[k] for k in LOOK_KEYS}
        self._parts = {p: {} for p in PARTS}
        self._look_target = "all"
        self._player_colors = {"player_color_left": DISPLAY_DEFAULTS["player_color_left"],
                               "player_color_right": DISPLAY_DEFAULTS["player_color_right"]}
        self._font_file = ""
        self._font_loaded_family = None
        self._ui_preferences = load_settings(persist_defaults=False).get("ui", {})
        self._settings_on_top = bool(self._ui_preferences.get("settings_on_top", False))
        if self._settings_on_top:
            self.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint, True)
        # True while controls are being filled in (building, loading a file or
        # preset): their change signals then mustn't count as user edits — that
        # would save the defaults over the user's file before it's even read.
        self._loading = True
        self._save_timer = QtCore.QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)  # don't write the file on every slider step
        self._save_timer.timeout.connect(self._save)
        self._row_labels = {}

        # The on/off switch, above everything (user: easy to find)
        # off -> on; on but hidden (home screen etc.) -> shown anyway
        # (display.force_show, user's request); on -> off
        self._enabled, self._force = True, False
        self._off_match_screen = False   # from the HUD (set_match_screen)
        self.enabled_button = QtWidgets.QPushButton()
        self.enabled_button.setMinimumHeight(40)
        self.enabled_button.clicked.connect(self._enabled_clicked)
        # where it shows while on: over the game / in OBS, each on its own (user's request)
        self.show_on_hud = QtWidgets.QCheckBox()
        self.show_on_obs = QtWidgets.QCheckBox()
        for c in (self.show_on_hud, self.show_on_obs):
            c.setChecked(True)
            c.toggled.connect(self._changed)
        self.on_top_check = QtWidgets.QCheckBox()
        self.on_top_check.setChecked(self._settings_on_top)
        self.on_top_check.toggled.connect(self._set_settings_on_top)
        self.tabs = QtWidgets.QTabWidget()
        # the look first: it's what people come to change, and the window opens on it
        self.tabs.addTab(self._scrolling(self._build_look_tab()), "")
        self.tabs.addTab(self._scrolling(self._build_show_tab()), "")
        self.tabs.addTab(self._build_place_tab(drag_available), "")
        self.tabs.addTab(self._build_obs_tab(), "")
        self.tabs.addTab(self._build_update_tab(), "")
        self._update_info = None
        self._update_silent = False
        self.update_checked.connect(self._on_update_checked)
        self.update_prepared.connect(self._on_update_prepared)
        self.update_progress.connect(self._on_update_progress)

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
        lay.addWidget(self.enabled_button)
        where = QtWidgets.QHBoxLayout()
        where.addWidget(self.show_on_hud)
        where.addWidget(self.show_on_obs)
        where.addStretch(1)
        lay.addLayout(where)
        lay.addWidget(self.on_top_check)
        lay.addWidget(self.tabs)
        lay.addWidget(self.note)
        lay.addLayout(buttons)
        self.retranslate()
        self._loading = False
        # The mouse wheel only scrolls: over a dropdown, number box or slider it
        # used to change the value while scrolling the page (user's request).
        for w in self.findChildren((QtWidgets.QComboBox, QtWidgets.QAbstractSpinBox, QtWidgets.QAbstractSlider)):
            if not isinstance(w, QtWidgets.QScrollBar):
                w.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Type.Wheel and not isinstance(obj, QtWidgets.QScrollBar):
            area = obj.parentWidget()
            while area is not None and not isinstance(area, QtWidgets.QAbstractScrollArea):
                area = area.parentWidget()
            if area is not None:   # scroll the page the control sits on instead
                QtCore.QCoreApplication.sendEvent(area.verticalScrollBar(), event)
            return True
        return super().eventFilter(obj, event)

    @staticmethod
    def _scrolling(page):
        """The design tab is tall (cards, presets, text, colors): scroll it
        rather than grow the window past a small screen."""
        area = QtWidgets.QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(page)
        area.setMinimumWidth(page.sizeHint().width() + 24)
        screen = QtGui.QGuiApplication.primaryScreen()
        h = page.sizeHint().height() + 8
        if screen is not None:
            h = min(h, int(screen.availableGeometry().height() * 0.7))
        area.setMinimumHeight(h)
        return area

    def _row(self, form, key, widget):
        lab = QtWidgets.QLabel()
        self._row_labels[key] = lab
        form.addRow(lab, widget)

    # --- tab 1: what is shown ---
    def _build_show_tab(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        form = _form()
        self.language = QtWidgets.QComboBox()
        self.language.addItem("日本語", "ja")
        self.language.addItem("English", "en")
        self.language.currentIndexChanged.connect(self._language_changed)
        self._row(form, "language", self.language)
        lay.addLayout(form)

        self.items_box = QtWidgets.QGroupBox()
        ib = QtWidgets.QVBoxLayout(self.items_box)
        self.items_hint = QtWidgets.QLabel()
        self.items_hint.setStyleSheet("color:#71717a;")
        ib.addWidget(self.items_hint)
        row = QtWidgets.QHBoxLayout()
        self.items = QtWidgets.QListWidget()
        self.items.setMaximumHeight(160)
        for key in STAT_ITEMS:
            it = QtWidgets.QListWidgetItem("")
            it.setData(QtCore.Qt.ItemDataRole.UserRole, key)
            it.setFlags(it.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(QtCore.Qt.CheckState.Unchecked)
            self.items.addItem(it)
        self.items.itemChanged.connect(self._changed)
        row.addWidget(self.items, 1)
        arrows = QtWidgets.QVBoxLayout()
        self.item_up, self.item_down = QtWidgets.QToolButton(), QtWidgets.QToolButton()
        self.item_up.clicked.connect(lambda: self._move_item(-1))
        self.item_down.clicked.connect(lambda: self._move_item(1))
        arrows.addWidget(self.item_up)
        arrows.addWidget(self.item_down)
        arrows.addStretch(1)
        row.addLayout(arrows)
        ib.addLayout(row)
        lay.addWidget(self.items_box)

        self.labels_box = QtWidgets.QGroupBox()
        lf = QtWidgets.QGridLayout(self.labels_box)
        self.label_edits = {}
        self.label_names = {}   # the default name beside each box (by language: retranslate)
        for i, key in enumerate(STAT_ITEMS):
            e = QtWidgets.QLineEdit()
            e.setMaxLength(12)
            e.setPlaceholderText(DEFAULT_LABELS[key])
            e.textChanged.connect(self._changed)
            self.label_edits[key] = e
            self.label_names[key] = QtWidgets.QLabel(DEFAULT_LABELS[key])
            lf.addWidget(self.label_names[key], i // 2, (i % 2) * 2)
            lf.addWidget(e, i // 2, (i % 2) * 2 + 1)
        lay.addWidget(self.labels_box)

        self.parts_box = QtWidgets.QGroupBox()
        pf = _form()
        self.always_show = QtWidgets.QCheckBox()
        self.always_show.toggled.connect(self._changed)
        self.show_clock = QtWidgets.QCheckBox()
        self.show_event_log = QtWidgets.QCheckBox()
        self.show_summary = QtWidgets.QCheckBox()
        self.show_opener = QtWidgets.QCheckBox()
        lo, hi = DISPLAY_RANGES["event_log_count"]
        self.event_log_count = self._spin(lo, hi, "")
        self.opener_display = QtWidgets.QComboBox()
        for key in OPENER_DISPLAY_ORDER:
            self.opener_display.addItem("", key)
        pf.addRow("", self.always_show)
        self.players = QtWidgets.QComboBox()
        for key in PLAYER_ORDER:
            self.players.addItem("", key)
        self.players.currentIndexChanged.connect(self._changed)
        self._row(pf, "players", self.players)
        pf.addRow("", self.show_clock)
        pf.addRow("", self.show_event_log)
        self._row(pf, "event_log_count", self.event_log_count)
        pf.addRow("", self.show_summary)
        # which rows the summary shows (fixed order; tick to show)
        self.summary_items = QtWidgets.QListWidget()
        self.summary_items.setMaximumHeight(170)
        for key in SUMMARY_ITEMS:
            it = QtWidgets.QListWidgetItem("")
            it.setData(QtCore.Qt.ItemDataRole.UserRole, key)
            it.setFlags(it.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(QtCore.Qt.CheckState.Unchecked)
            self.summary_items.addItem(it)
        self.summary_items.itemChanged.connect(self._changed)
        self._row(pf, "summary_items", self.summary_items)
        pf.addRow("", self.show_opener)
        self._row(pf, "opener_display", self.opener_display)
        self.opener_seconds = QtWidgets.QSpinBox()
        self.opener_seconds.setRange(0, 30)
        self.opener_seconds.valueChanged.connect(self._changed)
        self._row(pf, "opener_seconds", self.opener_seconds)
        self.opener_language = QtWidgets.QComboBox()
        for key in OPENER_LANGUAGES:
            self.opener_language.addItem("", key)
        self.opener_language.currentIndexChanged.connect(self._changed)
        self._row(pf, "opener_language", self.opener_language)
        self.parts_box.setLayout(pf)
        lay.addWidget(self.parts_box)
        lay.addStretch(1)
        for cb in (self.show_clock, self.show_event_log, self.show_summary, self.show_opener):
            cb.toggled.connect(self._changed)
        self.event_log_count.valueChanged.connect(self._changed)
        self.opener_display.currentIndexChanged.connect(self._changed)
        return page

    def _move_item(self, step):
        row = self.items.currentRow()
        new = row + step
        if row < 0 or not 0 <= new < self.items.count():
            return
        it = self.items.takeItem(row)
        self.items.insertItem(new, it)
        self.items.setCurrentRow(new)
        self._changed()

    # --- tab 2: how it looks ---
    def _build_look_tab(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)

        # the design, as cards showing what each one looks like (click to switch)
        self.design_box = QtWidgets.QGroupBox()
        grid = QtWidgets.QGridLayout(self.design_box)
        self._style = DISPLAY_DEFAULTS["style"]
        self.style_group = QtWidgets.QButtonGroup(self)
        self.style_group.setExclusive(True)
        self.style_cards = {}
        for i, key in enumerate(STYLE_ORDER):
            card = QtWidgets.QToolButton()
            card.setCheckable(True)
            card.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            card.setIconSize(QtCore.QSize(PREVIEW_W, PREVIEW_H))
            card.setMinimumSize(PREVIEW_W + 16, PREVIEW_H + 34)   # sized before the pictures arrive
            card.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
            card.setStyleSheet("QToolButton { padding: 4px; border: 2px solid transparent; border-radius: 6px; }"
                               "QToolButton:checked { border-color: #2563eb; background: #dbeafe; font-weight: bold; }"
                               "QToolButton:hover:!checked { border-color: #93c5fd; }")
            self.style_group.addButton(card, i)
            self.style_cards[key] = card
            grid.addWidget(card, i // 3, i % 3)
        self.style_group.idClicked.connect(self._style_picked)
        lay.addWidget(self.design_box)
        self._preview_timer = QtCore.QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(150)   # redraw the cards once a burst of edits settles
        self._preview_timer.timeout.connect(self._refresh_previews)

        self.presets_box = QtWidgets.QGroupBox()
        pb = QtWidgets.QVBoxLayout(self.presets_box)
        self.preset_box = QtWidgets.QComboBox()
        self.preset_box.activated.connect(self._apply_preset)
        pb.addWidget(self.preset_box)
        self.preset_save, self.preset_delete = QtWidgets.QPushButton(), QtWidgets.QPushButton()
        self.preset_export, self.preset_import = QtWidgets.QPushButton(), QtWidgets.QPushButton()
        self.preset_save.clicked.connect(self._save_preset)
        self.preset_delete.clicked.connect(self._delete_preset)
        self.preset_export.clicked.connect(self._export_preset)
        self.preset_import.clicked.connect(self._import_preset)
        pb.addWidget(_hbox(self.preset_save, self.preset_delete))
        pb.addWidget(_hbox(self.preset_export, self.preset_import))
        lay.addWidget(self.presets_box)

        self.text_box = QtWidgets.QGroupBox()
        tf = _form()
        # a slider, thin to thick (user's request); starts where "bold" was
        self.text_weight = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.text_weight.setRange(0, 100)
        self.text_weight.valueChanged.connect(self._changed)
        self.tw_thin, self.tw_thick = QtWidgets.QLabel(), QtWidgets.QLabel()
        self._row(tf, "text_weight", _hbox(self.tw_thin, self.text_weight, self.tw_thick, stretch=False))
        self.text_outline = QtWidgets.QCheckBox()
        self.text_outline.toggled.connect(self._changed)
        tf.addRow("", self.text_outline)
        # font: any installed family, or one loaded from a file (copied to assets/user_fonts/)
        self.font_box = QtWidgets.QComboBox()
        self.font_box.setMaxVisibleItems(20)
        self.font_box.addItem("", "")
        for fam in QtGui.QFontDatabase.families():
            self.font_box.addItem(fam, fam)
        self.font_box.currentIndexChanged.connect(self._font_changed)
        self.font_load = QtWidgets.QPushButton()
        self.font_load.clicked.connect(self._load_font)
        self._row(tf, "font", _hbox(self.font_box, self.font_load, stretch=False))
        self.text_box.setLayout(tf)
        lay.addWidget(self.text_box)

        self.look_box = QtWidgets.QGroupBox()
        lf = _form()
        self.look_target = QtWidgets.QComboBox()
        for key in LOOK_TARGETS:
            self.look_target.addItem("", key)
        self.look_target.currentIndexChanged.connect(self._look_target_changed)
        self._row(lf, "look_target", self.look_target)
        self.scale = self._spin(50, 200, "%", step=5)
        self.scale.valueChanged.connect(lambda v: self._look_edited("scale", v / 100))
        self._row(lf, "size", _hbox(self.scale))
        self.opacity = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.opacity.setRange(0, 100)
        self.opacity.valueChanged.connect(lambda v: self._look_edited("background_opacity", v / 100))
        self._row(lf, "opacity", _hbox(self.opacity, stretch=False))
        # the background row edits line_color in the minimal design (its lines are its background)
        self.color_buttons, self.color_resets = {}, {}
        for key in ("bg_color", "text_color"):
            pick, reset = QtWidgets.QPushButton(), QtWidgets.QPushButton()
            pick.setFixedWidth(90)
            pick.clicked.connect(lambda _=False, k=key: self._pick_look_color(k))
            reset.clicked.connect(lambda _=False, k=key: self._reset_look_color(k))
            self.color_buttons[key], self.color_resets[key] = pick, reset
            self._row(lf, key, _hbox(pick, reset))
        self.part_reset = QtWidgets.QPushButton()
        self.part_reset.clicked.connect(self._part_to_all)
        lf.addRow("", _hbox(self.part_reset))
        self.look_box.setLayout(lf)
        lay.addWidget(self.look_box)

        self.player_box = QtWidgets.QGroupBox()
        plf = _form()
        self.player_buttons, self.player_resets = {}, {}
        for key in ("player_color_left", "player_color_right"):
            pick, reset = QtWidgets.QPushButton(), QtWidgets.QPushButton()
            pick.setFixedWidth(90)
            pick.clicked.connect(lambda _=False, k=key: self._pick_player_color(k))
            reset.clicked.connect(lambda _=False, k=key: self._set_player_color(k, DISPLAY_DEFAULTS[k], changed=True))
            self.player_buttons[key], self.player_resets[key] = pick, reset
            self._row(plf, key, _hbox(pick, reset))
        self.player_box.setLayout(plf)
        lay.addWidget(self.player_box)
        lay.addStretch(1)
        return page

    # --- tab 3: where it sits ---
    def _build_place_tab(self, drag_available):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        form = _form()
        self.position = QtWidgets.QComboBox()
        self.position.addItem("", "left")
        self.position.addItem("", "right")
        self.position.currentIndexChanged.connect(self._changed)
        self._row(form, "position", self.position)
        lay.addLayout(form)
        self.position_section = self._build_offset_controls(drag_available)
        lay.addWidget(self.position_section)
        lay.addStretch(1)
        return page

    # --- tab 4: OBS ---
    # --- tab 5: updates (scripts/updater.py) ---
    def _build_update_tab(self):
        import updater
        from version import VERSION
        self._updater = updater
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        self.up_current = QtWidgets.QLabel()
        self.up_current.setStyleSheet("font-weight:bold; font-size:14px;")
        self._version = VERSION
        lay.addWidget(self.up_current)
        self.up_check_on_start = QtWidgets.QCheckBox()
        import config_store   # read without creating the file (building the window must not save anything)
        saved = load_settings() if config_store.CONFIG_PATH.exists() else config_store.DEFAULTS
        self.up_check_on_start.setChecked(saved.get("update", {}).get("check_on_start", True))
        self.up_check_on_start.toggled.connect(self._save_update_setting)
        lay.addWidget(self.up_check_on_start)
        self.up_check = QtWidgets.QPushButton()
        self.up_check.clicked.connect(lambda: self.check_for_update(silent=False))
        self.up_install = QtWidgets.QPushButton()
        self.up_install.setStyleSheet("font-weight:bold;")
        self.up_install.clicked.connect(self._install_update)
        self.up_install.setVisible(False)
        lay.addWidget(_hbox(self.up_check, self.up_install))
        self.up_status = QtWidgets.QLabel()
        self.up_status.setWordWrap(True)
        lay.addWidget(self.up_status)
        self.up_notes_title = QtWidgets.QLabel()
        self.up_notes_title.setStyleSheet("font-weight:bold;")
        self.up_notes = QtWidgets.QTextBrowser()
        self.up_notes.setOpenExternalLinks(True)
        self.up_notes.setMaximumHeight(180)
        for w in (self.up_notes_title, self.up_notes):
            w.setVisible(False)
            lay.addWidget(w)
        self.up_note = QtWidgets.QLabel()
        self.up_note.setWordWrap(True)
        self.up_note.setStyleSheet("color:#71717a;")
        lay.addWidget(self.up_note)
        lay.addStretch(1)
        return page

    def _hidden_off_screen(self):
        """On, but hidden because the game isn't on the match screen."""
        return self._enabled and self._off_match_screen and not self._force and not self.always_show.isChecked()

    def _paint_enabled(self):
        for c in (self.show_on_hud, self.show_on_obs):   # where it shows: only matters while on
            c.setEnabled(self._enabled)
        if not self._enabled:
            key, look = "enabled_off", "background: #e4e4e7; color: #3f3f46; }"
        elif self._hidden_off_screen():
            key, look = "enabled_away", "background: #f59e0b; color: white; }"
        else:
            key = "enabled_forced" if self._force and self._off_match_screen else "enabled_on"
            look = "background: #16a34a; color: white; }"
        self.enabled_button.setText(self.tr_(key))
        self.enabled_button.setStyleSheet(
            "QPushButton { font-size: 15px; font-weight: bold; border-radius: 6px; padding: 6px; " + look)

    def _enabled_clicked(self):
        if not self._enabled:
            self._enabled, self._force = True, self._off_match_screen   # on, and seen at once
        elif self._hidden_off_screen():
            self._force = True
        else:
            self._enabled, self._force = False, False
        self._paint_enabled()
        self._changed()

    def set_match_screen(self, on_screen):
        """From the HUD: the game went to / left the match screen. Back on it,
        a "show anyway" ends (the usual hiding returns after this match)."""
        self._off_match_screen = not on_screen
        # (the file's value: the window may never have been opened this session)
        if on_screen and display_settings(load_settings())["force_show"]:
            self._apply_saved(force_show=False)
        self._paint_enabled()

    def set_enabled(self, on):
        """The tray menu's switch. The window may never have been opened, so
        the saved values are read first: only on/off changes, nothing else
        (saving whatever the unopened window holds would put the defaults
        over the user's settings)."""
        if self._save_timer.isActive():   # an edit still waiting to be saved goes first
            self._save_timer.stop()
            self._save()
        self._apply_saved(enabled=on, force_show=on and self._off_match_screen)

    def set_shown_on(self, key, on):
        """The tray menu's "on the game screen" / "in OBS" (show_on_hud /
        show_on_obs): only that one changes (see set_enabled)."""
        self._apply_saved(**{key: on})

    def _apply_saved(self, **changes):
        """Changes just these display values on top of the saved ones (the
        window may never have been opened: see set_enabled), then saves and
        applies them."""
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save()
        d = display_settings(load_settings())
        self._show_values(display_settings({"display": {**d, **changes}}))
        self._changed()

    def _save_update_setting(self, on):
        settings = load_settings()
        settings.setdefault("update", {})["check_on_start"] = bool(on)
        save_settings(settings)

    def check_for_update(self, silent=True):
        """Asks GitHub for a newer version in the background. silent (start-up):
        nothing is said unless there is one."""
        import threading
        self._update_silent = silent
        if not silent:
            self.up_status.setText(self.tr_("up.checking"))
            self.up_check.setEnabled(False)

        def work():
            try:
                self.update_checked.emit(self._updater.check_latest(), "")
            except Exception as e:   # offline, GitHub down, no release yet...
                self.update_checked.emit(None, str(e) or e.__class__.__name__)
        threading.Thread(target=work, daemon=True).start()

    def _on_update_checked(self, info, error):
        self.up_check.setEnabled(True)
        self._update_info = info
        if info:
            self.up_status.setText(self.tr_("up.found").format(info["version"]))
            self.up_install.setVisible(True)
            self.up_notes.setMarkdown(info.get("notes") or "")
            for w in (self.up_notes_title, self.up_notes):
                w.setVisible(bool(info.get("notes")))
            if self._update_silent:
                self.update_available.emit(info)
        elif not self._update_silent:
            self.up_status.setText(self.tr_("up.failed") if error else self.tr_("up.latest"))
            self.up_install.setVisible(False)

    def show_update_tab(self):
        self.open()
        self.tabs.setCurrentIndex(self.tabs.count() - 1)

    def _install_update(self):
        info = self._update_info
        if not info:
            return
        answer = QtWidgets.QMessageBox.question(self, self.tr_("tab.update"),
                                                self.tr_("up.confirm").format(info["version"]))
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        import threading
        self.up_install.setEnabled(False)
        self.up_check.setEnabled(False)
        self.up_status.setText(self.tr_("up.downloading").format(""))

        def work():
            try:
                cmd = self._updater.prepare_update(info, progress=lambda d, t: self.update_progress.emit(d, t))
                self.update_prepared.emit(cmd, "")
            except Exception as e:
                self.update_prepared.emit(None, str(e) or e.__class__.__name__)
        threading.Thread(target=work, daemon=True).start()

    def _on_update_progress(self, done, total):
        amount = f"{done * 100 // total}%" if total else f"{done // 1024} KB"
        self.up_status.setText(self.tr_("up.downloading").format(amount))

    def _on_update_prepared(self, cmd, error):
        if not cmd:
            self.up_status.setText(self.tr_("up.install_failed").format(error))
            self.up_install.setEnabled(True)
            self.up_check.setEnabled(True)
            return
        if self._save_timer.isActive():   # nothing the user just changed is lost
            self._save_timer.stop()
            self._save()
        self._updater.run_detached(cmd)   # waits for this app to quit, copies, restarts it
        QtWidgets.QApplication.quit()

    def _build_obs_tab(self):
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        self.obs_title = QtWidgets.QLabel()
        self.obs_title.setStyleSheet("font-weight:bold; font-size:14px;")
        lay.addWidget(self.obs_title)
        self.obs_steps = QtWidgets.QLabel()
        self.obs_steps.setWordWrap(True)
        self.obs_steps.setTextFormat(QtCore.Qt.TextFormat.RichText)
        lay.addWidget(self.obs_steps)
        self.obs_path = QtWidgets.QLineEdit(str(OBS_PAGE))
        self.obs_path.setReadOnly(True)
        lay.addWidget(self.obs_path)
        self.obs_copy, self.obs_open = QtWidgets.QPushButton(), QtWidgets.QPushButton()
        self.obs_copy.clicked.connect(self._copy_obs_path)
        self.obs_open.clicked.connect(
            lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(OBS_PAGE))))
        lay.addWidget(_hbox(self.obs_copy, self.obs_open))
        self.obs_note = QtWidgets.QLabel()
        self.obs_note.setWordWrap(True)
        self.obs_note.setStyleSheet("color:#71717a;")
        lay.addWidget(self.obs_note)
        lay.addStretch(1)
        return page

    def _copy_obs_path(self):
        QtWidgets.QApplication.clipboard().setText(str(OBS_PAGE))
        self.obs_copy.setText(self.tr_("obs_copied"))
        QtCore.QTimer.singleShot(1500, lambda: self.obs_copy.setText(self.tr_("obs_copy")))

    def tr_(self, key):
        return TEXT[key][self.lang]

    def retranslate(self):
        """Sets every visible string for the current language."""
        t = self.tr_
        self.setWindowTitle(t("title"))
        self._paint_enabled()
        names = DEFAULT_LABELS_EN if self.lang == "en" else DEFAULT_LABELS
        for key, e in self.label_edits.items():
            e.setPlaceholderText(names[key])
            self.label_names[key].setText(names[key])
        for i, key in enumerate(("tab.look", "tab.show", "tab.place", "tab.obs", "tab.update")):
            self.tabs.setTabText(i, t(key))
        self.obs_title.setText(t("obs_title"))
        self.up_current.setText(t("up.current").format(self._version))
        self.up_check_on_start.setText(t("up.check_on_start"))
        self.up_check.setText(t("up.check"))
        self.up_install.setText(t("up.install"))
        self.up_notes_title.setText(t("up.notes"))
        self.up_note.setText(t("up.note"))
        self.obs_steps.setText(t("obs_steps"))
        self.obs_copy.setText(t("obs_copy"))
        self.obs_open.setText(t("obs_open"))
        self.obs_note.setText(t("obs_note"))
        self.design_box.setTitle(t("design_pick"))
        for key, card in self.style_cards.items():
            card.setText(t("style." + key))
        for key, lab in self._row_labels.items():
            lab.setText(t(key))
        self._row_labels["bg_color"].setText(t(self._color_key("bg_color")))
        self.items_box.setTitle(t("items"))
        self.items_hint.setText(t("items_hint"))
        self.items.blockSignals(True)   # renaming rows isn't an edit
        for i in range(self.items.count()):
            it = self.items.item(i)
            it.setText(t("item." + it.data(QtCore.Qt.ItemDataRole.UserRole)))
        self.items.blockSignals(False)
        self.item_up.setText(t("move_up"))
        self.item_down.setText(t("move_down"))
        self.labels_box.setTitle(t("labels"))
        self.parts_box.setTitle(t("parts_shown"))
        self.show_clock.setText(t("show_clock"))
        for i, key in enumerate(PLAYER_ORDER):
            self.players.setItemText(i, t("pl." + key))
        self.opener_seconds.setSuffix(" 秒" if self.lang == "ja" else " s")
        self.opener_seconds.setSpecialValueText(t("os.forever"))
        for i, key in enumerate(OPENER_LANGUAGES):
            self.opener_language.setItemText(i, t("ol." + key))
        self.always_show.setText(t("always_show"))
        self.show_event_log.setText(t("show_event_log"))
        self.show_summary.setText(t("show_summary"))
        self.summary_items.blockSignals(True)   # renaming rows isn't an edit
        for i in range(self.summary_items.count()):
            it = self.summary_items.item(i)
            it.setText(t("sum." + it.data(QtCore.Qt.ItemDataRole.UserRole)))
        self.summary_items.blockSignals(False)
        self.show_opener.setText(t("show_opener"))
        for i, key in enumerate(OPENER_DISPLAY_ORDER):
            self.opener_display.setItemText(i, t("od." + key))
        self.event_log_count.setSuffix(t("count_suffix"))
        self.presets_box.setTitle(t("presets"))
        if self.preset_box.count():
            self.preset_box.setItemText(0, t("preset_pick"))
        self.preset_save.setText(t("preset_save"))
        self.preset_delete.setText(t("preset_delete"))
        self.preset_export.setText(t("preset_export"))
        self.preset_import.setText(t("preset_import"))
        self.text_box.setTitle(t("text_group"))
        self.tw_thin.setText(t("tw.thin"))
        self.tw_thick.setText(t("tw.thick"))
        self.text_outline.setText(t("text_outline"))
        self.font_box.setItemText(0, t("font_default"))
        self.font_load.setText(t("font_load"))
        self.look_box.setTitle(t("look_group"))
        for i, key in enumerate(LOOK_TARGETS):
            self.look_target.setItemText(i, t("lt." + key))
        self._label_part_reset()
        for reset in self.color_resets.values():
            reset.setText(t("color_reset"))
        self.player_box.setTitle(t("player_colors"))
        for key in self.player_resets:
            self.player_resets[key].setText(t("color_reset"))
        self.position.setItemText(0, t("pos.left"))
        self.position.setItemText(1, t("pos.right"))
        self.position_section.setTitle(t("adjust"))
        self.move_label.setText(t("move_what"))
        for i, key in enumerate(TARGET_ORDER):
            self.target_box.setItemText(i, t("target." + key))
        self.drag_each_side.setText(t("drag_each_side"))
        for b, key in self.arrow_buttons:
            b.setToolTip(t(key))
        self.center_button.setToolTip(t("reset_pos"))
        self.drag_button.setText(t("drag_done") if self.drag_button.isChecked() else t("drag"))
        self.hint.setText(t("hint") + (t("hint_drag") if self._drag_available else ""))
        self.note.setText(t("note"))
        self.reset_button.setText(t("reset_all"))
        self.close_button.setText(t("close"))
        self.on_top_check.setText(t("settings_on_top"))
        self.show_on_hud.setText(t("show_on_hud"))
        self.show_on_obs.setText(t("show_on_obs"))
        for c in (self.show_on_hud, self.show_on_obs):
            c.setToolTip(t("show_on_tip"))
        self._update_offset_label()
        self._show_look()
        self.adjustSize()

    def _language_changed(self, *_):
        self.lang = self.language.currentData()
        self.retranslate()
        self._changed()

    # --- design cards ---
    def _style_picked(self, index):
        self._style = STYLE_ORDER[index]
        self._show_look()   # the background row means the lines in "minimal"
        self._changed()

    def _show_style(self):
        card = self.style_cards.get(self._style)
        if card is not None:
            card.setChecked(True)

    def _refresh_previews(self):
        """Redraws every card with the current colors / font / rows."""
        d = self.values()
        for key, card in self.style_cards.items():
            pm = render_style_preview(key, d)
            if pm is not None:
                card.setIcon(QtGui.QIcon(pm))

    # --- size / colors / background, overall or per part ---
    def _look_value(self, key):
        if self._look_target == "all":
            return self._overall[key]
        return self._parts[self._look_target].get(key, self._overall[key])

    def _show_look(self):
        """Puts the current target's values (its own, or the overall ones it
        follows) into the controls."""
        loading, self._loading = self._loading, True
        part = self._look_target != "all"
        self.scale.setValue(int(round(self._look_value("scale") * 100)))
        self.opacity.setValue(int(round(self._look_value("background_opacity") * 100)))
        for key in ("bg_color", "text_color"):
            self._paint_color_button(self.color_buttons[key], self._look_value(self._color_key(key)))
        self._row_labels["bg_color"].setText(self.tr_(self._color_key("bg_color")))
        self._label_part_reset()
        self._loading = loading

    def _look_target_changed(self, *_):
        self._look_target = self.look_target.currentData()
        self._show_look()

    def _look_edited(self, key, value):
        if self._loading:
            return
        if self._look_target == "all":
            # 全体 means every part at once: parts that had their own value for
            # this follow the new one too (user report: changing the background
            # color with 全体 picked left the numbers' own black as it was)
            self._overall[key] = value
            for own in self._parts.values():
                own.pop(key, None)
        else:
            self._parts[self._look_target][key] = value
        self._show_look()
        self._changed()

    def _color_key(self, key):
        """The setting a color row edits: the background row is the lines' color in "minimal"."""
        return "line_color" if key == "bg_color" and self._style == "minimal" else key

    def _pick_look_color(self, key):
        key = self._color_key(key)
        c = QtWidgets.QColorDialog.getColor(QtGui.QColor(self._look_value(key)), self, self.tr_(key))
        if c.isValid():
            self._look_edited(key, c.name())

    def _reset_look_color(self, key):
        """元に戻す: the overall color back to its default; a part's back to the overall one."""
        key = self._color_key(key)
        if self._look_target == "all":
            self._overall[key] = DISPLAY_DEFAULTS[key]
            for own in self._parts.values():
                own.pop(key, None)
        else:
            self._parts[self._look_target].pop(key, None)
        self._show_look()
        self._changed()

    def _label_part_reset(self):
        # the one button (user's choice): usable while a part is picked
        self.part_reset.setText(self.tr_("part_to_all"))
        self.part_reset.setEnabled(self._look_target != "all")

    def _part_to_all(self):
        """全体をこの色に合わせる: the picked part's colors (background, text,
        minimal's lines) become the overall ones, and every part follows them.
        Sizes and background strength stay as they are (user's request)."""
        if self._look_target == "all":
            return
        colors = {k: self._look_value(k) for k in COLOR_KEYS}
        self._overall.update(colors)
        for own in self._parts.values():
            for k in COLOR_KEYS:
                own.pop(k, None)
        self._show_look()
        self._changed()

    @staticmethod
    def _paint_color_button(button, hex_value):
        button.setText(hex_value.upper())
        light = QtGui.QColor(hex_value).lightness() > 140
        button.setStyleSheet(f"background:{hex_value}; color:{'#111' if light else '#fff'};")

    # --- player colors ---
    def _set_player_color(self, key, hex_value, changed=False):
        self._player_colors[key] = hex_value
        self._paint_color_button(self.player_buttons[key], hex_value)
        if changed:
            self._changed()

    def _pick_player_color(self, key):
        c = QtWidgets.QColorDialog.getColor(QtGui.QColor(self._player_colors[key]), self, self.tr_(key))
        if c.isValid():
            self._set_player_color(key, c.name(), changed=True)

    # --- presets ---
    def _presets(self):
        p = load_settings().get("presets")
        return p if isinstance(p, dict) else {}

    def _refresh_presets(self, select=None):
        self.preset_box.blockSignals(True)
        self.preset_box.clear()
        self.preset_box.addItem(self.tr_("preset_pick"), None)
        for name in sorted(self._presets()):
            self.preset_box.addItem(name, name)
        if select is not None:
            self.preset_box.setCurrentIndex(max(0, self.preset_box.findData(select)))
        self.preset_box.blockSignals(False)

    def _store_presets(self, presets):
        settings = load_settings()
        settings["presets"] = presets
        settings["display"] = self.values()
        save_settings(settings)

    def _apply_preset(self, index):
        name = self.preset_box.itemData(index)
        look = self._presets().get(name)
        if not isinstance(look, dict):
            return
        # the viewer's language stays; everything else comes from the preset
        self._show_values(display_settings({"display": {**look, "language": self.lang}}))
        self._changed()

    def _save_preset(self):
        name, ok = QtWidgets.QInputDialog.getText(self, self.tr_("presets"), self.tr_("preset_name"),
                                                  text=self.preset_box.currentData() or "")
        name = re.sub(r"[\x00-\x1f]", "", name or "").strip()[:40]
        if not ok or not name:
            return
        presets = self._presets()
        presets[name] = preset_of(self.values())
        self._store_presets(presets)
        self._refresh_presets(select=name)

    def _delete_preset(self):
        name = self.preset_box.currentData()
        if not name:
            return
        answer = QtWidgets.QMessageBox.question(
            self, self.tr_("confirm_title"), self.tr_("delete_confirm").format(name),
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No)
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        presets = self._presets()
        presets.pop(name, None)
        self._store_presets(presets)
        self._refresh_presets()

    def _export_preset(self):
        name = self.preset_box.currentData() or "preset"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, self.tr_("preset_export"),
                                                        f"{name}.json", "Preset (*.json)")
        if not path:
            return
        look = self._presets().get(name) if self.preset_box.currentData() else None
        display = display_settings({"display": look}) if isinstance(look, dict) else self.values()
        Path(path).write_text(json.dumps(preset_file(name, display), ensure_ascii=False, indent=2), encoding="utf-8")

    def _import_preset(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, self.tr_("preset_import"), "", "Preset (*.json)")
        if not path:
            return
        try:
            name, look = read_preset_file(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, ValueError):
            QtWidgets.QMessageBox.warning(self, self.tr_("presets"), self.tr_("preset_bad"))
            return
        presets = self._presets()
        base, n = name, 2
        while name in presets:
            name, n = f"{base} ({n})", n + 1
        presets[name] = look
        self._store_presets(presets)
        self._refresh_presets(select=name)
        self._apply_preset(self.preset_box.currentIndex())

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
        self.target_box = QtWidgets.QComboBox()   # 9 choices: a dropdown, not a row of buttons
        for key in TARGET_ORDER:
            self.target_box.addItem("", key)
        self.target_box.setCurrentIndex(TARGET_ORDER.index(self._target))
        self.target_box.currentIndexChanged.connect(self._target_changed)
        targets.addWidget(self.target_box, 1)
        outer.addLayout(targets)
        self.drag_each_side = QtWidgets.QCheckBox()
        self.drag_each_side.toggled.connect(self._changed)
        outer.addWidget(self.drag_each_side)

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

    def _target_changed(self, *_):
        self._target = self.target_box.currentData()
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

    def set_part_scale_from_hud(self, part, size):
        """The wheel resized a part on the HUD (already shown): keep it as that
        part's own size, show it if that part is the one being edited, save."""
        self._parts[part]["scale"] = size
        if self._look_target == part:
            self._show_look()
        self._save_timer.start()

    def set_offset_from_hud(self, target, x, y, finished):
        """The user dragged a part on the HUD (already moved there): show it
        as the part being adjusted, and save once the drag ends."""
        if target != self._target:
            self.target_box.setCurrentIndex(TARGET_ORDER.index(target))
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

    def open(self, activate=True):
        """Shows the window with the values currently in the file. activate=False
        (on start-up): shown without taking the focus from the game, which
        pauses itself when it loses focus."""
        self._show_values(display_settings(load_settings()))
        self._refresh_presets()
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, not activate)
        self.show()
        exclude_from_capture(self)
        if activate:
            self.raise_()
            self.activateWindow()

    def _show_values(self, d):
        self._loading = True
        self.language.setCurrentIndex(self.language.findData(d["language"]))
        self.lang = d["language"]
        self._style = d["style"]
        self._show_style()
        self.position.setCurrentIndex(self.position.findData(d["stats_position"]))
        for key, (kx, ky) in TARGET_KEYS.items():
            self._set_offset(key, d[kx], d[ky])
        self.drag_each_side.setChecked(d["drag_each_side"])
        # stat rows: the shown ones first in their order (ticked), the rest after
        shown = list(d["stat_items"])
        order = shown + [k for k in STAT_ITEMS if k not in shown]
        items = {self.items.item(i).data(QtCore.Qt.ItemDataRole.UserRole): self.items.item(i)
                 for i in range(self.items.count())}
        for key in list(items):
            self.items.takeItem(self.items.row(items[key]))
        for key in order:
            items[key].setCheckState(QtCore.Qt.CheckState.Checked if key in shown
                                     else QtCore.Qt.CheckState.Unchecked)
            self.items.addItem(items[key])
        for key, e in self.label_edits.items():
            e.setText(d["labels"].get(key, ""))
        self.text_weight.setValue(int(d["text_weight"]))
        self.text_outline.setChecked(d["text_outline"])
        self._overall = {k: d[k] for k in LOOK_KEYS}
        self._parts = {p: dict(d["parts"].get(p, {})) for p in PARTS}
        for key in self._player_colors:
            self._set_player_color(key, d[key])
        self._font_file = d["font_file"]
        self._font_loaded_family = (self._register_font_file(USER_FONTS.parent / d["font_file"])
                                    if d["font_file"] else None)
        i = self.font_box.findData(d["font_family"])
        if i < 0:
            self.font_box.addItem(d["font_family"], d["font_family"])
            i = self.font_box.count() - 1
        self.font_box.setCurrentIndex(i)
        self.show_clock.setChecked(d["show_clock"])
        self.always_show.setChecked(d["always_show"])
        self._enabled, self._force = d["enabled"], d["force_show"]
        self.show_on_hud.setChecked(d["show_on_hud"])
        self.show_on_obs.setChecked(d["show_on_obs"])
        self._paint_enabled()
        self.players.setCurrentIndex(max(0, self.players.findData(d["players"])))
        self.opener_language.setCurrentIndex(max(0, self.opener_language.findData(d["opener_language"])))
        self.opener_seconds.setValue(d["opener_seconds"])
        self.show_event_log.setChecked(d["show_event_log"])
        self.show_summary.setChecked(d["show_summary"])
        for i in range(self.summary_items.count()):
            it = self.summary_items.item(i)
            it.setCheckState(QtCore.Qt.CheckState.Checked if it.data(QtCore.Qt.ItemDataRole.UserRole)
                             in d["summary_items"] else QtCore.Qt.CheckState.Unchecked)
        self.show_opener.setChecked(d["show_opener"])
        self.opener_display.setCurrentIndex(self.opener_display.findData(d["opener_display"]))
        self.opener_display.setEnabled(d["show_opener"])
        self.event_log_count.setValue(d["event_log_count"])
        self.event_log_count.setEnabled(d["show_event_log"])
        self.retranslate()
        self._loading = False
        self._preview_timer.start()

    def values(self):
        items = [self.items.item(i) for i in range(self.items.count())]
        d = {
            "language": self.language.currentData(),
            "style": self._style,
            "stats_position": self.position.currentData(),
            **self._overall,
            "parts": {p: dict(v) for p, v in self._parts.items()},
            "stat_items": [it.data(QtCore.Qt.ItemDataRole.UserRole) for it in items
                           if it.checkState() == QtCore.Qt.CheckState.Checked],
            "labels": {k: e.text().strip() for k, e in self.label_edits.items() if e.text().strip()},
            **self._player_colors,
            "text_weight": self.text_weight.value(),
            "text_outline": self.text_outline.isChecked(),
            "font_family": self.font_box.currentData() or "",
            "font_file": self._font_file,
            "show_clock": self.show_clock.isChecked(),
            "always_show": self.always_show.isChecked(),
            "enabled": self._enabled,
            "force_show": self._enabled and self._force,
            "show_on_hud": self.show_on_hud.isChecked(),
            "show_on_obs": self.show_on_obs.isChecked(),
            "players": self.players.currentData(),
            "opener_seconds": self.opener_seconds.value(),
            "opener_language": self.opener_language.currentData(),
            "show_event_log": self.show_event_log.isChecked(),
            "show_summary": self.show_summary.isChecked(),
            "summary_items": [self.summary_items.item(i).data(QtCore.Qt.ItemDataRole.UserRole)
                              for i in range(self.summary_items.count())
                              if self.summary_items.item(i).checkState() == QtCore.Qt.CheckState.Checked],
            "show_opener": self.show_opener.isChecked(),
            "opener_display": self.opener_display.currentData(),
            "event_log_count": self.event_log_count.value(),
        }
        for key, (kx, ky) in TARGET_KEYS.items():
            d[kx], d[ky] = self._offsets[key]
        d["drag_each_side"] = self.drag_each_side.isChecked()
        return display_settings({"display": d})

    # --- font ---
    def _register_font_file(self, path):
        """Registers a font file with Qt and returns its family name ("" if it isn't a font)."""
        fid = QtGui.QFontDatabase.addApplicationFont(str(path))
        fams = QtGui.QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        if fams and self.font_box.findData(fams[0]) < 0:
            self.font_box.addItem(fams[0], fams[0])
        return fams[0] if fams else ""

    def _load_font(self):
        """Copies the chosen font file into assets/user_fonts/ (where the OBS page
        can load it too) and selects the family it contains."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, self.tr_("font_load_title"), "", "Fonts (*.ttf *.otf *.ttc)")
        if not path:
            return
        src = Path(path)
        name = re.sub(r"[^\w.\-]+", "_", src.stem)[:100] + src.suffix.lower()
        USER_FONTS.mkdir(parents=True, exist_ok=True)
        dest = USER_FONTS / name
        if src.resolve() != dest.resolve():
            shutil.copyfile(src, dest)
        family = self._register_font_file(dest)
        if not family:
            QtWidgets.QMessageBox.warning(self, self.tr_("font"), self.tr_("font_load_failed"))
            return
        self._font_file = f"user_fonts/{name}"
        self._font_loaded_family = family
        self.font_box.setCurrentIndex(self.font_box.findData(family))
        self._changed()

    def _font_changed(self, *_):
        if self._loading:
            return
        # picking some other family drops the loaded file (it's only for its own family)
        if self._font_file and self.font_box.currentData() != self._font_loaded_family:
            self._font_file = ""
        self._changed()

    def _changed(self, *_):
        if self._loading:
            return
        self.event_log_count.setEnabled(self.show_event_log.isChecked())
        self.opener_display.setEnabled(self.show_opener.isChecked())
        self.display_changed.emit(self.values())
        self._save_timer.start()
        self._preview_timer.start()

    def _reset(self):
        answer = QtWidgets.QMessageBox.question(
            self, self.tr_("confirm_title"), self.tr_("reset_confirm"),
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No)
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        # keep the chosen language: resetting the display shouldn't switch it
        self._show_values(display_settings({"display": {**DISPLAY_DEFAULTS, "language": self.lang}}))
        self._changed()

    def _set_settings_on_top(self, enabled):
        self._settings_on_top = bool(enabled)
        was_visible = self.isVisible()
        self.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint, self._settings_on_top)
        if was_visible:
            self.show()
            self.raise_()
        settings = load_settings()
        preferences = settings.get("ui", {})
        preferences["settings_on_top"] = self._settings_on_top
        settings["ui"] = preferences
        save_settings(settings)

    def _save(self):
        settings = load_settings()  # keep everything else in the file (presets included) as it is
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
