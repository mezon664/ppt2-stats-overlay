"""縛りプレイ: comments flowing as you play (scripts/comments.py)."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import comments
from config_store import display_settings


def state(log_left=(), log_right=(), **extra):
    return {"match_screen": True, "match_start_t": 5.0, "you_side": "left",
            "left": {"event_log": list(log_left), "b2b": 0}, "right": {"event_log": list(log_right)}, **extra}


def ev(t, label, **kw):
    return {"t": t, "label": label, "lines": 4, "btb": False, "ren_count": 0, "perfect_clear": False, **kw}


def test_comments_follow_the_play():
    d = display_settings({"display": {"challenge_comments": "normal"}})
    cs = comments.CommentStream(random.Random(1))
    kinds = lambda out: [c["kind"] for c in out["items"] if c["kind"] != "ambient"]
    out = cs.update(d, state(), 0.0)
    assert kinds(out) == ["start"] * comments.COUNT["start"]                      # the match starts
    out = cs.update(d, state([ev(6.0, "TETRIS")]), 1.0)
    assert kinds(out).count("tetris") == comments.COUNT["tetris"]                 # your TETRIS
    out = cs.update(d, state([ev(6.0, "TETRIS")], [ev(7.0, "T-SPIN Double")]), 2.0)
    assert kinds(out).count("rival") == comments.COUNT["rival"]                   # theirs: a few
    out = cs.update(d, state([ev(6.0, "TETRIS")], frozen=True, winner="left"), 3.0)
    assert "win" in kinds(out)                                                    # the win
    # through the set they keep coming now and then, and on a while after it
    t = 3.0
    for _ in range(40):
        t += 0.5
        out = cs.update(d, state(frozen=True), t)
    assert any(c["kind"] == "ambient" for c in out["items"])
    out = cs.update(d, {"match_screen": False}, t + 1)
    assert "set_end" in kinds(out)                                                # the set is over
    out = cs.update(d, {"match_screen": False}, t + comments.SET_END_S + comments.FLOW_S + 2)
    assert out["items"] == []                                                     # and then they stop
    assert cs.update(display_settings({}), state(), 20.0) is None                           # off
    texts = [c["text"] for c in comments.CommentStream(random.Random(2)).update(
        display_settings({"display": {"challenge_comments": "many", "language": "en"}}), state(), 0.0)["items"]]
    assert texts and all(t in comments._pool("start", "en") for t in texts)                   # English


def test_tspin_kinds_openers_and_numbers():
    d = display_settings({"display": {"challenge_comments": "normal"}})
    cs = comments.CommentStream(random.Random(4))
    kinds = lambda out: [c["kind"] for c in out["items"] if c["kind"] != "ambient"]
    cs.update(d, state(), 0.0)
    for k, (label, kind) in enumerate((("T-SPIN Double", "tsd"), ("T-SPIN Triple", "tst"),
                                       ("T-SPIN Mini Double", "tsmd"), ("T-SPIN Mini Single", "tsm"))):
        out = cs.update(d, state([ev(10.0 + k, label)]), 1.0 + k)
        assert kind in kinds(out), label
    # an opener, yours then theirs (by name)
    st = state()
    st["left"]["opener"] = "TKI"
    out = cs.update(d, st, 20.0)
    assert any(c["kind"] == "opener" and ("TKI" in c["text"] or "{" not in c["text"]) for c in out["items"])
    # APM well over your usual, PPS fast, and the match time
    st = {**state(), "match_elapsed_s": 60.5}
    st["left"].update({"apm": {"apm": 90.0}, "pps": 2.4})
    for t in (30.0, 33.5):
        out = cs.update(d, st, t, usual={"matches": 10, "apm": 50.0, "pps": 1.5})
    got = kinds(out)
    assert "apm_high" in got and "pps_fast" in got and "time" in got
    assert any(c["text"].startswith("APM90") or "{n}" not in c["text"] for c in out["items"] if c["kind"] == "apm_high")


def test_the_catalog_lists_every_kind():
    text = comments.catalog()
    for when, ja, en in comments.POOL.values():
        assert when in text and ja[0] in text


def test_garbage_pinch_comeback_and_quiet():
    d = display_settings({"display": {"challenge_comments": "normal"}})
    cs = comments.CommentStream(random.Random(5))
    kinds = lambda out: {c["kind"] for c in out["items"]}
    cs.update(d, state(), 0.0, board={"garbage": 0, "height": 3})
    out = cs.update(d, state(), 0.5, board={"garbage": 5, "height": 8})
    assert "garbage_big" in kinds(out)                                   # 5 rows came up at once
    cs.update(d, state(), 1.0, board={"garbage": 5, "height": 16})
    out = cs.update(d, state(), 1.6, board={"garbage": 5, "height": 16})
    assert "pinch" in kinds(out)                                         # high, and it stayed
    out = cs.update(d, state(), 2.0, board={"garbage": 0, "height": 7})
    assert "recover" in kinds(out)                                       # back down
    out = cs.update(d, state(), 12.0, board={"garbage": 0, "height": 7})
    assert "quiet" in kinds(out)                                         # no clear for 10 s
    out = cs.update(d, state(frozen=True, winner="left"), 13.0)
    assert "comeback" in kinds(out) and "win" in kinds(out)              # a win after a pinch


def test_a_pair_flows_together():
    """「ブロックを積むのは…」 then 「↑ は？」 right under it, a moment later (user)."""
    cs = comments.CommentStream(random.Random(0))
    pair = next(x for x in comments.POOL["ambient"][1] if isinstance(x, list))
    cs.rng.choice = lambda pool: pair if pair in pool else pool[0]
    cs._say("ambient", 10.0, "ja", 1.0)
    a, b = cs.items[-2:]
    assert (a["text"], b["text"]) == tuple(pair)
    assert b["lane"] == a["lane"] + 1 and 0 < b["t"] - a["t"] <= 1.0


def test_a_win_keeps_the_room_buzzing():
    """After a win more comments keep coming for a few seconds (the 8888s more than once is fine)."""
    cs = comments.CommentStream(random.Random(3))
    d = display_settings({"display": {"challenge_comments": "normal"}})
    st = {"match_screen": True, "match_start_t": 5.0, "you_side": "left",
          "left": {"event_log": []}, "right": {"event_log": []}}
    cs.update(d, st, 0.0)
    end = {**st, "frozen": True, "winner": "left"}
    at_once = {c["id"] for c in cs.update(d, end, 1.0)["items"] if c["kind"] == "win"}
    seen = set(at_once)
    t = 1.0
    while t < 7.0:
        t += 0.1
        seen |= {c["id"] for c in cs.update(d, end, t)["items"] if c["kind"] == "win"}
    assert len(at_once) == comments.COUNT["win"]
    assert len(seen) >= 2 * len(at_once)
    assert comments.POOL["win"][1].count("8888") >= 2


def test_a_mid_game_setup_used_is_called_out():
    """The STSD on your board, then your T-SPIN Double: "STSDきたあああ" and the like."""
    from test_midgame import STSD
    cs = comments.CommentStream(random.Random(6))
    d = display_settings({"display": {"challenge_comments": "normal"}})
    st = {"match_screen": True, "match_start_t": 5.0, "you_side": "left",
          "left": {"event_log": []}, "right": {"event_log": []}}
    cs.update(d, st, 0.0)
    board = {"garbage": 0, "height": 5, "grid": STSD}
    cs.update(d, st, 0.1, board=board)
    cs.update(d, st, 0.2, board=board)
    spun = {**st, "left": {"event_log": [{"label": "T-SPIN Double", "t": 0.3}]}}
    items = cs.update(d, spun, 0.3, board={"garbage": 0, "height": 3, "grid": STSD})["items"]
    mid = [c["text"] for c in items if c["kind"] == "midgame"]
    assert mid and all("STSD" in t or "{name}" not in t for t in mid)
    assert any("STSD" in t for t in mid)


def test_a_long_comment_is_not_on_screen_twice():
    """Short ones (GG, 8888) may come more than once; a long one only once at a time."""
    cs = comments.CommentStream(random.Random(7))
    d = display_settings({"display": {"challenge_comments": "many"}})
    st = {"match_screen": True, "match_start_t": 5.0, "you_side": "left",
          "left": {"event_log": []}, "right": {"event_log": []}}
    cs.update(d, st, 0.0)
    end = {**st, "frozen": True, "winner": "left"}
    t = 1.0
    while t < 5.0:
        items = cs.update(d, end, t)["items"]
        on = [c["text"] for c in items if not comments.REPEATABLE.match(c["text"])]
        assert len(on) == len(set(on))
        t += 0.1


def test_lines_are_as_written():
    """No made-up endings (ー, 〜, w …) added to short ones: just the lines as written."""
    assert comments._pool("tetris", "ja") == comments.POOL["tetris"][1]


def test_off_the_match_screen_they_stop_soon():
    """The set over (results / replay saving): no new ones after SET_END_S."""
    cs = comments.CommentStream(random.Random(8))
    d = display_settings({"display": {"challenge_comments": "many"}})
    st = {"match_screen": True, "match_start_t": 5.0, "you_side": "left",
          "left": {"event_log": []}, "right": {"event_log": []}}
    cs.update(d, st, 0.0)
    cs.update(d, {**st, "frozen": True, "winner": "left"}, 1.0)
    off = {"match_screen": False}
    cs.update(d, off, 1.5)
    t, last = 1.5, 0.0
    while t < 20.0:
        t += 0.1
        out = cs.update(d, off, t)
        last = max([c["t"] for c in out["items"]] + [last])
    assert last <= 1.5 + comments.SET_END_S + 3.0   # (the burst at the end spreads over a few seconds)


def _match(left, right=None, elapsed=60.0):
    return {"match_screen": True, "match_start_t": 5.0, "you_side": "left", "match_elapsed_s": elapsed,
            "left": {"event_log": [], **left}, "right": {"event_log": [], **(right or {})}}


def test_the_numbers_as_they_are():
    """Milestones once each; the live numbers now and then, not all at once."""
    d = display_settings({"display": {"challenge_comments": "normal"}})
    cs = comments.CommentStream(random.Random(9))
    cs.update(d, _match({}), 0.0)
    side = {"apm": {"apm": 62.0}, "pps": 1.6, "app": 0.4, "attack": 41, "pieces": 120, "b2b": 5,
            "match_stats": {"tspin": 5, "tetris": 1}}
    t, seen = 0.0, {}
    while t < 10.0:
        t += 0.5
        out = cs.update(d, _match(side, {"apm": {"apm": 58.0}}), t)
        seen.update({c["id"]: c for c in out["items"]})
    kinds = [c["kind"] for c in seen.values()]
    assert kinds.count("attack_mark") == comments.COUNT["attack_mark"]          # 40 lines (not 20 as well)
    assert kinds.count("pieces_mark") == comments.COUNT["pieces_mark"]
    assert kinds.count("spin_count") == comments.COUNT["spin_count"]
    assert "apm_now" in kinds
    texts = [c["text"] for c in seen.values() if c["kind"] == "attack_mark"]
    assert all("20" not in x for x in texts)
    # the BtB chain broken
    out = cs.update(d, _match({**side, "b2b": 0}), 14.0)
    assert any(c["kind"] == "b2b_break" for c in out["items"])


def test_only_crowd_lines_repeat_and_none_big():
    assert comments.REPEATABLE.match("88888") and comments.REPEATABLE.match("GG") and comments.REPEATABLE.match("ｗｗｗ")
    assert not comments.REPEATABLE.match("おめでとう") and not comments.REPEATABLE.match("完勝")
    assert comments.BIG == set()


def test_a_late_ren_break_entry_doesnt_replay_the_last_clear():
    d = display_settings({"display": {"challenge_comments": "normal"}})
    cs = comments.CommentStream(random.Random(11))
    base = {"match_screen": True, "match_start_t": 5.0, "you_side": "left", "match_elapsed_s": 5.0,
            "right": {"event_log": []}}
    cs.update(d, {**base, "left": {"event_log": []}}, 0.0)
    tetris = {"t": 10.0, "label": "TETRIS", "btb": False, "ren_count": 0}
    seen = {}
    for i in range(6):
        log = [tetris] if i == 0 else [{"t": 9.5, "label": "REN途切れ"}, tetris]
        out = cs.update(d, {**base, "left": {"event_log": log}}, 0.1 * (i + 1))
        seen.update({c["id"]: c for c in out["items"]})
    assert sum(c["kind"] == "tetris" for c in seen.values()) == comments.COUNT["tetris"]


def test_a_tetris_found_to_be_a_perfect_clear_gets_its_comments():
    """The pipeline rewrites the TETRIS entry as a PERFECT CLEAR ~0.2 s later (same time): the PC comments come."""
    d = display_settings({"display": {"challenge_comments": "normal"}})
    cs = comments.CommentStream(random.Random(12))
    base = {"match_screen": True, "match_start_t": 5.0, "you_side": "left", "match_elapsed_s": 5.0,
            "right": {"event_log": []}}
    cs.update(d, {**base, "left": {"event_log": []}}, 0.0)
    tetris = {"t": 10.0, "label": "TETRIS", "btb": False, "ren_count": 0, "perfect_clear": False}
    cs.update(d, {**base, "left": {"event_log": [tetris]}}, 0.1)
    out = cs.update(d, {**base, "left": {"event_log": [{**tetris, "label": "PERFECT CLEAR", "perfect_clear": True}]}}, 0.3)
    assert any(c["kind"] == "pc" for c in out["items"])


def test_comments_with_the_players_names():
    """Name lines only once the names are read (state["names"]); yours and theirs by you_side."""
    d = display_settings({"display": {"challenge_comments": "many"}})
    base = {"match_screen": True, "match_start_t": 5.0, "you_side": "right", "match_elapsed_s": 5.0,
            "left": {"event_log": []}, "right": {"event_log": []}}
    cs = comments.CommentStream(random.Random(13))
    texts = [c["text"] for c in cs.update(d, base, 0.0)["items"]]
    assert not any("{" in t for t in texts)                                  # no names yet: none of theirs
    seen = set()
    for i in range(40):
        cs2 = comments.CommentStream(random.Random(i))
        out = cs2.update(d, {**base, "names": {"left": "AAA", "right": "めぞん"}}, 0.0)
        seen |= {c["text"] for c in out["items"]}
    assert any("めぞん" in t for t in seen) and not any("{" in t for t in seen)
    assert not any(t.startswith("AAA") and "がんばれ" in t for t in seen)     # (AAA is the rival here)


def test_reading_names():
    import player_names
    assert player_names.clean(" め ぞ ん ") == "めぞん"
    assert player_names.clean("x" * 30) == ""
    assert player_names.settle(["めぞん", "めそん", "めぞん"]) is None
    assert player_names.settle(["めぞん", "めそん", "めぞん", "めぞん"]) == "めぞん"


def test_the_readers_usual_slips_put_right():
    import player_names
    assert player_names.clean("タ映えの少女が可憐") == "夕映えの少女が可憐"
    assert player_names.clean("CPUI") == "CPU1"
    assert player_names.clean("タロウ") == "タロウ"            # (タ before kana: left alone)
    assert player_names.clean("ハタ山") == "ハタ山"            # (inside a katakana word: left alone)


def test_a_burst_of_attack_gets_the_room_going():
    """Lots of attack sent in a short time: a burst of comments, then more for a moment (user)."""
    d = display_settings({"display": {"challenge_comments": "normal"}})
    cs = comments.CommentStream(random.Random(3))
    cs.update(d, state(), 0.0)
    log = [ev(10.0, "TETRIS", lines=4), ev(11.0, "T-SPIN Double", lines=4)]
    out = cs.update(d, state(log[:1]), 1.0)
    out = cs.update(d, state(log[::-1]), 2.0)
    assert not any(c["kind"] == "burst" for c in out["items"])          # 8 lines: not yet
    log = [ev(12.0, "TETRIS", lines=5)] + log[::-1]
    out = cs.update(d, state(log), 3.0)
    first = sum(c["kind"] == "burst" for c in out["items"])
    assert first >= comments.COUNT["burst"]                                # 13 lines in 2 s (a pair: two)
    out = cs.update(d, state(log), 4.5)
    assert sum(c["kind"] == "burst" for c in out["items"]) > first         # and on for a moment
    slow = comments.CommentStream(random.Random(3))
    slow.update(d, state(), 0.0)
    log = []
    for k in range(4):   # the same lines, spread out: nothing
        log = [ev(10.0 + k * 8, "TETRIS", lines=4)] + log
        out = slow.update(d, state(log), 1.0 + k * 8)
        assert not any(c["kind"] == "burst" for c in out["items"])


def test_a_pause_has_comments_of_its_own():
    """Paused mid-match: a few on the pause, its own lines while it lasts, a welcome back after (user)."""
    d = display_settings({"display": {"challenge_comments": "normal"}})
    cs = comments.CommentStream(random.Random(5))
    of = lambda out, kind: [c for c in out["items"] if c["kind"] == kind]
    cs.update(d, state(), 0.0)
    out = cs.update(d, state(paused=True), 1.0)
    assert len(of(out, "pause")) >= comments.COUNT["pause"]
    n = len(of(out, "pause"))
    for k in range(20):   # paused a while: pause lines, not the usual chatter
        out = cs.update(d, state(paused=True), 1.5 + k * 0.5)
    assert len(of(out, "pause")) > 0 and not of(out, "ambient")
    out = cs.update(d, state(), 12.0)
    assert len(of(out, "resume")) >= comments.COUNT["resume"]
    out = cs.update(d, state(paused=True, frozen=True), 13.0)   # (after the match: not a pause)
    assert not [c for c in of(out, "pause") if c["t"] >= 13.0]


def test_comments_in_a_row_never_touch():
    """A crowd (a loss: lots at once): two comments in one row never run into
    each other (user: they read as one, "くやしいうわあああ")."""
    d = display_settings({"display": {"challenge_comments": "many"}})
    cs = comments.CommentStream(random.Random(2))
    cs.update(d, state(), 0.0)
    seen, t = {}, 0.0
    while t < 12:
        t += 0.1
        for c in cs.update(d, state(frozen=t > 2, winner="right" if t > 2 else None), t)["items"]:
            seen[c["id"]] = c
    items = list(seen.values())
    assert len(items) > 30
    for a in items:
        for b in items:
            if a["id"] < b["id"] and a["lane"] == b["lane"]:
                assert comments.apart((a["t"], comments.text_width(a["text"])), (b["t"], comments.text_width(b["text"])))
