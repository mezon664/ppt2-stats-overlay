"""ドーパミンモード (hud/dopamine.py): a loud burst for each TETRIS / T-SPIN / PC of yours."""
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hud"))

from PyQt6 import QtGui, QtWidgets

import challenge
import dopamine
from config_store import display_settings

APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def ev(t, label, btb=False, ren=0, pc=False):
    return {"t": t, "label": label, "btb": btb, "ren_count": ren, "perfect_clear": pc}


def state(log, start=10.0, b2b=0, frozen=False):
    return {"match_screen": True, "match_start_t": start, "you_side": "left", "frozen": frozen,
            "left": {"event_log": log, "b2b": b2b}, "right": {"event_log": []}}


def test_setting_default_off_and_checked():
    assert display_settings({"display": {}})["challenge_dopamine"] == "off"
    assert display_settings({"display": {"challenge_dopamine": "max"}})["challenge_dopamine"] == "max"
    assert display_settings({"display": {"challenge_dopamine": "huge"}})["challenge_dopamine"] == "off"


def test_what_bursts():
    assert dopamine.kind_of(ev(1, "T-SPIN Double"))[0] == "T-SPIN DOUBLE"
    assert dopamine.kind_of(ev(1, "TETRIS"))[0] == "TETRIS"
    assert dopamine.kind_of(ev(1, "TETRIS", pc=True))[0] == "PERFECT CLEAR"
    assert dopamine.kind_of(ev(1, "REN途切れ")) is None
    assert dopamine.kind_of(ev(1, "T-SPIN")) is None          # (no lines: nothing to cheer)


def test_bigger_clears_burst_bigger():
    small = dopamine.Burst("a", "left", 0.0, ev(1, "T-SPIN Single"))
    big = dopamine.Burst("a", "left", 0.0, ev(1, "T-SPIN Triple"))
    louder = dopamine.Burst("a", "left", 0.0, ev(1, "T-SPIN Triple"), "max", b2b=4)
    assert small.power < big.power < louder.power
    assert len(small.parts) < len(big.parts) < len(louder.parts)
    assert any(op[0] == "rays" for op in big.ops(0.3)) and not any(op[0] == "rays" for op in small.ops(0.3))
    pc = dopamine.Burst("a", "left", 0.0, ev(1, "TETRIS", pc=True))
    assert pc.confetti and any(op[0] == "confetti" for op in pc.ops(1.0))
    # the subtitle: the BtB chain and the REN
    assert dopamine.Burst("a", "left", 0.0, ev(1, "TETRIS", btb=True, ren=3), b2b=2).sub == "BACK-TO-BACK x2   3 REN"
    # gone after its time, nothing drawn then
    assert big.gone(big.duration) and big.ops(big.duration) == []


def test_it_draws():
    img = QtGui.QImage(616, 346, QtGui.QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QtGui.QPainter(img)
    b = dopamine.Burst("a", "left", 0.0, ev(1, "TETRIS", pc=True), "max", b2b=5)
    for t in (0.0, 0.1, 0.5, 1.2, 2.5):
        dopamine.paint(p, b, 0.5, t, 616, 346)
    p.end()
    assert img.pixelColor(150, 160).alpha() > 0


def test_the_layer_bursts_for_new_clears_only():
    layer = challenge.ChallengeLayer(None)
    d = display_settings({"display": {"challenge_dopamine": "on"}})
    old = [ev(5.0, "TETRIS")]
    layer.update_state(state(old), d, 1.0, True)
    assert layer.bursts == []                                 # what was there before: no flood
    layer.update_state(state([ev(7.0, "T-SPIN Double"), ev(6.0, "REN途切れ")] + old, b2b=1), d, 1.0, True)
    assert [b.title for b in layer.bursts] == ["T-SPIN DOUBLE"]
    # a new match: none carried over; off: none
    layer.update_state(state([], start=20.0), d, 1.0, True)
    layer.update_state(state([ev(21.0, "TETRIS")], start=20.0), display_settings({"display": {}}), 1.0, True)
    assert layer.bursts == []


def test_the_obs_page_has_the_same_numbers():
    page = (ROOT / "obs" / "overlay.html").read_text(encoding="utf-8")

    def js(name):
        m = re.search(rf"\b{name} = ([^,;]+(?:\[[^\]]*\])?)", page)
        return m.group(1)
    assert js("DOPA_FLASH_S") == str(dopamine.FLASH_S)
    assert f"DOPA_PARTICLES = {list(dopamine.PARTICLES)}" in page
    alpha = re.search(r"DOPA_FLASH_ALPHA = \[([^\]]*)\]", page).group(1)
    assert [float(x) for x in alpha.split(",")] == list(dopamine.FLASH_ALPHA)
    assert js("DOPA_TEXT_PX") == str(dopamine.TEXT_PX)
    assert js("DOPA_CONFETTI") == str(dopamine.CONFETTI)
    assert f"DOPA_RAYS = {dopamine.RAYS}" in page and f"DOPA_RING_S = {dopamine.RING_S}" in page


def test_sounds_for_each_burst():
    small = dopamine.Burst("a", "left", 0.0, ev(1, "T-SPIN Single"))
    big = dopamine.Burst("a", "left", 0.0, ev(1, "TETRIS", pc=True), "max")
    assert [n for _, n in small.sounds] == ["kyuin_p0", "slam"]
    assert {"whoosh", "fever", "jara"} <= {n for _, n in big.sounds}
    files = {p.stem for p in dopamine.SOUNDS_DIR.glob("*.wav")}
    assert {n for _, n in big.sounds} | {"fanfare_p0"} <= files
    assert display_settings({"display": {"challenge_dopamine_volume": 300}})["challenge_dopamine_volume"] == 100


def test_rainbow_in_the_same_steps_on_the_page():
    page = (ROOT / "obs" / "overlay.html").read_text(encoding="utf-8")
    assert f"DOPA_HUE_STEPS = {dopamine.HUE_STEPS}," in page


def test_text_pictures_are_kept():
    """The slow part of a text is made once; a new colour only tints it."""
    dopamine._TEXT_IMAGES.clear()
    dopamine._TEXT_LAYERS.clear()
    font = dopamine._title_font(66, 1.0)
    a = dopamine._text_image("TETRIS", font, ((0, (255, 255, 255)), (1, (0, 0, 255))), (0, 0, 255), (0, 0, 0), 4, 1.0)
    assert dopamine._text_image("TETRIS", font, ((0, (255, 255, 255)), (1, (0, 0, 255))), (0, 0, 255), (0, 0, 0), 4, 1.0) is a
    dopamine._text_image("TETRIS", font, ((0, (255, 255, 255)), (1, (255, 0, 0))), (255, 0, 0), (0, 0, 0), 4, 1.0)
    assert len(dopamine._TEXT_LAYERS) == 1 and len(dopamine._TEXT_IMAGES) == 2


def test_higher_with_every_back_to_back():
    """Each BtB in a row: the sounds a step up the scale, a bell too; past the top they stay there."""
    def names(b2b, btb=True):
        return [n for _, n in dopamine.Burst("a", "left", 0.0, ev(1, "T-SPIN Triple", btb=btb), "max", b2b=b2b).sounds]
    assert "kyuin_p0" in names(0, btb=False) and not any(n.startswith("chime") for n in names(0, btb=False))
    assert "kyuin_p3" in names(3) and "chime_p3" in names(3) and "fanfare_p3" in names(3)
    assert "kyuin_p14" in names(40)
    # (only the base pitch ships; the higher ones are made from it on the PC, and kept)
    assert all(dopamine.pitched_file(n, i).exists() for n in dopamine.PITCHED for i in (0, 7, dopamine.PITCH_STEPS - 1))
    assert len(dopamine.PITCH_SCALE) == dopamine.PITCH_STEPS


def test_every_five_back_to_backs_a_level_up():
    def burst(b2b, btb=True):
        return dopamine.Burst("a", "left", 0.0, ev(1, "T-SPIN Double", btb=btb), "on", b2b=b2b)
    b4, b5, b6, b10 = burst(4), burst(5), burst(6), burst(10)
    assert (b4.tier, b5.tier, b6.tier, b10.tier) == (0, 1, 1, 2)
    assert b5.milestone and b10.milestone and not b6.milestone
    assert len(b4.parts) < len(b6.parts) < len(b10.parts)                 # bigger from 5 on
    assert b5.band == "BtB5連!!" and b10.band == "BtB10突破!!!"
    assert b5.confetti and not b6.confetti                                 # gold rain on the milestone
    assert ("fever" in [n for _, n in b5.sounds]) and b5.flashes == dopamine.FLASH_COLORS
    assert b6.band and b6.medals                                           # (the band and medals from BtB 5 on)
    assert burst(5, btb=False).tier == 0


def test_the_page_levels_up_the_same():
    page = (ROOT / "obs" / "overlay.html").read_text(encoding="utf-8")
    assert f"DOPA_BTB_TIER = {dopamine.BTB_TIER}" in page and f"DOPA_TIER_MAX = {dopamine.TIER_MAX}" in page
    assert "BtB${b2b}連!!" in page and "BtB${b2b}突破!!!" in page


def test_flashes_leave_the_middle_clear_and_pc_is_its_own_show():
    assert 0 < dopamine.FLASH_CLEAR < 1
    pc = dopamine.Burst("a", "left", 0.0, {**ev(1, "TETRIS", pc=True), "lines": 10}, "max", chain=6)
    assert pc.flashes == 0 and any(op[0] == "dim" for op in pc.ops(0.2))
    assert pc.band == "FEVER!!!" and pc.reels == 0                          # always FEVER, 777
    letters = [op[1] for op in pc.ops(2.0) if op[0] == "text" and len(op[1]) == 1]
    assert "".join(letters) == "PERFECTCLEAR"                                # one letter at a time
    assert any(op[0] == "spark" for op in pc.ops(1.2))                       # fireworks
    names = [n for _, n in pc.sounds]
    assert names.count("whistle") == dopamine.ROCKETS and "jackpot" in names


def test_reels_and_the_lines_sent():
    b = dopamine.Burst("a", "left", 0.0, {**ev(1, "T-SPIN Triple", btb=True), "lines": 6}, "max", b2b=3)
    reels = [op for op in b.ops(2.0) if op[0] == "reels"][0]
    assert all(abs(x - b.reels) < 0.05 for x in reels[3])                     # all three on the triple
    assert [op[1] for op in b.ops(0.2) if op[0] == "attack"] == ["+6"]
    x = [op for op in b.ops(dopamine.ATTACK_UP + dopamine.ATTACK_FLY + 0.05) if op[0] == "attack"][0][2]
    assert abs(x - b.target[0]) < 1                                          # landed on the other board
    files = {p.stem for p in dopamine.SOUNDS_DIR.glob("*.wav")}
    assert {"tick", "jackpot", "whistle", "pop"} <= files


def test_a_late_ren_break_entry_doesnt_replay_the_last_clear():
    """The REN break goes on top of the log later, with an earlier time than the
    TETRIS under it: that TETRIS isn't new again (it burst ~10 times running)."""
    layer = challenge.ChallengeLayer(None)
    d = display_settings({"display": {"challenge_dopamine": "on"}})
    layer.update_state(state([]), d, 1.0, True)
    tetris = ev(10.0, "TETRIS")
    layer.update_state(state([tetris]), d, 1.0, True)
    assert len(layer.bursts) == 1
    for _ in range(5):
        layer.update_state(state([ev(9.5, "REN途切れ"), tetris]), d, 1.0, True)
    assert len(layer.bursts) == 1
    # a PERFECT CLEAR found a moment later on that same clear: its own show
    layer.update_state(state([ev(9.5, "REN途切れ"), {**tetris, "label": "PERFECT CLEAR", "perfect_clear": True}]), d, 1.0, True)
    assert [b.pc for b in layer.bursts] == [True]     # (the TETRIS's burst gave way to the PC's)


def test_the_everyday_level_is_calm():
    """普通: the name, a ring, a few sparkles, the lines sent, a bell — no flashes, bands, reels, medals."""
    b = dopamine.Burst("a", "left", 0.0, {**ev(1, "T-SPIN Triple", btb=True), "lines": 6}, "lite", b2b=10, chain=8)
    kinds = {op[0] for t in (0.05, 0.3, 0.8) for op in b.ops(t)}
    assert not kinds & {"flash", "dim", "band", "reels", "medal", "pillar", "rays", "frame", "confetti"}
    assert {"text", "attack"} <= kinds and "ring" not in {op[0] for op in b.ops(0.3)}
    assert b.tier == 0 and not b.milestone and b.duration < 2.0
    assert [n for _, n in b.sounds] == ["glint_p10"]
    assert display_settings({"display": {"challenge_dopamine": "lite"}})["challenge_dopamine"] == "lite"
    pc = dopamine.Burst("a", "left", 0.0, ev(1, "TETRIS", pc=True), "lite")
    assert len(pc.rockets) == dopamine.LITE_ROCKETS and not any(op[0] == "dim" for op in pc.ops(0.2))


def test_what_the_announcer_says():
    tsd = dopamine.Burst("a", "left", 0.0, ev(1, "T-SPIN Double", btb=True), "lite", b2b=2)
    assert dopamine.phrase(tsd) == "Back to Back, T-Spin Double!"
    assert dopamine.phrase(dopamine.Burst("a", "left", 0.0, ev(1, "TETRIS"), "lite")) == "Tetris!"
    assert dopamine.phrase(dopamine.Burst("a", "left", 0.0, ev(1, "TETRIS", btb=True, pc=True), "lite", b2b=3)) == "Perfect Clear!"
    assert display_settings({"display": {}})["challenge_announcer"] is False
    assert display_settings({"display": {}})["challenge_announcer_voice"] == "heart"
    assert display_settings({"display": {"challenge_announcer_voice": "x"}})["challenge_announcer_voice"] == "heart"


def test_every_line_is_recorded_in_both_voices():
    lines = dopamine.phrases()
    assert len(lines) == 13 and "Back to Back, Perfect Clear!" not in lines
    for voice in dopamine.ANNOUNCER_VOICES:
        for text in lines:
            assert dopamine.line_file(voice, text).exists(), (voice, text)




def test_the_announcer_works_without_the_effects():
    said = []

    class Fake:
        def preload(self, voice="heart", kind="plain"):
            pass

        def say(self, burst, volume, voice="heart"):
            said.append((dopamine.phrase(burst), volume, voice))
    real = dopamine.shared_announcer
    dopamine.shared_announcer = lambda: Fake()
    try:
        layer = challenge.ChallengeLayer(None)
        d = display_settings({"display": {"challenge_announcer": True, "challenge_announcer_voice": "adam"}})
        layer.update_state(state([]), d, 1.0, True)
        layer.update_state(state([ev(10.0, "T-SPIN Double", btb=True)], b2b=1), d, 1.0, True)
        assert layer.bursts == []                                   # (演出強化 off: no effects)
        assert said == [("Back to Back, T-Spin Double!", 100, "adam")]
    finally:
        dopamine.shared_announcer = real


def test_the_voice_can_go_louder_than_100():
    import numpy as np
    assert dopamine.play_level(50) == ("plain", 0.5)
    assert dopamine.play_level(100) == ("plain", 1.0)
    assert dopamine.play_level(200) == ("loud", 1.0)
    assert dopamine.play_level(150)[0] == "loud"
    x = 0.97 * np.sin(np.linspace(0, 200 * np.pi, 24000)) * np.linspace(0.1, 1, 24000)
    y = dopamine.louder(x)
    assert np.sqrt((y ** 2).mean()) > 1.3 * np.sqrt((x ** 2).mean()) and np.abs(y).max() <= 0.97 + 1e-9
    assert display_settings({"display": {"challenge_announcer_volume": 180}})["challenge_announcer_volume"] == 180


def test_old_clears_turning_up_again_say_nothing():
    """The log seen empty for a moment, then whole again: its old clears aren't
    new — no burst, no voice (user: the voice with nothing done)."""
    said = []

    class Fake:
        def preload(self, voice="heart", kind="plain"):
            pass

        def say(self, burst, volume, voice="heart"):
            said.append(dopamine.phrase(burst))
    real = dopamine.shared_announcer
    dopamine.shared_announcer = lambda: Fake()
    try:
        layer = challenge.ChallengeLayer(None)
        d = display_settings({"display": {"challenge_announcer": True, "challenge_dopamine": "on"}})
        old = [ev(25.0, "TETRIS"), ev(15.0, "T-SPIN Double")]
        at = lambda log, elapsed: {**state(log), "match_elapsed_s": elapsed}
        layer.update_state(at(old, 20.0), d, 1.0, True)
        layer.update_state(at([], 20.1), d, 1.0, True)        # (a moment with the log empty)
        layer.update_state(at(old, 20.2), d, 1.0, True)       # the old ones again
        assert said == [] and layer.bursts == []
        layer.update_state(at([ev(30.4, "TETRIS")] + old, 20.5), d, 1.0, True)   # a real new one
        assert said == ["Tetris!"] and len(layer.bursts) == 1
    finally:
        dopamine.shared_announcer = real
