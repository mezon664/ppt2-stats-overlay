"""Draw the same state with the HUD (hud/overlay.py) and the OBS page
(obs/overlay.html, in headless Edge) and compare them pixel by pixel.

    python tools/validation/hud_vs_obs.py OUT_DIR [style ...]

For each case it writes OUT_DIR/<case>.png: HUD | OBS | difference
(red = where they differ), and prints how much of the picture differs.
"""
import json
import os
import subprocess
import time
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hud"))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np
import cv2
from PyQt6 import QtCore, QtGui, QtWidgets

import overlay
from config_store import DISPLAY_DEFAULTS

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
W, H = overlay.REFERENCE_W, overlay.REFERENCE_H
BG = (70, 90, 110)   # BGR backdrop both are put on (a mid color shows edges and see-through parts)

LEFT = {"opener": "パフェ積み(中あけ)", "opener_en": "PC Opener", "opener_age_s": 0.5,
        "pps": 2.09, "app": 0.62, "apm": {"apm": 77.8}, "attack": 112, "pieces": 181, "ren": 3, "b2b": 2,
        "match_stats": {"lines_sent": 112, "pieces": 181, "max_ren": 5, "tetris": 6, "tspin": 9, "perfect_clear": 1},
        "event_log": [{"text": "T-SPIN Double +4", "text_en": "T-SPIN Double +4"},
                      {"text": "TETRIS +4 BtB", "text_en": "TETRIS +4 BtB"}]}
RIGHT = {"opener": "合掌TSD", "opener_en": "Gassho TSD", "opener_age_s": 0.5,
         "pps": 1.74, "app": 0.41, "apm": {"apm": 43.2}, "attack": 62, "pieces": 151, "ren": 0, "b2b": 0,
         "match_stats": {"lines_sent": 62, "pieces": 151, "max_ren": 3, "tetris": 2, "tspin": 4, "perfect_clear": 0},
         "event_log": [{"text": "Single +0", "text_en": "Single +0"}]}


def state_for(display, frozen=False):
    if display.get("_vs_puyo"):   # 2P plays Puyo Puyo
        st = state_for({k: v for k, v in display.items() if k != "_vs_puyo"}, frozen)
        st["right"] = {"puyo": True}
        return st
    return {"match_elapsed_s": 86.6, "frozen": frozen, "display": display, "match_screen": True,
            "left": json.loads(json.dumps(LEFT)), "right": json.loads(json.dumps(RIGHT)),
            "capture": {"ok": True}}


def hud_image(app, display, frozen):
    settings = {"hud": {"follow_game": False, "position": {"x": 0, "y": 0}},
                "server": {"host": "127.0.0.1", "port": 1}, "display": display}
    overlay.WsClient.start = lambda self: None
    win = overlay.HudWindow(settings)
    win._size = (W, H)
    win._scale = 1.0
    win.apply_display(overlay.display_settings({"display": {k: v for k, v in display.items() if k != "_vs_puyo"}}))
    win._layout()
    win.on_state(state_for(display, frozen))
    win._place_openers()
    app.processEvents()
    pm = win.grab()
    img = pm.toImage().convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    rgba = np.frombuffer(ptr, np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)[:, :img.width()].copy()
    win.deleteLater()
    return over_bg(rgba[:, :, [2, 1, 0, 3]])   # -> BGRA


def obs_image(display, frozen, work):
    page = (ROOT / "obs" / "overlay.html").read_text(encoding="utf-8")
    assets = (ROOT / "assets").as_uri() + "/"
    page = page.replace('"../assets/', '"' + assets).replace("url(\"../assets/", "url(\"" + assets)
    # no server: draw this state once; no fades in between
    page = page.replace("connect();\n</script>",
                        "connected = true; render(" + json.dumps(state_for(display, frozen), ensure_ascii=False)
                        + ");\n</script>")
    page = page.replace("</style>", "* { transition: none !important; }\n</style>", 1)
    html = work / "obs_case.html"
    html.write_text(page, encoding="utf-8")
    shot = work / "obs_case.png"
    if shot.exists():
        shot.unlink()
    subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                    "--default-background-color=00000000", f"--user-data-dir={work / 'edge'}", f"--window-size={W},{H}",
                    "--virtual-time-budget=1500", f"--screenshot={shot}", html.as_uri()],
                   check=True, capture_output=True, timeout=60)
    # msedge.exe hands the work to another process and returns before the shot is written
    img, t0 = None, time.monotonic()
    while img is None and time.monotonic() - t0 < 30:
        time.sleep(0.3)
        if shot.exists():
            img = cv2.imread(str(shot), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise RuntimeError("Edge wrote no screenshot")
    if img.shape[2] == 3:
        img = np.dstack([img, np.full(img.shape[:2], 255, np.uint8)])
    return over_bg_obs(img[:H, :W])


def _to_linear(v):
    return np.where(v <= 0.04045, v / 12.92, ((v + 0.055) / 1.055) ** 2.4)


def _to_srgb(v):
    return np.where(v <= 0.0031308, v * 12.92, 1.055 * np.clip(v, 0, None) ** (1 / 2.4) - 0.055)


def over_bg_obs(bgra):
    """The page on the backdrop the way OBS lays a browser source on the scene:
    its premultiplied colors made linear, blended in linear light."""
    a = bgra[:, :, 3:4].astype(np.float32) / 255
    pre = bgra[:, :, :3].astype(np.float32) / 255 * a
    bg = np.empty(bgra.shape[:2] + (3,), np.float32)
    bg[:] = np.array(BG, np.float32) / 255
    out = _to_srgb(_to_linear(pre) + _to_linear(bg) * (1 - a))
    return np.clip(out * 255 + 0.5, 0, 255).astype(np.uint8)


def over_bg(bgra):
    a = bgra[:, :, 3:4].astype(np.float32) / 255
    bg = np.empty(bgra.shape[:2] + (3,), np.float32)
    bg[:] = BG
    # Qt's grab and the screenshot are both straight (not premultiplied) alpha
    return (bgra[:, :, :3].astype(np.float32) * a + bg * (1 - a)).astype(np.uint8)


def compare(a, b, zoom=3):
    """How much differs (% of the picture), and a picture of each drawn part
    zoomed: HUD | OBS | difference (red) side by side, the parts stacked."""
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16)).max(axis=2)
    mask = diff > 40
    drawn = ((np.abs(a.astype(np.int16) - BG).max(axis=2) > 8)
             | (np.abs(b.astype(np.int16) - BG).max(axis=2) > 8)).astype(np.uint8)
    drawn = cv2.dilate(drawn, np.ones((25, 25), np.uint8))
    n, _, boxes, _ = cv2.connectedComponentsWithStats(drawn)
    rows = []
    for x, y, w, h, area in sorted(boxes[1:].tolist(), key=lambda r: (r[1], r[0])):
        if area < 50:
            continue
        sl = (slice(y, y + h), slice(x, x + w))
        vis = (a[sl].astype(np.float32) * 0.35).astype(np.uint8)
        vis[mask[sl]] = (0, 0, 255)
        gap = np.full((h, 6, 3), 255, np.uint8)
        row = np.hstack([a[sl], gap, b[sl], gap, vis])
        rows.append(cv2.resize(row, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_NEAREST))
    width = max((r.shape[1] for r in rows), default=10)
    rows = [np.pad(r, ((0, 10), (0, width - r.shape[1]), (0, 0)), constant_values=255) for r in rows]
    return mask.mean() * 100, (np.vstack(rows) if rows else a)


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    styles = sys.argv[2:] or ["band", "pop", "gauge", "text", "versus", "simple",
                              "frame", "slash", "hex", "meter", "tower", "minimal", "trend"]
    app = QtWidgets.QApplication(sys.argv[:1])
    cases = []
    for st in styles:
        cases.append((f"{st}", dict(DISPLAY_DEFAULTS, style=st, show_event_log=True), False))
        cases.append((f"{st}_summary", dict(DISPLAY_DEFAULTS, style=st), True))
    cases.append(("vs_puyo", dict(DISPLAY_DEFAULTS, _vs_puyo=True), False))
    for om in ("hold", "namebar", "top"):
        cases.append((f"opener_{om}", dict(DISPLAY_DEFAULTS, opener_display=om), False))
    for name, display, frozen in cases:
        a = hud_image(app, display, frozen)
        b = obs_image(display, frozen, out)
        pct, vis = compare(a, b)
        cv2.imwrite(str(out / f"{name}.png"), vis)
        print(f"{name:20s} differs {pct:5.2f}%")


if __name__ == "__main__":
    main()
