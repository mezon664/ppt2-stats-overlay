"""English versions of the text the server generates (event log entries and
capture problems). The overlays pick "text" or "text_en" / "message" or
"message_en" by the display.language setting; the HUD's and the settings
window's own strings live with them (hud/overlay.py, hud/settings_window.py,
obs/overlay.html)."""

CLEAR_TYPE_LABEL_EN = {
    "clear_1": "Single",
    "clear_2": "Double",
    "clear_3": "Triple",
    "clear_4": "TETRIS",
    "tspin_double": "T-SPIN Double",
    "tspin_single": "T-SPIN Single",
    "tspin_triple": "T-SPIN Triple",
    "tspin_mini": "T-SPIN Mini Single",
}

REN_BREAK_EN = "Combo ended (no clear)"   # the English game says "Combo" for REN

# Capture problems: the Japanese messages start with these (some carry
# details after them, which are dropped in English).
_CAPTURE_EN = (
    ("ゲームのウインドウが見つかりません", "Game window not found (is the game running?)"),
    ("ゲームが最小化されています", "The game is minimized (keep its window on screen)"),
    ("フルスクリーンでは認識できません", "Can't read the game in fullscreen (switch the game to windowed mode)"),
    ("ウインドウのサイズを取得できません", "Can't get the game window size"),
    ("ウインドウサイズを取得できません", "Can't get the game window size"),
    ("ウインドウのアスペクト比が未対応です", "Unsupported window shape (use a 16:9 window)"),
    ("ウインドウサイズが対応範囲外です", "The game window is too small or too large"),
    ("キャプチャに失敗しました", "Screen capture failed"),
)


def capture_message_en(message):
    for prefix, en in _CAPTURE_EN:
        if message.startswith(prefix):
            return en
    return message
