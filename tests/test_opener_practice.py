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
    monkeypatch.setattr(op, "_WIKI_ROUTES", {"X": [{"name": "a", "fumen": "f", "min": True}, {"name": "b", "fumen": "g"},
                                                  {"name": "c", "fumen": "h", "min": True}]})
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


def test_at_first_only_the_minimal_patterns_are_on(monkeypatch):
    monkeypatch.setattr(op, "_WIKI_ROUTES", {
        "X": [{"name": "a", "fumen": "f"}, {"name": "m", "fumen": "g", "min": True}],
        "Y": [{"name": "a", "fumen": "f"}, {"name": "b", "fumen": "g"}]})
    assert [(r["name"], r["on"]) for r in op.entry_routes({"name": "X"})] == [("a", True), ("m", True)]
    assert [(r["name"], r["on"]) for r in op.entry_routes({"name": "Y"})] == [("a", True), ("b", False)]


def test_your_own_route_comes_first_and_is_guided(monkeypatch):
    monkeypatch.setattr(op, "_WIKI_ROUTES", {"X": [{"name": "a", "fumen": IMPERIAL, "min": True}]})
    rows = ["OOIIII....", "OO........"]
    e = {"name": "X", "forms": [], "own_routes": [{"name": "mine", "paint": rows}]}
    routes = op.entry_routes(e)
    assert routes[0]["name"] == "mine" and routes[0]["own"] and routes[0]["on"]
    got = op.deck_routes({"mode": "deck", "mirror": False, "openers": [e]})["X"]
    assert got[0].name == "mine" and got[0].points[0].colors[(0, 0)] == "O"


def test_a_form_saved_before_moves_to_the_routes(tmp_path):
    path = tmp_path / "deck.json"
    entry = op.new_entry("迷走砲")
    entry["forms"].append({"name": "理想形", "fumen": IMPERIAL, "on": True})
    op.save_deck({"mode": "deck", "mirror": True, "openers": [entry]}, path)
    got = op.load_deck(path)["openers"][0]
    assert [f["name"] for f in got["forms"]] == ["Wiki"]
    assert got["own_routes"] == [{"name": "理想形", "fumen": IMPERIAL}]


def test_a_route_has_to_go_on_from_the_opener():
    start = op.opener_starts("開幕TSD")[0]
    good = op.Target(set(start) | {(0, 15), (1, 15)})
    assert op.route_problem("開幕TSD", [good]) is None
    assert op.route_problem("開幕TSD", [op.Target({(5, 12), (6, 12)})]) == "far"
    assert op.route_problem("開幕TSD", []) == "empty"
    assert op.route_problem("開幕TSD", [op.Target({(0, 0)})]) == "count"
    assert op.route_problem("開幕TSD", [op.Target(start, {next(iter(start)): "T"})]) == "shape"


def test_the_opener_standing_with_no_route_on_isnt_off_the_route():
    far = op.Target({(x, 9) for x in range(4)})
    setup = frozenset((x, 0) for x in range(4))
    p = op.Practice()
    p.routes, p.opener, p.pick, p.base = {"X": [op.Route("r", [far])]}, "X", ("X", "r"), setup
    assert p._route_plan(setup, tuple("TIO"), 1, None)[0] == "done"
    assert p._route_plan(frozenset((x, 1) for x in range(4)), tuple("TIO"), 1, None)[0] == "end"


def test_the_smallest_cover_is_the_fewest_boards():
    # the biggest board tempts a greedy pick into three; two do it
    masks = {0: 0b0111110, 1: 0b0001111, 2: 0b1110000}
    keys, covered = op.smallest_cover(masks)
    assert sorted(keys) == [1, 2] and covered == 7


def test_of_covers_as_small_the_wikis_earlier_boards_win():
    masks = {0: 0b0011, 1: 0b1100, 2: 0b0110, 3: 0b1001}
    assert op.smallest_cover(masks)[0] == [0, 1]
    assert op.smallest_cover({5: 0b11, 2: 0b11})[0] == [2]


def test_page_orders_agree_with_the_search():
    import random
    points = op.route_points(IMPERIAL)
    base, goal = points[1].cells, points[3]
    bits = op.page_orders(base, goal)
    assert bits
    random.seed(4)
    bags = op.all_bags()
    for b in random.sample(range(len(bags)), 40):
        got = op.plan_towards(goal.cells, tuple(bags[b]) + ("I",), base, 0, None, goal.colors)
        assert bool(bits >> b & 1) == bool(got and got[1])


def test_the_cover_is_what_starts_on(monkeypatch):
    monkeypatch.setattr(op, "_WIKI_ROUTES", {"X": [{"name": "a", "fumen": "f", "min": True, "start": True}]})
    monkeypatch.setattr(op, "_MIN_COVERS", {"X": {"rate": 1.0, "hold": None, "boards": [["OO........"], ["II........"]]}})
    got = op.entry_routes({"name": "X"})
    assert [r["on"] for r in got] == [True, True, False] and got[0]["name"].startswith("最少パターン 1/2")


def test_a_next_bag_board_may_keep_its_t():
    points = op.route_points(IMPERIAL)
    base, goal = points[1].cells, points[3]
    t_cells = frozenset(c for c in goal.cells - base if goal.colors[c] == "T")
    setup = op.Target(goal.cells - t_cells, {c: v for c, v in goal.colors.items() if c not in t_cells})
    with_t, without = op.page_orders(base, goal), op.page_orders(base, setup)
    assert without and with_t | without == without     # (whatever builds it with the T builds it before the T)


def test_boards_drawn_one_above_the_other_are_separate():
    class Page:
        def board_with_piece(self):
            rows = [[0] * 10 for _ in range(23)]
            rows[0][:4] = [1, 1, 1, 1]      # an I on the floor
            rows[3][5:7] = [3, 3]           # an empty row or two, then an O
            rows[4][5:7] = [3, 3]
            return rows
    top, bottom = op.route_points_of_page(Page())
    assert top.cells == frozenset({(5, 0), (6, 0), (5, 1), (6, 1)}) and top.colors[(5, 0)] == "O"
    assert bottom.cells == frozenset((x, 0) for x in range(4))


def test_bt_cannon_has_its_compromise_form():
    route = next(r for r in op.wiki_routes("BT砲") if r["name"] == "2巡目妥協")
    assert all(max(y for _, y in t.cells) < 12 for t in op.route_points(route["fumen"]))
    assert len(op.route_points(route["fumen"])) > 3


def _wait_for(p, *args):
    import time
    out = p.update(*args)
    for _ in range(600):
        if p._job is None and p._asked is not None:
            return p.update(*args)
        time.sleep(0.005)
        out = p.update(*args)
    return out


def test_the_next_piece_showing_isnt_the_last_one_going_in():
    import itertools
    cands = op.candidates({"mode": "single", "single": "開幕TSD", "mirror": False, "openers": []})
    target, order = next((t, q) for t in cands[0][2] for q in itertools.islice(itertools.permutations(op.PIECES), 400)
                         if op.solve(t.cells, q) is not None)
    cands = [(cands[0][0], cands[0][1], [target])]
    plan = op.solve(target.cells, order)
    before = frozenset(c for st in plan[:-1] for c in map(tuple, st["cells"]))
    p = op.Practice()
    assert _wait_for(p, cands, 1, list(order), True, sorted(before), None, len(plan) - 1)["status"] == "ok"
    above = before | {(3, 19), (4, 19), (5, 19), (6, 19)}
    assert p.update(cands, 1, list(order), True, sorted(above), None, len(plan) - 1)["status"] == "ok"
    elsewhere = before | {(0, 10), (1, 10), (2, 10), (3, 10)}
    assert p.update(cands, 1, list(order), True, sorted(elsewhere), None, len(plan))["status"] != "done"


def test_the_last_piece_clearing_rows_is_done():
    shape = frozenset((x, 0) for x in range(10)) | {(0, 1), (1, 1)}
    p = op.Practice()
    p.target = op.Target(shape)
    assert p._last_cleared(frozenset({(0, 0), (1, 0)}), 3)
    assert not p._last_cleared(frozenset({(0, 0), (1, 0)}), 2)
    assert not p._last_cleared(shape, 3)


def test_a_shape_on_the_way_to_a_bigger_one_isnt_the_end():
    small = frozenset({(0, 0), (1, 0), (2, 0), (3, 0)})
    big = small | {(4, 0), (5, 0), (4, 1), (5, 1)}
    p = op.Practice()
    p.cands, p.target = [("X", "Wiki", [op.Target(small), op.Target(big)])], None
    got = p._plan(small, tuple("IOTSZJL"), 1, None)
    assert got[0] == "ok" and got[2].cells == big and got[3][0]["piece"] == "O"
    assert p._plan(small, tuple("IOTSZJL"), 1, "O")[0] == "done"       # (its piece in HOLD: that's the shape)


def _guide():
    p = op.Practice()
    p.cands, p.status, p.on_route = [], "ok", False
    p.plan = [{"piece": "O", "cells": [(0, 0), (1, 0), (0, 1), (1, 1)], "hold": False},
              {"piece": "I", "cells": [(2, 0), (3, 0), (4, 0), (5, 0)], "hold": False}]
    return p


def test_the_guide_moves_on_the_moment_the_piece_is_there():
    p = _guide()
    p._advance(frozenset({(0, 1), (1, 1), (0, 2), (1, 2)}))     # falling, one row up
    assert p.plan[0]["piece"] == "O"
    p._advance(frozenset({(0, 0), (1, 0), (0, 1), (1, 1)}))
    assert p.plan[0]["piece"] == "I" and len(p.plan) == 1


def test_a_piece_only_passing_through_brings_the_step_back():
    p = _guide()
    p._advance(frozenset({(0, 0), (1, 0), (0, 1), (1, 1)}))
    assert p.plan[0]["piece"] == "I"
    p._advance(frozenset({(3, 18), (4, 18), (3, 19), (4, 19)}))
    assert p.plan[0]["piece"] == "O" and len(p.plan) == 2


def test_a_step_that_clears_rows_waits_for_the_new_plan():
    p = _guide()
    full = frozenset((x, 0) for x in range(10)) | {(0, 1), (1, 1)}
    p._advance(full)
    assert p.plan[0]["piece"] == "O"


def test_the_wikis_groups_are_all_that_is_listed(monkeypatch):
    monkeypatch.setattr(op, "_WIKI_ROUTES", {"X": [{"name": "a", "fumen": "f", "start": True}]})
    monkeypatch.setattr(op, "_MIN_COVERS", {"X": {"rate": 1.0, "hold": None, "groups": [
        {"name": "Standard S①", "rows": ["OO........"], "on": True},
        {"name": "Advance A①", "rows": ["II........"], "on": False}]}})
    got = op.entry_routes({"name": "X"})
    assert [(r["name"], r["on"]) for r in got] == [("Standard S①", True), ("Advance A①", False)]


def test_hachimitsu_has_its_standard_on():
    got = op.entry_routes({"name": "はちみつ砲"})
    assert [r["name"] for r in got if r["on"]] == ["Standard S①", "Standard S②", "Standard S③"]
    assert all(r["name"].split()[0] in ("Standard", "Advance", "Extra") for r in got)


def test_meisou_standard_is_what_the_wiki_says():
    got = {r["name"]: r for r in op.entry_routes({"name": "迷走砲"})}
    assert [n for n, r in got.items() if r["on"]][:3] == ["Standard S①", "Standard S②", "Standard S③"]
    base = op.opener_shapes("迷走砲")[0]
    rates = [round(bin(op.page_orders(base, op.route_targets(got[f"Standard S{k}"])[0], "S")).count("1") / 50.40, 2)
             for k in "①②③"]
    assert rates == [66.67, 66.67, 50.0]     # the wiki's own setup rates
