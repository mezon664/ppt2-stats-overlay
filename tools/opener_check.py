"""A page to judge the opener names the app gave, from server.log.

Every "named X from board ..." line in logs/server.log* is one naming; the
same name on the same board is one card (with how often). Each card shows the
board (pieces colored by kind, from the landed pieces in the log), the name
given, the name the current code gives that board, and the opener's own
shapes from the wiki. The user marks each 合ってる / 違う (with the right name)
/ わからない; the marks stay in the browser and come out as text to paste.

    python tools/opener_check.py   ->  debug_frames/opener_check/index.html
"""
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import opener_detect as od  # noqa: E402

COLS = od.COLS
LINE = re.compile(r"\[(left|right)\] named (.+?) from board (\S+) \| landed (.*?)(?: \| hold \S+)? \| placements (\d+)")
COLORS = {"I": "#3ec6e8", "O": "#f2d43a", "T": "#b04fd0", "S": "#5ec34a", "Z": "#e5443a",
          "J": "#3a62e0", "L": "#f08a2a", None: "#9a9a9a"}


def parse(drawing):
    m = 0
    for r, row in enumerate(reversed(drawing.split("/"))):
        for c, ch in enumerate(row):
            if ch == "#":
                m |= 1 << (r * COLS + c)
    return m


def svg(mask, kinds=None, cell=14):
    rows = max((i // COLS for i in range(od.MASK_ROWS * COLS) if mask >> i & 1), default=0) + 2
    rows = max(rows, 5)
    out = [f'<svg width="{COLS * cell}" height="{rows * cell}" viewBox="0 0 {COLS * cell} {rows * cell}">',
           f'<defs><pattern id="g{cell}" width="{cell}" height="{cell}" patternUnits="userSpaceOnUse">'
           f'<rect width="{cell}" height="{cell}" fill="#1d1d22" stroke="#2c2c33"/></pattern></defs>'
           f'<rect width="100%" height="100%" fill="url(#g{cell})"/>']
    for r in range(rows):
        for c in range(COLS):
            bit = 1 << (r * COLS + c)
            x, y = c * cell, (rows - 1 - r) * cell
            if mask & bit:
                color = COLORS[(kinds or {}).get(bit)]
                out.append(f'<rect x="{x + .5}" y="{y + .5}" width="{cell - 1}" height="{cell - 1}" fill="{color}"/>')
    return "".join(out) + "</svg>"


def main():
    logs = sorted(ROOT.glob("logs/server.log*"), reverse=True)
    seen = Counter()
    first = {}
    for log in logs:
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            m = LINE.search(line)
            if not m:
                continue
            side, name, board, landed, placements = m.groups()
            key = (name, board)
            seen[key] += 1
            first.setdefault(key, (landed, line[:19]))
    index = od.openers()
    data = json.loads(od.OPENERS_PATH.read_text(encoding="utf-8"))
    shapes_of = {}
    for op in data["openers"]:
        shapes_of.setdefault(od.screen_name(op.get("display") or op["name"]), []).extend(op["shapes"])

    cards = []
    for n, ((name, board), count) in enumerate(seen.most_common()):
        landed, when = first[(name, board)]
        mask = parse(board)
        kinds = {}
        for p in landed.split():
            pm = parse(p)
            k = od._kind(pm)
            for i in range(od.MASK_ROWS * COLS):
                if pm >> i & 1 and mask >> i & 1:
                    kinds[1 << i] = k
        rows = [[bool(mask >> (r * COLS + c) & 1) for c in range(COLS)] for r in range(od.ROWS)]
        now = od.shown_name(index.match(rows)) or name   # (no exact shape: named with HOLD, not redone here)
        refs = []
        for single in [s.strip() for s in re.sub(r" ほか$", "", name).split(" / ")]:
            for f in shapes_of.get(single, [])[:4]:
                refs.append((single, svg(od._mask(od._shape_rows(f)), cell=8)))
        ref_html = "".join(f'<figure>{s}<figcaption>{html.escape(t)}</figcaption></figure>' for t, s in refs)
        changed = "" if now == name else f'<div class="now">今のコードだと: {html.escape(now)}</div>'
        cards.append(f'''<section class="card" data-id="{n}" data-name="{html.escape(name)}" data-board="{board}">
  <div class="head"><span class="no">#{n + 1}</span><b>{html.escape(name)}</b><span class="cnt">{count}回</span></div>
  <div class="body"><div class="board">{svg(mask, kinds)}</div>
    <div class="refs"><div class="lbl">Wikiの形</div><div class="figs">{ref_html or "（なし）"}</div></div></div>
  {changed}
  <div class="btns"><button data-v="ok">合ってる</button><button data-v="ng">違う</button><button data-v="unk">わからない</button>
    <input placeholder="正しいテンプレ名（違うとき）"></div>
</section>''')

    page = (ROOT / "tools" / "opener_check_page.html").read_text(encoding="utf-8")
    page = page.replace("<!--CARDS-->", "\n".join(cards)).replace("<!--TOTAL-->", str(len(cards)))
    out = ROOT / "debug_frames" / "opener_check" / "index.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    print(out, len(cards), "cards from", sum(seen.values()), "namings")


if __name__ == "__main__":
    main()
