"""Builds assets/opener_routes.json: what each opener goes on to (its 派生).

wiki_routes_raw.json: for every page of テトリステンプレ整理Wiki's テンプレ一覧,
the テト譜 links with the heading they're under ({page: [[heading, label,
fumen]]}), collected through the browser (the site refuses plain requests, see
docs/opener_import_progress.md).

Kept: links under a 派生 heading whose テト譜 has a board that goes on from the
opener: holding one of its shapes as it stands, or as it is after its T-spin
cleared its full rows.

Links are grouped as the wiki does (wiki_routes_ctx.json: for pages with such
groups, each link's group title and whether it's inside a fold): a "3巡目テト譜"
starts a route named by the line above it (迷走砲's 高火力パフェ型), the links in
its folds are that route's; a link that's only a list of patterns belongs to
the route before it; overview links ("3巡目一覧") are left out.

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
CTX = Path(__file__).with_name("wiki_routes_ctx.json")
MINS = Path(__file__).with_name("wiki_routes_min.json")     # {page: [[heading, label, fumen]]}, labels with 最小 / 最少
OUT = ROOT / "assets" / "opener_routes.json"
PATTERNS = re.compile(r"パターン$|^\d+-\d+$|のリスト$")


def short(title):
    """A group's title, or just its type when it ends in （…型）."""
    m = re.search(r"[（(]([^（）()]*型)[）)]\s*$", title)
    return m.group(1) if m else title.strip()


def grouped(rows, ctx):
    """[(name, [fumen])] of one page's 派生 links, the wiki's way."""
    rows = [r for r in rows if "派生" in r[0] and r[1] and r[1] != "テト譜"]
    if ctx is None or len(ctx) != len(rows):
        ctx = [["", 0]] * len(rows)
    out = []
    for (head, label, fumen), (title, folded) in zip(rows, ctx):
        if re.match(r"^\d巡目一覧", label):
            continue
        if title:                               # "3巡目テト譜"
            out.append((short(title), [fumen]))
        elif out and (folded or PATTERNS.search(label)):
            out[-1][1].append(fumen)
        else:
            out.append((label, [fumen]))
    return out


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


def leads_on(begin, t, until):
    """One bag or so from a start to this board, its colors kept."""
    for b in begin:
        if not b < t.cells or len(t.cells) - len(b) > 32:
            continue
        rows = tuple(sorted({y for _, y in t.cells}))
        if rows == tuple(range(len(rows))) and op._colors_whole(t, b, rows) and op._fits_page(t, b, rows, until):
            return True
    return False


def main():
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    ctxs = json.loads(CTX.read_text(encoding="utf-8"))
    mins = json.loads(MINS.read_text(encoding="utf-8"))
    openers = json.loads(op.OPENERS_PATH.read_text(encoding="utf-8"))["openers"]
    routes, links, kept = {}, 0, 0
    for o in openers:
        page = re.search(r"pages/(\d+)", o["page"]).group(1)
        begin = starts(o)
        begin |= {op.mirror_cells(c) for c in begin}
        name = screen_name(o.get("display") or o["name"])
        for label, fumens in grouped(raw.get(page, []), ctxs.get(page)):
            links += 1
            good = []
            for f in fumens:
                try:
                    op.route_points(f)
                    good.append(f)
                except Exception:
                    pass
            if not good or not any(goes_on(begin, t.cells) for t in op.route_points(good)):
                continue
            have = routes.setdefault(name, [])
            taken = {r["name"] for r in have}
            shown, k = label, 2
            while shown in taken:
                shown, k = f"{label} {k}", k + 1
            have.append({"name": shown, "fumen": good if len(good) > 1 else good[0]})
            kept += 1
        # the wiki's 最小 patterns (the routes that start switched on): a route
        # holding one is marked, one under another heading (迷走砲's S①) is added
        for head, label, fumen in mins.get(page, []):
            have = routes.setdefault(name, [])
            hit = next((r for r in have if fumen == r["fumen"] or (isinstance(r["fumen"], list) and fumen in r["fumen"])),
                       None)
            if hit is not None:
                hit["min"] = True
                continue
            try:
                points = op.route_points(fumen)
            except Exception:
                continue
            if not any(goes_on(begin, t.cells) for t in points):
                continue
            base = label if not head or "派生" in head else f"{head} {label}"
            taken = {r["name"] for r in have}
            shown, k = base, 2
            while shown in taken:
                shown, k = f"{base} {k}", k + 1
            have.append({"name": shown, "fumen": fumen, "min": True})
            kept += 1
        if name in routes and not routes[name]:
            del routes[name]
    # for each shape of the opener, the first route that goes on from it
    import time
    for name, have in routes.items():
        points = [op.route_points(r["fumen"]) for r in have]
        for b in op.opener_starts(name):
            for r, pts in zip(have, points):
                if any(leads_on([b], t, time.monotonic() + 0.02) for t in pts):
                    r["start"] = True
                    break
    OUT.write_text(json.dumps({
        "_about": "Each opener's 派生 from テトリステンプレ整理Wiki (tools/opener_import/build_routes.py).",
        "source": "https://w.atwiki.jp/sasasa123/pages/1851.html",
        "routes": routes}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"openers with routes {len(routes)} / {len(openers)}, routes {kept} of {links} links, "
          f"{OUT.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
