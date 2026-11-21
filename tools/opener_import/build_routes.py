"""Builds assets/opener_routes.json: what each opener goes on to (its 派生).

wiki_routes_raw.json: for every page of テトリステンプレ整理Wiki's テンプレ一覧,
the テト譜 links with the heading they're under ({page: [[heading, label,
fumen]]}), collected through the browser (the site refuses plain requests, see
docs/opener_import_progress.md).

Kept: links under a 派生 heading whose テト譜 has a board that goes on from the
opener: holding one of its shapes as it stands, or as it is after its T-spin
cleared its full rows.

    python tools/opener_import/build_routes.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from fumen import decode  # noqa: E402
from opener_detect import screen_name  # noqa: E402
import opener_practice as op  # noqa: E402

RAW = Path(__file__).with_name("wiki_routes_raw.json")
OUT = ROOT / "assets" / "opener_routes.json"


def after_clear(cells):
    """The shape with its full rows gone (what's left after its T-spin)."""
    full = {y for _, y in cells if all((x, y) in cells for x in range(op.COLS))}
    return frozenset((x, y - sum(1 for f in full if f < y)) for x, y in cells if y not in full)


def starts(opener):
    out = set()
    for f in opener["shapes"]:
        rows = decode(f)[0].board_with_piece()
        cells = frozenset((x, y) for y, r in enumerate(rows) for x, v in enumerate(r) if v)
        if not cells:
            continue
        out.add(cells)
        left = after_clear(cells)
        if left:
            out.add(left)
    return out


def goes_on(begin, cells):
    """This board holds a start, or is a start one piece short (before its T)."""
    return any(b <= cells or (cells < b and len(b) - len(cells) == 4) for b in begin)


def main():
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    openers = json.loads(op.OPENERS_PATH.read_text(encoding="utf-8"))["openers"]
    routes, links, kept = {}, 0, 0
    for o in openers:
        page = re.search(r"pages/(\d+)", o["page"]).group(1)
        begin = starts(o)
        begin |= {op.mirror_cells(c) for c in begin}
        name = screen_name(o.get("display") or o["name"])
        for head, label, fumen in raw.get(page, []):
            if "派生" not in head or not label or label == "テト譜":
                continue
            links += 1
            try:
                points = op.route_points(fumen)
            except Exception:
                continue
            if not any(goes_on(begin, t.cells) for t in points):
                continue
            have = routes.setdefault(name, [])
            if all(r["name"] != label for r in have):
                have.append({"name": label, "fumen": fumen})
                kept += 1
    OUT.write_text(json.dumps({
        "_about": "Each opener's 派生 from テトリステンプレ整理Wiki (tools/opener_import/build_routes.py).",
        "source": "https://w.atwiki.jp/sasasa123/pages/1851.html",
        "routes": routes}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"openers with routes {len(routes)} / {len(openers)}, routes {kept} of {links} links, "
          f"{OUT.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
