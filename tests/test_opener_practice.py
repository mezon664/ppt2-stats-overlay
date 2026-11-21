"""開幕テンプレ練習 (scripts/opener_practice.py): the search for how to build
an opener with a given first bag, and following a match with it."""
import time

import opener_practice as op


def check_plan(shape, plan, queue):
    """The plan builds the shape with the queue's pieces in order (HOLD as
    the game has it), each piece a real tetromino of its kind."""
    assert set().union(*(set(map(tuple, st["cells"])) for st in plan)) == set(shape)
    i, hold = 0, None
    for st in plan:
        if st["hold"]:
            if hold is None:
                hold, i = queue[i], i + 1
                current = queue[i]
            else:
                current, hold = hold, queue[i]
        else:
            current = queue[i]
        i += 1
        assert st["piece"] == current
        cells = frozenset(map(tuple, st["cells"]))
        assert any(cells == frozenset((x + dx - s[0][0], y + dy - s[0][1]) for dx, dy in s)
                   for s in op.SHAPES[current] for x, y in cells)


def test_a_plan_builds_the_shape_with_the_bag():
    for name, bag in (("迷走砲", "TIOLJSZ"), ("迷走砲", "IOLJSZT"), ("石見の光", "LJSZIOT")):
        shape, plan = op.plan_for(name, bag)
        assert plan is not None, (name, bag)
        check_plan(shape, plan, bag)


def test_a_t_spin_opener_ends_with_its_t_spin():
    """開幕TSD's tag has its two rows full: they're the T-spin Double at the
    end, the T pointing down into its slot (not a T stood up at a wall)."""
    shape, plan = op.plan_for("石見の光", "LJSZIOT")
    last = plan[-1]
    assert last["piece"] == "T"
    cells = set(map(tuple, last["cells"]))
    rows = sorted({y for _, y in cells})
    assert len(rows) == 2 and sum(1 for _, y in cells if y == rows[1]) == 3   # flat side up top
    full = {y for _, y in shape if all((x, y) in shape for x in range(10))}
    assert full == set(rows)


def test_the_bag_from_six():
    assert op.bag_order("TIOLJS") == list("TIOLJSZ")
    assert op.bag_order("TIOLJT") is None          # a piece twice: not the first bag
    assert op.bag_order("TIO") is None


def test_the_rate_matches_the_wiki():
    """開幕TSD (Flat Top): the wiki gives 61.67% one side, 66% with mirrored;
    with the 8th piece in hand (HOLD keeps one of the first bag) the search
    builds about that share of all bags."""
    import itertools
    import random
    random.seed(1)
    bags = random.sample(list(itertools.permutations(op.PIECES)), 30)
    ok = sum(any(op.plan_for("開幕TSD", b + (e,))[1] is not None for e in op.PIECES) for b in bags)
    assert 15 <= ok <= 27   # 50-90% (60 bags: 68%)


def settle(practice, *args):
    """update() until the search for this board is in (it runs on a thread)."""
    out = practice.update(*args)
    for _ in range(300):
        time.sleep(0.05)
        out = practice.update(*args)
        if practice._job is None:
            return out
    return out


def deck(*names, mirror=True):
    return op.candidates({"mirror": mirror, "openers": [op.new_entry(n) for n in names]})


def follow(pr, cands, bag, key):
    """Places what the guide says, piece by piece; the last state."""
    out = settle(pr, cands, key, list(bag[:6]), True, [], None, 0)
    board, hold, n = set(), None, 0
    for _ in range(10):
        nxt = out.get("next")
        if not nxt:
            break
        if nxt["hold"]:
            hold = bag[n] if hold is None else hold
        board |= set(map(tuple, nxt["cells"]))
        n += 1
        out = settle(pr, cands, key, list(bag), True, sorted(board), hold, n)
    return out


def test_following_a_match():
    cands = deck("迷走砲")
    pr = op.Practice()
    assert pr.update([], 1, list("TIOLJSZ"), True, [], None) is None            # off
    out = settle(pr, cands, 1, list("TIOLJS"), True, [], None, 0)
    assert out["status"] == "ok" and out["name"] == "迷走砲" and out["next"]["piece"] in "TI"
    assert follow(pr, cands, "TIOLJSZ", 2)["status"] == "done"


def test_the_deck_picks_the_first_that_builds():
    """開幕TSD first: picked when this bag builds it, else the next."""
    cands = deck("開幕TSD", "迷走砲")
    tsd = [ts for o, f, ts in cands if o == "開幕TSD"][0]
    bags = op.all_bags()
    yes = next(b for b in bags if op.builds(tsd, b))
    no = next(b for b in bags if not op.builds(tsd, b) and not any(op.builds(tsd, b + (e,)) for e in op.PIECES)
              and op.builds([ts for o, f, ts in cands if o == "迷走砲"][0], b))
    pr = op.Practice()
    assert settle(pr, cands, 1, list(yes[:6]), True, [], None, 0)["name"] == "開幕TSD"
    assert settle(pr, cands, 2, list(no[:6]), True, [], None, 0)["name"] == "迷走砲"


def test_another_order_and_the_mirrored_shape_still_count():
    """Pieces down in another order than the guide's, or the mirrored shape:
    the rest is worked out again from the board."""
    bag = "ITOJZLS"
    cands = deck("石見の光")
    targets = cands[0][2]
    plans = [(t, op.solve(t.cells, bag)) for t in targets]
    target, plan = [(t, p) for t, p in plans if p][-1]    # the last one that builds: not what the guide picks first
    pr = op.Practice()
    settle(pr, cands, 1, list(bag[:6]), True, [], None, 0)
    board, hold = set(), None
    for k, st in enumerate(plan[:3]):
        if st["hold"] and hold is None:
            hold = bag[k]
        board |= set(map(tuple, st["cells"]))
    out = settle(pr, cands, 1, list(bag), True, sorted(board), hold, 3)
    # (another of the opener's shapes holding the same pieces may be the one followed)
    assert out["status"] == "ok" and board <= set(map(tuple, out["shape"]))


def test_off_the_deck():
    cands = deck("迷走砲")
    pr = op.Practice()
    settle(pr, cands, 2, list("TIOLJS"), True, [], None, 0)
    out = settle(pr, cands, 2, list("TIOLJSZ"), True, [(0, 5), (1, 5), (2, 5), (3, 5)], None, 1)
    assert out["status"] == "off"


def test_not_from_the_match_start_waits():
    """The queue wasn't read from the first piece: the bag's order isn't known."""
    pr = op.Practice()
    assert pr.update(deck("迷走砲"), 1, list("TIOLJSZ"), False, [], None)["status"] == "wait"


def test_the_setup_rate_matches_the_wiki():
    """響 (one page, first bag only): the wiki's 18.10% one side, 34.76%
    with mirrored — the same counting gives the same numbers."""
    for mirror, want in ((False, 0.1810), (True, 0.3476)):
        (o, f, ts), = deck("響", mirror=mirror)
        masks = [op.bag_mask(ts, b) for b in op.all_bags()]
        r = op.deck_rates([(o, f, masks)])
        assert abs(r["total"] - want) < 0.00005


def test_a_colored_fumen_keeps_its_pieces():
    """A form from a テト譜 with colors: those pieces there (gray: any)."""
    tag = op.opener_shapes("響")[0]
    gray = op.Target(tag)
    cut = op.tilings(tag)[0]
    colors = {c: p for p, cells in cut for c in cells}
    colored = op.Target(tag, colors)
    bags = op.all_bags()[::50]
    g = sum(op.builds([gray], b) for b in bags)
    c = sum(op.builds([colored], b) for b in bags)
    assert c <= g
    for b in bags:
        plan = op.solve(colored.cells, b, colors=colored.colors)
        if plan:
            assert all(colors[tuple(cell)] == st["piece"] for st in plan for cell in st["cells"])
    m = colored.mirrored()
    assert all(m.colors[(9 - x, y)] == {"L": "J", "J": "L", "S": "Z", "Z": "S"}.get(p, p) for (x, y), p in colors.items())


def test_a_deck_file_round_trip(tmp_path):
    d = {"mode": "deck", "mirror": False, "openers": [op.new_entry("迷走砲")]}
    op.save_deck(d, tmp_path / "deck.json")
    assert op.load_deck(tmp_path / "deck.json") == d
    assert op.load_deck(tmp_path / "missing.json") == op.default_deck()


def test_single_opener_uses_only_it_and_keeps_its_forms():
    a, b = "開幕TSD", "迷走砲"
    deck = {"mode": "single", "single": b, "mirror": True, "openers": [op.new_entry(a)]}
    assert {o for o, _, _ in op.candidates(deck)} == {b}
    entry = op.single_entry(deck, keep=True)
    entry["forms"][0]["on"] = False
    assert op.candidates(deck) == []                # (its one form switched off)
    assert op.single_entry(deck)["forms"][0]["on"] is False
    deck["mode"] = "deck"
    assert {o for o, _, _ in op.candidates(deck)} == {a}


def test_single_says_whether_it_builds():
    p = op.Practice()
    cands = op.candidates({"mode": "single", "single": "開幕TSD", "mirror": True, "openers": []})
    out = p.update(cands, 1, [], True, [], None, 0)
    assert out["status"] == "wait" and out["single"] is True and out["name"] == "開幕TSD"


IMPERIAL = ("v115@Ahi0DeglBeBtg0Q4CeglCeBtR4RphlAezhQ4RpJeFKJvhAAAAUhilDeg0BeBtglwhMeAAAxgR4GeR4AtHeBtilzhAeAtg0gl"
            "RpFeg0AeRpEeh0JetsBvhAAAA")


def test_a_route_reads_as_boards_in_order():
    points = op.route_points(IMPERIAL)
    assert [len(t.cells) for t in points] == [28, 8, 8, 36, 16]
    assert points[0].colors[(3, 0)] == "I"


def test_plan_towards_goes_as_far_as_the_pieces_seen():
    import itertools
    points = op.route_points(IMPERIAL)
    base, goal = points[1].cells, points[3]
    pieces = sorted({goal.colors[c] for c in goal.cells - base})
    assert len(pieces) == 7
    order = next(q for q in itertools.permutations(pieces) if q[-1] == "T"
                 and (op.plan_towards(goal.cells, q, base, 0, None, goal.colors) or (0, False))[1])
    steps, whole = op.plan_towards(goal.cells, order, base, 0, None, goal.colors)
    assert whole and len(steps) == 7 and steps[-1]["piece"] == "T"
    part, whole = op.plan_towards(goal.cells, order[:2], base, 0, None, goal.colors)
    assert not whole and len(part) >= 1
    assert op.plan_towards(goal.cells, ("O", "O"), frozenset(goal.cells - {(7, 0)}), 0, None, goal.colors) is None


def test_entry_routes_keep_your_order_and_ticks(monkeypatch):
    monkeypatch.setattr(op, "_WIKI_ROUTES", {"X": [{"name": "a", "fumen": "f"}, {"name": "b", "fumen": "g"},
                                                  {"name": "c", "fumen": "h"}]})
    e = {"name": "X", "routes": [{"name": "b", "on": False}, {"name": "gone", "on": True}]}
    assert [(r["name"], r["on"]) for r in op.entry_routes(e)] == [("b", False), ("a", True), ("c", True)]


def _settle(p, *args, **kw):
    import time
    out = p.update(*args, **kw)
    for _ in range(400):
        if p._job is None:
            out2 = p.update(*args, **kw)
            if p._job is None:
                return out2
        time.sleep(0.005)
        out = p.update(*args, **kw)
    return out


def test_the_guide_goes_on_along_a_route_after_the_opener():
    import itertools
    points = op.route_points(IMPERIAL)
    shape, after, goal = points[0], points[1], points[3]
    t_cells = frozenset(c for c, v in shape.colors.items() if v == "T")
    setup = shape.cells - t_cells
    second = next(q for q in itertools.permutations(sorted({goal.colors[c] for c in goal.cells - after.cells}))
                  if q[-1] == "T" and (op.plan_towards(goal.cells, q, after.cells, 0, None, goal.colors) or (0, 0))[1])
    first = next(q for q in itertools.permutations("IOSZJL") if op.solve(setup, q) is not None)
    seen = list(first) + ["T"] + list(second)
    cands = [("X", "Wiki", [op.Target(setup)])]
    routes = {"X": [op.Route("Imperial", points)]}
    p = op.Practice()
    _settle(p, cands, 1, seen, True, sorted(setup), None, 6, routes)    # the opener stands
    out = _settle(p, cands, 1, seen, True, sorted(setup), None, 6, routes)
    assert out["route"] is True and out["status"] == "ok" and out["next"]["piece"] == "T"
    assert out["form"] == "Imperial"
    out = _settle(p, cands, 1, seen, True, sorted(after.cells), None, 7, routes)    # its T-spin cleared
    assert out["status"] == "ok" and out["next"]["piece"] in second
    assert frozenset(map(tuple, out["next"]["cells"])) <= goal.cells - after.cells
    assert _settle(p, cands, 1, seen, False, sorted(after.cells), None, 7, routes)["status"] == "lost"


def test_a_painted_form():
    # bottom row first: an O and an I, in their colors
    rows = ["OOIIII....", "OO........"]
    assert op.paint_problem(rows) is None
    assert op.paint_cells(rows)[(2, 0)] == "I"
    assert op.paint_rows(op.paint_cells(rows)) == rows
    form = {"name": "mine", "paint": rows, "on": True}
    plain, both = op.form_targets("x", form, False), op.form_targets("x", form, True)
    assert len(plain) == 1 and plain[0].colors[(0, 0)] == "O" and len(both) == 2
    assert both[1].colors[(9, 0)] == "O"
    assert op.solve_from(plain[0].cells, tuple("OI"), [], 0, None, plain[0].colors) is not None
    assert op.solve_from(plain[0].cells, tuple("IO"), [], 0, None, plain[0].colors) is not None


def test_a_painting_that_cant_be_a_form():
    assert op.paint_problem([]) == "empty"
    assert op.paint_problem(["XXX......."]) == "count"
    assert op.paint_problem(["XXXXXXXX..", "XXXXXXXX..", "XXXXXXXX..", "XXXXXXXX..", "XXXXXXXX.."]) == "big"
    assert op.paint_problem(["IIOO......"]) == "shape"          # colors that make no piece
    assert op.paint_problem(["XXXXXXXXXX", "XX........"]) == "shape"   # a full row with no T-spin


def test_on_a_route_with_no_way_on_isnt_called_off_it():
    goal = frozenset((x, y) for x in range(10) for y in range(2))
    p = op.Practice()
    p.routes, p.opener, p.pick = {"X": [op.Route("r", [op.Target(goal)])]}, "X", ("X", "r")
    on_it = goal - {(0, 0), (1, 0), (0, 1), (1, 1)}
    assert p._route_plan(on_it, tuple("ZZ"), 0, None)[0] == "stuck"
    assert p._route_plan(frozenset({(0, 5)}), tuple("ZZ"), 0, None)[0] == "end"


def test_a_perfect_clear_page_clears_rows_on_the_way():
    # four rows, the two right columns open: the first O clears two rows
    page = frozenset((x, y) for x in range(10) for y in range(4))
    board = frozenset(c for c in page if c[0] < 8)
    steps, whole = op.plan_towards(page, tuple("OO"), board, 0, None)
    assert whole and [st["piece"] for st in steps] == ["O", "O"]
    assert sorted(steps[0]["cells"]) == [(8, 0), (8, 1), (9, 0), (9, 1)]
    assert sorted(steps[1]["cells"]) == [(8, 0), (8, 1), (9, 0), (9, 1)]    # (what was above came down)
    # after the rows went, the board sits on the page's upper rows
    after = frozenset((x, y) for x in range(8) for y in range(2))
    assert (2, 3) in op.page_rows(page, after)
    assert op.plan_towards(page, ("O",), after, 0, None, None, (2, 3))[1] is True


def test_the_wiki_main_shape_and_its_mirror_come_first():
    shapes = op.opener_shapes("迷走砲")
    ts = op.form_targets("迷走砲", {"name": "Wiki", "source": op.WIKI_FORM, "on": True}, True)
    first = op.setup_targets(shapes[0])[0]
    assert ts[0].cells == first and ts[1].cells == op.mirror_cells(first)


def test_meisou_routes_are_the_wiki_groups():
    names = [r["name"] for r in op.wiki_routes("迷走砲")]
    assert "高火力パフェ型" in names and "千鳥格子型" in names
    assert not any(n.startswith("3巡目が組める確率") or n == "3巡目テト譜" for n in names)
    route = next(r for r in op.wiki_routes("迷走砲") if r["name"] == "高火力パフェ型")
    assert isinstance(route["fumen"], list) and len(op.route_points(route["fumen"])) > 5
