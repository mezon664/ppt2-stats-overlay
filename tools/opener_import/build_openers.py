"""Builds assets/openers.json from the wiki data in wiki_tags.json.

wiki_tags.json: every page listed on テトリステンプレ整理Wiki's テンプレ一覧
(https://w.atwiki.jp/sasasa123/pages/1851.html) with the shape tags (テト譜) of
that page — collected 2026-10-31 through the browser, see
docs/opener_import_progress.md. Each tag is the template's first-bag shape.

Kept: every page with at least one shape that decodes. Skipped: pages titled
名無し… (no name to show). A shorter on-screen name ("display") given by hand
in the old openers.json is kept for the same page.

English names ("name_en", shown when the overlay's language is English; the
user's rule: Hard Drop's name, else the Japanese one): the English name the
wiki page gives after its Japanese one ("迷走砲 / Stray Cannon", from
wiki_heads.json) spelled as on Hard Drop when Hard Drop has that page; else a
Hard Drop page about that one opener whose text names it in Japanese
(harddrop.json, pages naming at most 4 Japanese words — longer ones are lists
of many openers); else the wiki's English name; else none (Japanese shown).

    python tools/opener_import/build_openers.py
"""
import json
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from fumen import decode  # noqa: E402

WIKI = Path(__file__).with_name("wiki_tags.json")
HEADS = Path(__file__).with_name("wiki_heads.json")
HARDDROP = Path(__file__).with_name("harddrop.json")
OUT = ROOT / "assets" / "openers.json"
PAGE_URL = "https://w.atwiki.jp/sasasa123/pages/{}.html"


def clean(fumen):
    """Some tags came URL-encoded twice (%2F for /)."""
    for _ in range(3):
        fumen = urllib.parse.unquote(fumen)
    return fumen.strip()


def decodes(fumen):
    try:
        decode(fumen)[0].board_with_piece()
        return True
    except Exception:
        return False


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def wiki_english(title, head):
    """The English name a wiki page gives after its Japanese one, or None."""
    if not head.startswith(title[:4]):
        return None
    m = re.match(r"(.{1,60}?) / (.+?)(?: 詳細テト譜| テト譜| このテンプレ|  |$)", head)
    if not m:
        return None
    en = m.group(2).split(" / ")[0].strip()
    return en if en and sum(c.isascii() for c in en) >= 0.8 * len(en) else None


def english_names(pages):
    heads = json.loads(HEADS.read_text(encoding="utf-8"))["heads"] if HEADS.exists() else {}
    hd = json.loads(HARDDROP.read_text(encoding="utf-8")) if HARDDROP.exists() else {"titles": [], "ja": {}}
    hd_titles = {_norm(t): t for t in hd["titles"]}
    ja_pages = {}
    for t, words in hd["ja"].items():
        if len(words) <= 4:
            for w in words:
                ja_pages.setdefault(w, set()).add(t)
    out = {}
    for pid, p in pages.items():
        title = p["title"].strip()
        en = wiki_english(title, heads.get(pid, ""))
        if en and _norm(en) in hd_titles:
            out[pid] = hd_titles[_norm(en)]
        elif len(ja_pages.get(title, ())) == 1:
            out[pid] = next(iter(ja_pages[title]))
        elif en:
            out[pid] = en
    return out


def main():
    pages = json.loads(WIKI.read_text(encoding="utf-8"))["pages"]
    english = english_names(pages)
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"openers": []}
    display = {op["page"]: op["display"] for op in old["openers"] if op.get("display") and op.get("page")}
    openers, skipped, dropped = [], 0, 0
    for pid, p in pages.items():
        title = p["title"].strip()
        if not title or title.startswith("名無し"):
            skipped += 1
            continue
        shapes = []
        for f in p["shapes"]:
            f = clean(f)
            if f not in shapes and decodes(f):
                shapes.append(f)
            elif not decodes(f):
                dropped += 1
        if not shapes:
            skipped += 1
            continue
        url = PAGE_URL.format(pid)
        op = {"name": title, "page": url, "shapes": shapes}
        if url in display:
            op["display"] = display[url]
        if pid in english:
            op["name_en"] = english[pid]
        openers.append(op)
    data = {
        "_about": ("First-bag shapes of openers: the shape tags (テト譜/fumen) of every page on "
                   "テトリステンプレ整理Wiki's テンプレ一覧. Only the board shapes are taken; names and shapes "
                   "belong to the wiki and the openers' authors. Rebuilt by tools/opener_import/build_openers.py. "
                   '"display" is a shorter name shown on screen.'),
        "source": "テトリステンプレ整理Wiki https://w.atwiki.jp/sasasa123/ (テンプレ一覧 pages/1851.html, 2026-10-31)",
        "openers": openers,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(openers)} openers ({sum('name_en' in o for o in openers)} with an English name), "
          f"{sum(len(o['shapes']) for o in openers)} shapes "
          f"(skipped {skipped} pages, dropped {dropped} shapes that don't decode) -> {OUT}")


if __name__ == "__main__":
    main()
