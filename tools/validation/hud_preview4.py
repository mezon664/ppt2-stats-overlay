_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]   # the project folder
import sys, json
sys.path.insert(0, str(_ROOT) + r"\hud")
from PyQt6 import QtWidgets, QtGui
import overlay
app = QtWidgets.QApplication(sys.argv)
settings = overlay.load_settings(); settings["hud"]["follow_game"] = False
overlay.WsClient.start = lambda self: None
win = overlay.HudWindow(settings)
W, H = 1245, 700
win._size = (W, H); win._scale = W / overlay.REFERENCE_W
L = {"opener": "パフェ積み(中あけ)", "opener_age_s": 1.0, "pps": 2.09, "app": 0.62, "apm": {"apm": 77.8}, "match_stats": {"lines_sent": 112, "pieces": 181, "max_ren": 5, "tetris": 6, "tspin": 9, "perfect_clear": 1}}
R = {"opener": "合掌TSD", "opener_age_s": 3.6, "pps": 1.74, "app": 0.41, "apm": {"apm": 43.2}, "match_stats": {"lines_sent": 62, "pieces": 151, "max_ren": 3, "tetris": 2, "tspin": 4, "perfect_clear": 0}}
win.on_state({"match_elapsed_s": 86.6, "frozen": json.loads(sys.argv[4]), "display": json.loads(sys.argv[3]), "left": L, "right": R, "capture": {"ok": True}})
pm = win.grab(); bg = QtGui.QImage(sys.argv[1]); p = QtGui.QPainter(bg); p.drawPixmap(0, 0, pm); p.end(); bg.save(sys.argv[2])
