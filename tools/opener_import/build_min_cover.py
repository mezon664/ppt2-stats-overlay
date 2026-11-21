"""Builds assets/opener_min_cover.json: each opener's 最少パターン.

The fewest of the wiki's next-bag boards that, between them, can be built for
as many of the next bag's 5040 orders as those boards can (100% where they
reach it), with HOLD and each piece getting to its place the game's way. Of
sets as small, the one with the wiki's earlier boards: those of the page's
own main テト譜 first (wiki_routes_main.json), then its 派生 in order.
Worked out from the opener's main shape (after its T-spin); a shape with a
piece left in HOLD is tried with each piece it can be.

    python tools/opener_import/build_min_cover.py
"""
import json
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from fumen import decode  # noqa: E402
from opener_detect import screen_name  # noqa: E402
import opener_practice as op  # noqa: E402

OUT = ROOT / "assets" / "opener_min_cover.json"
MAIN = Path(__file__).with_name("wiki_routes_main.json")    # {page: the page's first テト譜}
# the wiki's Standard / Advance / Extra where they're only an image, read off
# it by color: {page: {"S①": rows bottom first}}. A board is used only if it
# makes whole pieces and goes on from the opener (迷走砲's S①〜S③ come to the
# setup rates the wiki gives, 66.67 / 66.67 / 50.00%)
IMAGES = Path(__file__).with_name("wiki_groups_images.json")
MAX_BOARDS = 120    # next-bag boards looked at per opener
OPENER_S = 90       # time for one opener
# a page of the main テト譜 labelled as one of the wiki's groups
GROUP = re.compile(r"^\s*#?(S|A|EX)\s*([①-⑳])")
GROUP_NAME = {"S": "Standard", "A": "Advance", "EX": "Extra"}


def op_name(o):
    return screen_name(o.get("display") or o["name"])


def holds_of(shape):
    """What can be in HOLD after this shape: None for a whole bag on the board."""
    if len(shape) >= 28:
        return [None]
    left = set()
    for cut in op.tilings(frozenset(shape)):
        names = [p for p, _ in cut]
        if len(set(names)) == len(names):
            left |= set(op.PIECES) - set(names)
    return sorted(left) or [None]


def wiki_groups(base, labelled, holds, starts=()):
    """The wiki's Standard / Advance / Extra boards one bag on from `base`:
    all of Standard on, then the fewest others that cover more."""
    best = None
    for hold in holds:
        want = 28 + (4 if hold else 0)
        items = []
        for label, t in labelled:
            for b in [base] + [s for s in starts if s != base]:     # (the opener's other shapes too)
                if b < t.cells and len(t.cells) - len(b) in (want, want - 4, want - 8):
                    m = op.page_orders(b, t, hold, spare=True)
                    if m:
                        items.append((label, t, m))
                        break
        if not items:
            continue
        standard = 0
        for label, _, m in items:
            if label.startswith("S"):
                standard |= m
        more = {k: m & ~standard for k, (label, _, m) in enumerate(items) if not label.startswith("S") and m & ~standard}
        extra = set(op.smallest_cover(more)[0]) if more else set()
        covered = standard
        for k in extra:
            covered |= items[k][2]
        got = bin(covered).count("1")
        if best is None or got > best[0]:
            best = (got, items, extra, hold)
    if best is None:
        return None
    got, items, extra, hold = best
    groups, used = [], {}
    for k, (label, t, _) in enumerate(items):
        used[label] = used.get(label, 0) + 1
        kind = re.match(r"S|A|EX", label).group(0)
        shown = f"{GROUP_NAME[kind]} {label}" + (f" ({used[label]})" if used[label] > 1 else "")
        groups.append({"name": shown, "rows": op.paint_rows({c: (t.colors or {}).get(c, "X") for c in t.cells}),
                       "on": label.startswith("S") or k in extra})
    return {"rate": round(got / len(op.all_bags()), 4), "hold": hold, "groups": groups}


def job(name):
    t0 = time.monotonic()
    shapes = op.opener_shapes(name)
    routes = op.wiki_routes(name)
    if not shapes:
        return name, None
    shape = shapes[0]
    full = any(all((x, y) in shape for x in range(op.COLS)) for _, y in shape)
    base = op.after_clear(shape) if full else frozenset(shape)
    pages, labels, labelled = {}, {}, []
    data = json.loads(op.OPENERS_PATH.read_text(encoding="utf-8"))["openers"]
    main = json.loads(MAIN.read_text(encoding="utf-8"))
    for o in data:
        if op_name(o) != name:
            continue
        fumen = main.get(re.search(r"pages/(\d+)", o["page"]).group(1))
        if not fumen:
            continue
        try:
            main_pages = decode(fumen)
        except Exception:       # (a few of the wiki's テト譜 don't decode)
            continue
        for page in main_pages:
            for t in op.route_points_of_page(page):
                pages.setdefault(t.key(), t)
                if page.comment:
                    labels.setdefault(t.key(), page.comment.strip()[:24])
                    tag = GROUP.match(page.comment)
                    if tag and all(t.key() != x.key() for _, x in labelled):
                        labelled.append((tag.group(1) + tag.group(2), t))
    for r in routes:
        if not r.get("fumen"):
            continue
        for t in op.route_points(r["fumen"]):
            pages.setdefault(t.key(), t)
            labels.setdefault(t.key(), r["name"][:24])
    if not labelled:
        images = json.loads(IMAGES.read_text(encoding="utf-8"))
        for o in data:
            if op_name(o) == name:
                for label, rows in images.get(re.search(r"pages/(\d+)", o["page"]).group(1), {}).items():
                    labelled.append((label, op.route_targets({"paint": rows})[0]))
    if labelled:
        got = wiki_groups(base, labelled, [None] if full else holds_of(shape), op.opener_starts(name))
        if got:
            return name, got
    best = None
    for hold in ([None] if full else holds_of(shape)):
        want = 28 + (4 if hold else 0)
        # (want - 4: the setup, with the bag's T kept for its T-spin)
        boards = [t for t in pages.values() if base < t.cells and len(t.cells) - len(base) in (want, want - 4)][:MAX_BOARDS]
        masks = {}
        for k, t in enumerate(boards):
            if time.monotonic() - t0 > OPENER_S:
                break
            m = op.page_orders(base, t, hold)
            if m:
                masks[k] = m
        if not masks:
            continue
        picked, covered = op.smallest_cover(masks)
        if best is None or (covered, -len(picked)) > (best[0], -len(best[1])):
            best = (covered, [boards[k] for k in sorted(picked)], hold)
    if best is None:
        return name, None
    rows = [op.paint_rows({c: (t.colors or {}).get(c, "X") for c in t.cells}) for t in best[1]]
    return name, {"rate": round(best[0] / len(op.all_bags()), 4), "hold": best[2], "boards": rows,
                  "names": [labels.get(t.key(), "") for t in best[1]]}


def main():
    names = sorted({op_name(o) for o in json.loads(op.OPENERS_PATH.read_text(encoding="utf-8"))["openers"]})
    out, done, t0 = {}, 0, time.monotonic()
    with ProcessPoolExecutor() as pool:
        for f in as_completed([pool.submit(job, n) for n in names]):
            done += 1
            try:
                name, got = f.result()
            except Exception as e:
                print("failed:", repr(e)[:120], flush=True)
                continue
            if got:
                out[name] = got
            if done % 50 == 0:
                print(done, "/", len(names), round(time.monotonic() - t0), "s", flush=True)
    OUT.write_text(json.dumps({
        "_about": "The fewest wiki next-bag boards covering the next bag's orders (tools/opener_import/build_min_cover.py).",
        "covers": dict(sorted(out.items()))}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    full = sum(v["rate"] >= 1 for v in out.values())
    print(f"openers {len(out)} of {len(names)}, reaching 100%: {full}, {OUT.stat().st_size / 1e3:.0f} KB,",
          round(time.monotonic() - t0), "s")


if __name__ == "__main__":
    main()
