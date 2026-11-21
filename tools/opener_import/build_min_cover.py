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
MAX_BOARDS = 120    # next-bag boards looked at per opener
OPENER_S = 90       # time for one opener


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


def job(name):
    t0 = time.monotonic()
    shapes = op.opener_shapes(name)
    routes = op.wiki_routes(name)
    if not shapes:
        return name, None
    shape = shapes[0]
    full = any(all((x, y) in shape for x in range(op.COLS)) for _, y in shape)
    base = op.after_clear(shape) if full else frozenset(shape)
    pages, labels = {}, {}
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
    for r in routes:
        if not r.get("fumen"):
            continue
        for t in op.route_points(r["fumen"]):
            pages.setdefault(t.key(), t)
            labels.setdefault(t.key(), r["name"][:24])
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
