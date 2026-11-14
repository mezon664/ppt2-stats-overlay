"""演出強化モード (display.challenge_dopamine; first called ドーパミンモード):
each TETRIS / T-SPIN / PERFECT CLEAR of yours gets its own effect over the
game. Three levels (user: what came first is the joke top level; make one
fit to play with every day):

  "lite"  普通 — the clear's name, a ring, a few sparkles, the lines sent
          flying to the other board, a soft bell (higher with each BtB); a
          PERFECT CLEAR: its letters dropping in, three fireworks. No
          flashes, nothing over the middle of the screen for long.
  "on"    派手 / "max" 超派手 — a pachinko parlour's worth, below.

  - flashes round the screen's edges only, the middle (the game) left clear
    (user: a bit too bright, a whole-screen flash); the big ones flash
    again, up to 3 times, 1/3 s apart: never more than 3 a second
  - a slot machine's three reels spinning and stopping one by one on a
    triple (BAR, ★, 777 for a PC or a BtB milestone)
  - the lines sent, "+N", flying over to the other player's board
  - a PERFECT CLEAR its own show: the screen dims, P-E-R-F-E-C-T drops in a
    letter at a time, fireworks go up all over, 777, FEVER, gold rain
  - shock rings, flying blocks and sparkles, light rays turning behind
  - the clear's name slammed in big (rainbow letters at "max")
  - a rainbow LED frame chasing round the screen's edge
  - a cut-in band across the screen, pachinko style: 激アツ!! 大当たり!!
    確変突入!!! … or 〇連チャン!! when they keep coming
  - spotlights sweeping up from below, a fountain of gold medals
  - confetti over everything for a PERFECT CLEAR
  - 連チャン: the bursts this match are counted, and shown
  - every BTB_TIER Back-to-Backs in a row it all goes up a level (user):
    the bursts after BtB 5 are bigger, after 10 bigger again; at BtB 5, 10,
    15 … itself a special one — 「BtB5連!!」「BtB10突破!!!」 on the band,
    three flashes, gold rain over the screen, the FEVER fanfare
  - sounds (assets/dopamine_sounds/, made by tools/sound/make_dopamine_sounds.py):
    a キュイン every time, a boom as the name lands, and for the big ones a
    whoosh with the band, a fanfare (FEVER for a PC) and medals pouring.
    Played by the app (Sounds below), not the OBS page: the PC's speakers,
    so the player hears them and OBS's desktop audio takes them to the
    stream (from both they'd come twice)

The bursts are worked out here as plain shapes (ops) for a moment in time,
from a seed: hud/challenge.py draws them with Qt, obs/overlay.html dopa*
the same numbers on its canvas (keep the two in sync). All in reference px
(1232 x 692).

  level "on":  the band and medals for the big ones only; "max": one step
               bigger every time, everything for everything
"""
import math
from pathlib import Path

from challenge import Rand, BOARD, SCREEN_W, SCREEN_H

LEVELS = ("off", "lite", "on", "max")
LITE_TEXT_K, LITE_HOLD_S, LITE_PARTS, LITE_ROCKETS = 0.6, 0.6, 0.3, 3
LITE_TOP = 24        # (普通: the name at the board's top edge, this far down)
MAX_BURSTS = 6

# what each clear is: (title, power 1-4, palette)
PURPLE = ((196, 75, 255), (255, 91, 225), (150, 120, 255), (255, 255, 255))
CYAN = ((59, 232, 255), (74, 123, 255), (140, 255, 250), (255, 255, 255))
GOLD = ((255, 225, 74), (255, 91, 208), (91, 255, 176), (90, 200, 255), (255, 255, 255))
KINDS = {
    "T-SPIN Single": ("T-SPIN SINGLE", 1, PURPLE),
    "T-SPIN Double": ("T-SPIN DOUBLE", 2, PURPLE),
    "T-SPIN Triple": ("T-SPIN TRIPLE", 3, PURPLE),
    "T-SPIN Mini Single": ("T-SPIN MINI", 1, PURPLE),
    "T-SPIN Mini Double": ("T-SPIN MINI DOUBLE", 2, PURPLE),
    "TETRIS": ("TETRIS", 2, CYAN),
}
PC = ("PERFECT CLEAR", 4, GOLD)
MEDAL = ((255, 214, 64), (255, 245, 170), (190, 130, 20))   # the gold medals: face, shine, rim

# (power: 1 small .. 6 all out; index 0 unused)
FLASH_S = 0.22
FLASH_ALPHA = (0, 0.20, 0.28, 0.36, 0.44, 0.50, 0.56)   # (at the screen's edge; the middle stays clear)
FLASH_CLEAR = 0.42                 # the middle this share of the way out is left clear
FLASH_GAP_S = 0.34                 # the next flash of a big one (3 a second at most)
FLASH_COLORS = 3                   # (1st: the clear's colour, 2nd: gold, 3rd: its other colour)
RING_S, RING_GAP_S = 0.55, 0.07
RAYS, RAY_SPIN, RAY_S = 18, 0.7, 1.6
PARTICLES = (0, 34, 56, 84, 120, 150, 180)
GRAVITY = 900.0
TEXT_IN_S, TEXT_HOLD_S, TEXT_OUT_S = 0.16, 1.1, 0.45
TEXT_PX = 66
CONFETTI, CONFETTI_S = 150, 2.8
FRAME_S, FRAME_SEGMENTS, FRAME_PX = 1.4, 56, 12      # the LED frame: how long (+0.2 s a power), lights, width
BAND_IN, BAND_STOP, BAND_HOLD, BAND_OUT = 0.10, 0.28, 0.95, 1.15   # the cut-in: slides in, sits, slides out
BAND_Y, BAND_H, BAND_PX = 470, 132, 92
BAND_WORDS = (None, "アツい!!", "アツい!!", "激アツ!!", "大当たり!!", "確変突入!!!", "超激アツ!!!")
BAND_PC = "FEVER!!!"
PILLARS, PILLAR_S = 6, 1.6
MEDALS, MEDAL_GRAVITY, MEDAL_S = 26, 1500.0, 2.3
BTB_TIER = 5         # every this many BtBs in a row: a level up (and a special burst on it)
TIER_MAX = 3
PITCH_STEPS = 15     # the sounds' pitches (tools/sound/make_dopamine_sounds.py SCALE): BtB 0 .. 14 and on
REEL_SYMBOLS = ("7", "BAR", "★", "◆", "♥")
REEL_IN, REEL_STOP, REEL_GAP, REEL_SPEED, REEL_END = 0.12, 0.55, 0.28, 16.0, 2.2
REEL_W, REEL_H, REEL_PX = 66, 76, 46
REEL_SCALE = {"BAR": 0.55}          # (wider than the rest: made to fit its box)
ATTACK_UP, ATTACK_FLY, ATTACK_HIT = 0.30, 0.55, 0.35    # "+N": pops up, flies to the other board, lands
ATTACK_PX = 58
PC_S = 3.9                          # a PERFECT CLEAR's own show
PC_DIM = 0.38
PC_LETTER_START, PC_LETTER_GAP, PC_LETTER_DROP = 0.30, 0.07, 0.25
ROCKETS, ROCKET_START, ROCKET_GAP, ROCKET_RISE = 7, 0.35, 0.32, 0.5
SPARKS, SPARK_LIFE, SPARK_GRAVITY, SPARK_PX = 60, 1.2, 240.0, 8
HUE_STEPS = 12       # the rainbow letters change colour in this many steps a turn (each a new picture)


def kind_of(event):
    """(title, power, palette) for an event_log entry, or None (not one that bursts)."""
    if not isinstance(event, dict):
        return None
    if event.get("perfect_clear"):
        return PC
    label = str(event.get("label") or "")
    if label in KINDS:
        return KINDS[label]
    if "TETRIS" in label:
        return KINDS["TETRIS"]
    return None


def _ease_out(t):
    return 1 - (1 - t) ** 3


def _ease_back(t):
    c = 1.9
    return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2


def hue(h, sat=1.0, light=0.55):
    """An RGB tuple for a hue in [0, 1) (HSL; the page's hsl() the same)."""
    h = h % 1.0
    c = (1 - abs(2 * light - 1)) * sat
    x = c * (1 - abs((h * 6) % 2 - 1))
    m = light - c / 2
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][int(h * 6) % 6]
    return int(round((r + m) * 255)), int(round((g + m) * 255)), int(round((b + m) * 255))


class Burst:
    def __init__(self, seed, side, t0, event, level="on", b2b=0, chain=1):
        title, power, palette = kind_of(event)
        self.seed, self.side, self.t0, self.level = seed, side, t0, level
        self.btb = bool(event.get("btb")) and b2b >= 1
        self.event_t = round(float(event.get("t") or 0), 3)   # (which clear: a PC found later replaces it)
        self.title, self.palette, self.pc = title, palette, palette is GOLD
        self.max = level == "max"
        self.lite = level == "lite"
        btb = bool(event.get("btb")) and b2b >= 1
        self.tier = min(TIER_MAX, b2b // BTB_TIER) if btb and not self.lite else 0   # BtB 5+: 1, 10+: 2, 15+: 3
        self.milestone = btb and b2b >= BTB_TIER and b2b % BTB_TIER == 0 and not self.lite  # BtB 5, 10, 15 …
        boost = 1 + 0.5 * self.tier
        self.power = power if self.lite else \
            min(6, power + (1 if self.max else 0) + (1 if b2b >= 3 else 0) + min(2, self.tier))
        self.chain = chain
        subs = []
        if event.get("btb") and b2b >= 1:
            subs.append(f"BACK-TO-BACK x{b2b}")
        ren = int(event.get("ren_count") or 0)
        if ren >= 2:
            subs.append(f"{ren} REN")
        self.sub = "   ".join(subs)
        x1, y1, x2, y2 = BOARD[side]
        self.cx, self.cy = (x1 + x2) / 2, (y1 + y2) / 2
        # where the name, the sparkles and "+N" start: the board's middle — at
        # 普通 its top edge instead, the rows you play in left clear (user)
        self.ty = y1 + LITE_TOP if self.lite else self.cy - 70
        self.oy = y1 + LITE_TOP if self.lite else self.cy
        self.ay = y1 + LITE_TOP + 44 if self.lite else self.cy + 40
        rng = Rand(seed)
        n = int(PARTICLES[self.power] * (LITE_PARTS if self.lite else (2.0 if self.max else 1.0)) * boost)
        self.parts = []
        for _ in range(n):
            a = rng.uniform(0, 2 * math.pi)
            speed = rng.uniform(260, 560 + 70 * self.power)
            self.parts.append((math.cos(a) * speed, math.sin(a) * speed - rng.uniform(80, 260),
                               rng.uniform(0.7, 1.2 + 0.1 * self.power), rng.uniform(5, 9 + self.power),
                               int(rng.random() * len(palette)), rng.random() < 0.35, rng.uniform(0, 360),
                               rng.uniform(-720, 720)))
        self.confetti = []
        self.confetti_pal = GOLD if self.milestone else palette   # (a BtB milestone: gold rain)
        if self.pc or self.milestone:
            for _ in range(int(CONFETTI * (0.4 if self.lite else (1.6 if self.max else 1.0)))):
                self.confetti.append((rng.uniform(0, SCREEN_W), rng.uniform(-260, -10), rng.uniform(180, 420),
                                      rng.uniform(0.5, 2.0), rng.uniform(20, 60),
                                      int(rng.random() * len(self.confetti_pal)),
                                      rng.uniform(0, 360), rng.uniform(-540, 540), rng.uniform(6, 12)))
        self.shake = (rng.uniform(0, 6.28), rng.uniform(0, 6.28))
        # the pachinko parts: what shows for this one
        big = (self.power >= (2 if self.max else 4) or self.tier >= 1) and not self.lite
        self.flashes = 0 if self.lite else (
            FLASH_COLORS if self.milestone else min(FLASH_COLORS, max(1, self.power - (1 if self.max else 2))))
        self.frame = (self.power >= (1 if self.max else 3) or self.tier >= 1) and not self.lite
        self.frame_px = FRAME_PX * (1.4 if self.max else 1.0) * (1 + 0.35 * self.tier)
        self.text_k = 1.0 + 0.1 * self.tier + (0.1 if self.milestone else 0)
        self.band = None
        if big:
            word = BAND_PC if self.pc else BAND_WORDS[self.power]
            if chain >= 3 and rng.random() < 0.5 and not self.pc:   # (a PC: always FEVER)
                word = f"{chain}連チャン!!"
            if self.milestone:
                word = f"BtB{b2b}連!!" if b2b < 2 * BTB_TIER else f"BtB{b2b}突破!!!"
            self.band = word
        self.pillars = [(rng.uniform(0.05, 0.95) * SCREEN_W, rng.uniform(0, 1), rng.uniform(0.6, 1.4))
                        for _ in range(PILLARS)] if big else []
        self.medals = []
        if big:
            for _ in range(int(MEDALS * max(1, self.power - 2) * (1.5 if self.max else 1.0) * boost)):
                self.medals.append((self.cx + rng.uniform(-170, 170), rng.uniform(-320, 320),
                                    -rng.uniform(800, 1250), rng.uniform(0, 0.35), rng.uniform(9, 15),
                                    rng.uniform(4, 11), rng.uniform(0, 6.28)))
        # the sounds: (seconds in, name). Each Back-to-Back in a row a step higher
        # (user: for the brain juice): the キュイン, the fanfare, and a bell
        # going up a scale as the chain goes on
        self.step = min(PITCH_STEPS - 1, b2b) if event.get("btb") and b2b >= 1 else 0
        self.sounds = [(0.0, f"kyuin_p{self.step}"), (TEXT_IN_S * 0.7, "slam")]
        if self.step:
            self.sounds.append((0.05, f"chime_p{self.step}"))
        if self.lite:   # (普通: a soft bell arpeggio, a step higher each BtB — the plain bell sounded cheap)
            self.sounds = [(0.0, f"glint_p{self.step}")]
        if self.band:
            self.sounds += [(BAND_IN, "whoosh"),
                            (BAND_STOP, "fever" if self.pc or self.milestone else f"fanfare_p{self.step}")]
        if self.medals:
            self.sounds.append((0.2, "jara"))
        # the slot reels (with the band): what they land on
        self.reels = None
        if self.band:
            self.reels = 0 if (self.pc or self.milestone) else (2 if (self.tier >= 1 or self.power >= 5) else 1)
            stops = [REEL_STOP + REEL_GAP * i for i in range(3)]
            self.sounds += [(at, "tick") for at in stops] + [(stops[-1] + 0.05, "jackpot")]
        # the lines sent, flying over to the other board
        self.lines = int(event.get("lines") or 0)
        other = "right" if side == "left" else "left"
        ox1, oy1, ox2, oy2 = BOARD[other]
        self.target = ((ox1 + ox2) / 2, (oy1 + oy2) / 2)
        # a PERFECT CLEAR: fireworks
        self.rockets = []
        if self.pc:
            for i in range(LITE_ROCKETS if self.lite else ROCKETS):
                launch = ROCKET_START + ROCKET_GAP * i
                x = rng.uniform(0.12, 0.88) * SCREEN_W
                peak = rng.uniform(70, 230)
                h0 = rng.random()
                sparks = [(2 * math.pi * k / SPARKS + rng.uniform(-0.05, 0.05), rng.uniform(170, 360))
                          for k in range(SPARKS)]
                self.rockets.append((launch, x, peak, h0, sparks))
                self.sounds += [(launch, "whistle"), (launch + ROCKET_RISE, "pop")] if not self.lite else \
                    [(launch + ROCKET_RISE, "pop")]
            self.flashes = 0   # (dimmed instead: its own show)
        self.hold = LITE_HOLD_S if self.lite else TEXT_HOLD_S
        self.duration = max(TEXT_IN_S + self.hold + TEXT_OUT_S, CONFETTI_S if self.confetti else 0,
                            REEL_END if self.reels is not None else 0, PC_S if self.pc else 0,
                            ATTACK_UP + ATTACK_FLY + ATTACK_HIT if self.lines else 0,
                            MEDAL_S if self.medals else 0, FRAME_S + 0.2 * self.power if self.frame else 0)

    def _pc_letters(self, t, out):
        """P-E-R-F-E-C-T C-L-E-A-R dropping in one letter at a time, each its own colour."""
        px = TEXT_PX * 1.25 * (LITE_TEXT_K if self.lite else 1.0)
        adv = px * 0.80
        letters = [(i, ch) for i, ch in enumerate(self.title)]
        width = adv * len(letters)
        left = min(max(self.cx - width / 2, 10), SCREEN_W - 10 - width)
        end = PC_S - 0.9
        step = round(t * 0.9 * HUE_STEPS) / HUE_STEPS
        for i, ch in letters:
            if ch == " ":
                continue
            start = PC_LETTER_START + PC_LETTER_GAP * i
            u = t - start
            if u < 0:
                continue
            drop = min(1.0, u / PC_LETTER_DROP)
            y = self.ty - 220 * (1 - _ease_back(drop))
            a = min(1.0, drop * 3) * (1.0 if t < end else max(0.0, 1 - (t - end) / 0.5))
            colors = (hue(step + i / len(letters)), hue(step + i / len(letters) + 0.33))
            out.append(("text", ch, left + adv * (i + 0.5), y, px, 1.0, colors, a))
        if self.sub and t >= PC_LETTER_START + 0.5:
            a = min(1.0, (t - PC_LETTER_START - 0.5) / 0.2) * (1.0 if t < end else max(0.0, 1 - (t - end) / 0.5))
            out.append(("text", self.sub, self.cx, self.ty + px * 0.9, px * 0.38, 1.0,
                        (MEDAL[0], (255, 140, 0)), a))

    def gone(self, now):
        return now - self.t0 >= self.duration

    def ops(self, now):
        """What to draw at `now`: a list of tuples, the first item the shape (back to front)."""
        t = now - self.t0
        if t < 0 or t >= self.duration:
            return []
        p, pal, out = self.power, self.palette, []
        # a PERFECT CLEAR: the screen dims first (then everything shines out of the dark)
        if self.pc and t < 1.3 and not self.lite:
            a = PC_DIM * min(1.0, t / 0.15) * (1.0 if t < 0.5 else max(0.0, 1 - (t - 0.5) / 0.8))
            out.append(("dim", a))
        # flashes: round the screen's edges, tinted; the big ones again, 1/3 s apart
        tints = (pal[0], MEDAL[0], pal[1])
        for i in range(self.flashes):
            u = t - i * FLASH_GAP_S
            if 0 <= u < FLASH_S:
                a = FLASH_ALPHA[p] * (1.3 if self.max else 1.0) * (0.8 ** i) * (1 - u / FLASH_S) ** 2
                c = tints[i]
                out.append(("flash", (int((255 + c[0]) / 2), int((255 + c[1]) / 2), int((255 + c[2]) / 2)), a))
        # spotlights sweeping up from below, their colours going round
        if self.pillars and t < PILLAR_S:
            a = 0.20 * min(1.0, t / 0.15) * (1 - t / PILLAR_S)
            for x, h0, rate in self.pillars:
                angle = math.sin(t * 2.4 * rate + h0 * 6.28) * 0.45
                out.append(("pillar", x, SCREEN_H + 10, 900, 70, angle, hue(h0 + t * 0.8), a))
        # light rays turning behind (the big ones)
        if p >= 3 and t < RAY_S and not self.lite:
            a = (0.30 if self.max else 0.24) * min(1.0, t / 0.1) * (1 - t / RAY_S)
            out.append(("rays", self.cx, self.cy - 40, 620, RAYS, t * RAY_SPIN * 2 * math.pi / RAYS,
                        hue(t * 0.6) if self.max else pal[1], a))
        # shock rings from the board's middle
        for i in range(0 if self.lite else min(5, p + 1)):   # (普通: no ring over the board)
            u = (t - i * RING_GAP_S) / RING_S
            if 0 <= u < 1:
                r = 24 + (300 + 60 * p) * _ease_out(u) * (0.6 if self.lite else 1.0)
                c = hue(i / 5 + t) if self.max else pal[i % len(pal)]
                out.append(("ring", self.cx, self.cy, r, (2 + 8 * (1 - u)) if self.lite else (3 + 16 * (1 - u)), c,
                            (0.55 if self.lite else 0.85) * (1 - u)))
        # blocks and sparkles flying out
        for vx, vy, life, size, ci, star, rot0, spin in self.parts:
            if t >= life:
                continue
            k = (1 - math.exp(-3.2 * t)) / 3.2
            x = self.cx + vx * k
            y = self.oy + vy * k + 0.5 * GRAVITY * 0.55 * t * t
            a = 1.0 - (t / life) ** 2
            out.append(("star" if star else "block", x, y, size * (1.3 if star else 1.0), rot0 + spin * t,
                        pal[ci], a))
        # gold medals: a fountain from below the board
        for x0, vx, vy, delay, size, spin, phase in self.medals:
            u = t - delay
            if u < 0:
                continue
            y = SCREEN_H + 20 + vy * u + 0.5 * MEDAL_GRAVITY * u * u
            if y > SCREEN_H + 40 and u > 0.2:
                continue
            out.append(("medal", x0 + vx * u, y, size, abs(math.cos(phase + spin * u)), min(1.0, (MEDAL_S - t) / 0.4)))
        # confetti over the whole screen (a PC)
        for x0, y0, fall, sway_hz, sway, ci, rot0, spin, size in self.confetti:
            y = y0 + fall * t
            if y > SCREEN_H + 20:
                continue
            x = x0 + sway * math.sin(sway_hz * 2 * math.pi * t + x0)
            a = min(1.0, (CONFETTI_S - t) / 0.6)
            cp = self.confetti_pal
            c = hue(ci / len(cp) + t * 0.5) if self.max else cp[ci]
            out.append(("confetti", x, y, size, rot0 + spin * t, c, a))
        if self.pc:
            self._pc_letters(t, out)
        # the clear's name, slammed in, shaking, then gone
        if not self.pc and t < TEXT_IN_S + self.hold + TEXT_OUT_S:
            if t < TEXT_IN_S:
                scale = (1.6 - 0.6 * _ease_back(t / TEXT_IN_S)) if self.lite else (2.6 - 1.6 * _ease_back(t / TEXT_IN_S))
                a = min(1.0, t / (TEXT_IN_S * 0.5))
            else:
                scale = 1.0 + (0 if self.lite else 0.05) * math.sin((t - TEXT_IN_S) * 9) * \
                    max(0.0, 1 - (t - TEXT_IN_S) / 0.6)
                a = 1.0 - max(0.0, (t - TEXT_IN_S - self.hold) / TEXT_OUT_S)
            amp = 0 if self.lite else 4 * p * max(0.0, 1 - t / 0.45)
            dx = amp * math.sin(t * 61 + self.shake[0])
            dy = amp * math.sin(t * 53 + self.shake[1])
            px = TEXT_PX * (1.15 if self.pc else 1.0) * (0.85 if len(self.title) > 14 else 1.0) * self.text_k * \
                (LITE_TEXT_K if self.lite else 1.0)
            # (rainbow at "max": the colours going round)
            step = round(t * 0.9 * HUE_STEPS) / HUE_STEPS   # (in steps: each colour's text picture is kept)
            colors = (hue(step), hue(step + 0.33)) if self.max else (pal[0], pal[1])
            out.append(("text", self.title, self.cx + dx, self.ty + dy, px, scale, colors, a))
            subs = [x for x in (self.sub, f"{self.chain}連チャン" if self.chain >= 2 and not self.lite else "") if x]
            if subs and t >= TEXT_IN_S * 0.6:
                out.append(("text", "   ".join(subs), self.cx - dx * 0.5, self.ty + px * 0.95, px * 0.42,
                            1.0, colors, a))
        # the cut-in band across the screen
        if self.band and BAND_IN <= t < BAND_OUT:
            if t < BAND_STOP:
                slide = (1 - _ease_out((t - BAND_IN) / (BAND_STOP - BAND_IN))) * SCREEN_W
            elif t < BAND_HOLD:
                slide = -40 * (t - BAND_STOP) / (BAND_HOLD - BAND_STOP)   # (creeping: alive)
            else:
                slide = -40 - (SCREEN_W + 200) * ((t - BAND_HOLD) / (BAND_OUT - BAND_HOLD)) ** 2
            pop = 1.0 + 0.12 * max(0.0, 1 - abs(t - BAND_STOP) / 0.12)
            out.append(("band", slide, BAND_Y, BAND_H, self.band, BAND_PX, t * 600,
                        hue(round(t * 1.2 * HUE_STEPS) / HUE_STEPS), pop))
        # the slot reels, over the board: spinning, stopping one by one on the triple
        if self.reels is not None and REEL_IN <= t < REEL_END:
            positions = []
            for i in range(3):
                stop = REEL_STOP + REEL_GAP * i
                if t < stop:
                    pos = self.reels - REEL_SPEED * (stop - t)        # (counting down to it)
                else:
                    u = t - stop
                    pos = self.reels + 0.18 * math.sin(u * 30) * math.exp(-u * 9)   # (a little bounce)
                positions.append(pos)
            done = t - (REEL_STOP + 2 * REEL_GAP)
            glow = 0.0 if done < 0 else 0.5 + 0.5 * math.sin(done * 14)
            a = min(1.0, (t - REEL_IN) / 0.12) * min(1.0, (REEL_END - t) / 0.3)
            out.append(("reels", self.cx, self.cy - 158, positions, glow, a))
        # "+N": the lines sent pop up, fly over to the other board, land there
        if self.lines:
            u = t - ATTACK_UP
            text = f"+{self.lines}"
            if t < ATTACK_UP:
                out.append(("attack", text, self.cx, self.ay, 0.4 + 1.0 * _ease_back(t / ATTACK_UP), 1.0))
            elif u < ATTACK_FLY:
                k = (u / ATTACK_FLY) ** 1.6   # (speeding up as it goes)
                x = self.cx + (self.target[0] - self.cx) * k
                y = self.ay + (self.target[1] - self.ay) * k - 160 * math.sin(math.pi * k)
                out.append(("attack", text, x, y, 1.4 - 0.4 * k, 1.0))
                for j in range(1, 6):   # a trail of sparkles
                    kj = max(0.0, k - 0.05 * j)
                    tx = self.cx + (self.target[0] - self.cx) * kj
                    ty = self.ay + (self.target[1] - self.ay) * kj - 160 * math.sin(math.pi * kj)
                    out.append(("spark", tx, ty, 9 - j, MEDAL[0], 0.8 - 0.13 * j))
            elif u < ATTACK_FLY + ATTACK_HIT:
                v = (u - ATTACK_FLY) / ATTACK_HIT
                out.append(("attack", text, self.target[0], self.target[1], 1.0 + 0.6 * v, 1 - v))
                out.append(("ring", self.target[0], self.target[1], 20 + 120 * _ease_out(v), 10 * (1 - v) + 2,
                            MEDAL[0], 0.9 * (1 - v)))
        # a PERFECT CLEAR: fireworks all over
        for launch, x, peak, h0, sparks in self.rockets:
            u = t - launch
            if u < 0:
                continue
            if u < ROCKET_RISE:
                y = SCREEN_H + 10 - (SCREEN_H + 10 - peak) * _ease_out(u / ROCKET_RISE)
                out.append(("spark", x, y, 6, (255, 240, 200), 1.0))
                for j in range(1, 5):
                    out.append(("spark", x, y + 14 * j, 5 - j, (255, 200, 120), 0.7 - 0.15 * j))
            else:
                v = u - ROCKET_RISE
                if v >= SPARK_LIFE:
                    continue
                a = 1.0 - (v / SPARK_LIFE) ** 2
                c = hue(h0)
                k = (1 - math.exp(-2.5 * v)) / 2.5
                for angle, speed in sparks:
                    out.append(("spark", x + math.cos(angle) * speed * k,
                                peak + math.sin(angle) * speed * k + 0.5 * SPARK_GRAVITY * v * v, SPARK_PX, c, a))
        # the LED frame chasing round the screen's edge
        if self.frame and t < FRAME_S + 0.2 * p:
            end = FRAME_S + 0.2 * p
            a = min(1.0, t / 0.08) * min(1.0, (end - t) / 0.4)
            out.append(("frame", t * 1.6 * (1 + 0.5 * self.tier), a, self.frame_px))
        return out


# --- Qt ---------------------------------------------------------------------

SOUNDS_DIR = Path(__file__).resolve().parent.parent / "assets" / "dopamine_sounds"
SOUND_COPIES = 3     # each sound can be playing this many times at once (bursts close together)
PITCHED_COPIES = 2   # (each pitch of one: fewer, there are many)
# The sounds that go up with each BtB ship at their base pitch only (*_p0.wav);
# the 14 higher ones are made from it on first use, by resampling, and kept
# in %LOCALAPPDATA%/PPTetrics/sounds (user: a lighter download — 56 files, ~7 MB)
PITCHED = ("kyuin", "fanfare", "chime", "glint")
PITCH_SCALE = (0, 2, 4, 5, 7, 9, 11, 12, 14, 16, 17, 19, 21, 23, 24)   # semitones (make_dopamine_sounds.SCALE)


def pitched_file(name, step):
    """The sound a step up the scale: shipped, or made from its base and kept."""
    import os
    shipped = SOUNDS_DIR / f"{name}_p{step}.wav"
    if shipped.exists():
        return shipped
    out = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "PPTetrics" / "sounds" / f"{name}_p{step}.wav"
    if not out.exists():
        import wave
        import numpy as np
        with wave.open(str(SOUNDS_DIR / f"{name}_p0.wav")) as w:
            rate = w.getframerate()
            x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(float)
        k = 2 ** (PITCH_SCALE[step] / 12)   # (faster: higher, and a little shorter)
        y = np.interp(np.arange(0, len(x) - 1, k), np.arange(len(x)), x)
        out.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(out), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(np.clip(y, -32768, 32767).astype("<i2").tobytes())
    return out


# --- the announcer (display.challenge_announcer) ------------------------------
# The clear's name said out loud (user: "T-Spin Double!" read out, in English,
# lively). Recorded ahead with Kokoro (tools/sound/make_announcer.py; the
# Kokoro-82M model, Apache-2.0) in the two voices the user picked —
# assets/announcer/<voice>/ — cut tight and loud, so a line starts at once
# (Windows' own voice lagged and was quiet). Like the sounds, played by the
# app: the player hears it, OBS's desktop audio takes it to the stream. A new
# line cuts the one before short (a TETRIS found to be a PC: "Perfect Clear!").
ANNOUNCER_DIR = Path(__file__).resolve().parent.parent / "assets" / "announcer"
ANNOUNCER_VOICES = {"heart": "af_heart", "adam": "am_adam"}
SAY = {"T-SPIN SINGLE": "T-Spin Single", "T-SPIN DOUBLE": "T-Spin Double", "T-SPIN TRIPLE": "T-Spin Triple",
       "T-SPIN MINI": "T-Spin Mini", "T-SPIN MINI DOUBLE": "T-Spin Mini Double", "TETRIS": "Tetris",
       "PERFECT CLEAR": "Perfect Clear"}
ANNOUNCE_COPIES = 2
# above 100% (user: louder still): a louder copy of each line, squeezed harder
# (made from the shipped one on first use, kept in %LOCALAPPDATA%/PPTetrics)
VOLUME_MAX = 200
LOUD_DRIVE = 4.0


def louder(samples):
    """A line squeezed harder (tanh): the same peak, much more loudness."""
    import numpy as np
    x = np.asarray(samples, dtype=float)
    peak = np.abs(x).max() or 1.0
    y = np.tanh(LOUD_DRIVE * x / peak) / np.tanh(LOUD_DRIVE)
    return y * 0.97


def _loud_file(path):
    """The louder copy of a recording (made once)."""
    import os
    import wave
    import numpy as np
    out = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "PPTetrics" / "announcer_loud" / \
        path.parent.name / path.name
    if not out.exists():
        with wave.open(str(path)) as w:
            rate = w.getframerate()
            x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(float) / 32768
        out.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(out), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes((louder(x) * 32767).astype("<i2").tobytes())
    return out


def play_level(volume):
    """(which recording, QSoundEffect volume) for a volume 0 .. VOLUME_MAX:
    up to 100 the line as it is; above, its louder copy (~twice as loud)."""
    v = max(0, min(VOLUME_MAX, int(volume)))
    if v <= 100:
        return "plain", v / 100
    return "loud", 0.5 + 0.5 * (v - 100) / (VOLUME_MAX - 100)


def phrase(burst):
    """What the announcer says for a burst: "Back to Back, T-Spin Double!", "Perfect Clear!"."""
    name = SAY.get(burst.title, burst.title)
    if burst.btb and not burst.pc:
        name = "Back to Back, " + name
    return name + "!"


def phrases():
    """Every line the announcer can say (tools/sound/make_announcer.py makes the same)."""
    out = []
    for title in SAY:
        for btb in (False, True):
            if btb and title == "PERFECT CLEAR":
                continue
            fake = type("B", (), {"title": title, "btb": btb, "pc": title == "PERFECT CLEAR"})()
            out.append(phrase(fake))
    return out


def line_file(voice, text):
    """A line's recording (tools/sound/make_announcer.py slug)."""
    import re
    folder = ANNOUNCER_VOICES.get(voice, ANNOUNCER_VOICES["heart"])
    return ANNOUNCER_DIR / folder / (re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") + ".wav")


class Announcer:
    """Plays the announcer's recorded lines (loaded ahead: no lag)."""

    def __init__(self, parent=None):
        self.parent = parent
        self.voice = None
        self._effects = {}     # line -> [QSoundEffect] (the set in use)
        self._sets = {}        # (voice, plain / loud) -> such a set, all kept
        self._playing = []

    def preload(self, voice="heart", kind="plain"):
        if (voice, kind) == self.voice and self._effects:
            return
        from PyQt6 import QtCore, QtMultimedia
        # every set made is kept (never dropped: a QSoundEffect destroyed while
        # still loading took the process down) — switching back is instant too
        self.voice = (voice, kind)
        if self.voice in self._sets:
            self._effects = self._sets[self.voice]
            return
        self._effects = self._sets[self.voice] = {}
        for text in phrases():
            path = line_file(voice, text)
            if not path.exists():
                continue
            if kind == "loud":
                path = _loud_file(path)
            copies = []
            for _ in range(ANNOUNCE_COPIES):
                e = QtMultimedia.QSoundEffect(self.parent)
                e.setSource(QtCore.QUrl.fromLocalFile(str(path)))
                copies.append(e)
            self._effects[text] = copies

    def say(self, burst, volume, voice="heart"):
        if volume <= 0:
            return
        kind, level = play_level(volume)
        try:
            self.preload(voice, kind)
        except Exception:   # (no sound here: just quiet)
            return
        for e in self._playing:   # (cut short the one still talking)
            e.stop()
        self._playing = []
        copies = self._effects.get(phrase(burst))
        if not copies:
            return
        effect = copies[0] if not copies[0].isPlaying() else copies[-1]
        effect.setVolume(max(0.0, min(1.0, level)))
        effect.play()
        self._playing = [effect]


_SHARED = {}


def shared_sounds():
    """The one Sounds for the app, never thrown away: a QSoundEffect destroyed
    while it was still loading took the whole process down (a HUD window
    made and dropped in the tests, with the effects on in the settings)."""
    if "sounds" not in _SHARED:
        _SHARED["sounds"] = Sounds(None)
    return _SHARED["sounds"]


def shared_announcer():
    """The one Announcer for the app (see shared_sounds)."""
    if "announcer" not in _SHARED:
        _SHARED["announcer"] = Announcer(None)
    return _SHARED["announcer"]


class Sounds:
    """Plays a burst's sounds, each at its time (QSoundEffect: quick to start)."""

    def __init__(self, parent=None):
        self.parent = parent
        self._effects = None
        self._next = {}

    def _load(self):
        from PyQt6 import QtCore, QtMultimedia
        self._effects = {}
        paths = [f for f in sorted(SOUNDS_DIR.glob("*.wav")) if "_p" not in f.stem]
        paths += [pitched_file(name, step) for name in PITCHED for step in range(len(PITCH_SCALE))]
        for path in paths:
            copies = []
            for _ in range(PITCHED_COPIES if "_p" in path.stem else SOUND_COPIES):
                e = QtMultimedia.QSoundEffect(self.parent)
                e.setSource(QtCore.QUrl.fromLocalFile(str(path)))
                copies.append(e)
            self._effects[path.stem] = copies

    def preload(self):
        """Read the sounds now (they load in the background: the first burst isn't quiet)."""
        if self._effects is None:
            try:
                self._load()
            except Exception:   # (no sound device, no multimedia: just quiet)
                self._effects = {}

    def play(self, burst, volume):
        """volume: 0-100 (0: none)."""
        if volume <= 0:
            return
        from PyQt6 import QtCore
        self.preload()
        for at, name in burst.sounds:
            copies = self._effects.get(name)
            if not copies:
                continue
            i = self._next.get(name, 0)
            self._next[name] = (i + 1) % len(copies)
            effect = copies[i]
            effect.setVolume(max(0.0, min(1.0, volume / 100)))
            QtCore.QTimer.singleShot(int(at * 1000), effect.play)

def _qc(c, a=1.0):
    from PyQt6 import QtGui
    return QtGui.QColor(int(c[0]), int(c[1]), int(c[2]), max(0, min(255, int(255 * a))))


_TEXT_IMAGES = {}
TEXT_CACHE = 160
GLOW_SHRINK = 6      # the glow is drawn this many times smaller, then stretched (blurred) back


_TEXT_LAYERS = {}


def _text_layers(text, font, outline, outline_w, s):
    """A text's three layers, made once: the glow's shape (white, soft), the
    outline, the letters' shape (white) — colours go on after (_text_image),
    so the rainbow letters don't make the slow part again each colour."""
    from PyQt6 import QtCore, QtGui
    key = (text, font.family(), font.pixelSize(), outline, outline_w, round(s, 3))
    layers = _TEXT_LAYERS.get(key)
    if layers is not None:
        return layers
    path = QtGui.QPainterPath()
    path.addText(0, 0, font, text)
    box = path.boundingRect()
    pad = 12 * s + outline_w * s
    size = QtCore.QSize(max(1, int(box.width() + 2 * pad)), max(1, int(box.height() + 2 * pad)))
    fmt = QtGui.QImage.Format.Format_ARGB32_Premultiplied

    def blank(w, h):
        img = QtGui.QImage(w, h, fmt)
        img.fill(0)
        return img
    # the glow: the letters filled small, then stretched back up (a soft blur) —
    # wide strokes round the glyphs took 20+ ms each
    k = GLOW_SHRINK
    small = blank(max(1, size.width() // k), max(1, size.height() // k))
    sp = QtGui.QPainter(small)
    sp.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    sp.scale(1 / k, 1 / k)
    sp.translate(pad - box.left(), pad - box.top())
    sp.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 10 * s))
    sp.setBrush(QtGui.QColor(255, 255, 255))
    sp.drawPath(path)
    sp.end()
    glow = blank(size.width(), size.height())
    gp = QtGui.QPainter(glow)
    gp.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
    for grow, alpha in ((1.10, 0.45), (1.0, 0.75)):
        w, h = size.width() * grow, size.height() * grow
        gp.setOpacity(alpha)
        gp.drawImage(QtCore.QRectF((size.width() - w) / 2, (size.height() - h) / 2, w, h), small)
    gp.end()
    edge = blank(size.width(), size.height())
    ep = QtGui.QPainter(edge)
    ep.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    ep.translate(pad - box.left(), pad - box.top())
    ep.setPen(QtGui.QPen(_qc(outline), outline_w * s, QtCore.Qt.PenStyle.SolidLine,
                         QtCore.Qt.PenCapStyle.FlatCap, QtCore.Qt.PenJoinStyle.BevelJoin))
    ep.drawPath(path)
    ep.end()
    letters = blank(size.width(), size.height())
    lp = QtGui.QPainter(letters)
    lp.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    lp.translate(pad - box.left(), pad - box.top())
    lp.setPen(QtCore.Qt.PenStyle.NoPen)
    lp.setBrush(QtGui.QColor(255, 255, 255))
    lp.drawPath(path)
    lp.end()
    top, bottom = pad, pad + box.height()
    layers = (glow, edge, letters, top, bottom)
    if len(_TEXT_LAYERS) >= TEXT_CACHE:
        _TEXT_LAYERS.pop(next(iter(_TEXT_LAYERS)))
    _TEXT_LAYERS[key] = layers
    return layers


def _tinted(mask, brush):
    """The mask's shape, coloured with brush."""
    from PyQt6 import QtGui
    img = mask.copy()
    p = QtGui.QPainter(img)
    p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceIn)
    p.fillRect(img.rect(), brush)
    p.end()
    return img


def _text_image(text, font, fill, glow, outline, outline_w, s):
    """The text with its glow, outline and fill, as a picture (kept per colour)."""
    from PyQt6 import QtGui
    key = (text, font.family(), font.pixelSize(), fill, glow, outline, outline_w, round(s, 3))
    img = _TEXT_IMAGES.get(key)
    if img is not None:
        return img
    glow_mask, edge, letters, top, bottom = _text_layers(text, font, outline, outline_w, s)
    img = _tinted(glow_mask, _qc(glow))
    grad = QtGui.QLinearGradient(0, top, 0, bottom)
    for stop, c in fill:
        grad.setColorAt(stop, _qc(c))
    p = QtGui.QPainter(img)
    p.drawImage(0, 0, edge)
    p.drawImage(0, 0, _tinted(letters, QtGui.QBrush(grad)))
    p.end()
    if len(_TEXT_IMAGES) >= TEXT_CACHE:
        _TEXT_IMAGES.pop(next(iter(_TEXT_IMAGES)))
    _TEXT_IMAGES[key] = img
    return img


def warm(s):
    """Make the texts' slow layers ahead (turned on: the first burst doesn't stall)."""
    from PyQt6 import QtGui
    for title, _, _ in list(KINDS.values()) + [PC]:
        _outlined_font_layers(title, TEXT_PX * (1.15 if title == PC[0] else 1.0) * (0.85 if len(title) > 14 else 1.0), s)
    for word in [w for w in BAND_WORDS if w] + [BAND_PC]:
        font = _band_font(BAND_PX, s)
        _text_layers(word, font, (90, 0, 0), 6, s)
    for sym in REEL_SYMBOLS:
        _text_layers(sym, _title_font(REEL_PX, s), (20, 20, 20), 3, s)
    for n in range(1, 13):
        _text_layers(f"+{n}", _title_font(ATTACK_PX, s), (60, 20, 0), 4, s)
    # the Japanese in the line under the name (〇連チャン): the font for it is
    # looked up the first time (~150 ms) — done here, not at a burst
    _text_layers("BACK-TO-BACK x1   2 REN   2連チャン", _title_font(TEXT_PX * 0.42, s), (20, 10, 40), 4, s)


def _title_font(px, s):
    from PyQt6 import QtGui
    font = QtGui.QFont("Arial Black")
    font.setPixelSize(max(4, int(px * s)))
    font.setWeight(QtGui.QFont.Weight.Black)
    font.setItalic(True)
    return font


def _band_font(px, s):
    from PyQt6 import QtGui
    font = QtGui.QFont("Yu Gothic UI")
    font.setPixelSize(max(4, int(px * s)))
    font.setWeight(QtGui.QFont.Weight.Black)
    font.setItalic(True)
    return font


def _outlined_font_layers(title, px, s):
    _text_layers(title, _title_font(px, s), (20, 10, 40), 4, s)


def _outlined_text(p, text, font, x, y, scale, fill, glow, outline, outline_w, s, width):
    """The text's picture, centred on (x, y) px, scaled (kept on the screen)."""
    from PyQt6 import QtCore
    img = _text_image(text, font, tuple(fill), tuple(glow), tuple(outline), outline_w, s)
    w, h = img.width() * scale, img.height() * scale
    half = w / 2
    cx = min(max(x, half), width - half) if width > 2 * half else x
    p.drawImage(QtCore.QRectF(cx - w / 2, y - h / 2, w, h), img)


def paint(p, burst, s, now, width=None, height=None):
    """Draw one burst with a QPainter `p`, `s` px per reference px."""
    from PyQt6 import QtCore, QtGui
    W, H = width or SCREEN_W * s, height or SCREEN_H * s
    smooth = QtGui.QPainter.RenderHint.Antialiasing
    p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
    for op in burst.ops(now):
        kind = op[0]
        # (antialiasing only where an edge shows: the rings; the soft shapes and
        # the many small pieces without it — a frame took ~30 ms with it)
        p.setRenderHint(smooth, kind == "ring")
        if kind == "flash":   # round the edges only: the middle (the game) stays clear
            _, c, a = op
            grad = QtGui.QRadialGradient(W / 2, H / 2, math.hypot(W, H) / 2)
            grad.setColorAt(0, _qc(c, 0))
            grad.setColorAt(FLASH_CLEAR, _qc(c, 0))
            grad.setColorAt(1, _qc(c, a))
            p.fillRect(QtCore.QRectF(0, 0, W, H), QtGui.QBrush(grad))
        elif kind == "dim":
            p.fillRect(QtCore.QRectF(0, 0, W, H), QtGui.QColor(0, 0, 0, int(255 * op[1])))
        elif kind == "spark":
            _, x, y, size, c, a = op
            if a > 0:
                h = max(1.0, size * s / 2)
                p.fillRect(QtCore.QRectF(x * s - h, y * s - h, 2 * h, 2 * h), _qc(c, a))
        elif kind == "attack":
            _, text, x, y, scale, a = op
            if a > 0:
                p.save()
                p.setOpacity(max(0.0, min(1.0, a)))
                _outlined_text(p, text, _title_font(ATTACK_PX, s), x * s, y * s, scale,
                               ((0, (255, 255, 255)), (0.5, MEDAL[0]), (1, (255, 120, 0))), (255, 160, 0),
                               (60, 20, 0), 4, s, W)
                p.restore()
        elif kind == "reels":
            _, x, y, positions, glow, a = op
            _paint_reels(p, x, y, positions, glow, a, s)
        elif kind == "pillar":
            _, x, y, length, w, angle, c, a = op
            p.save()
            p.translate(x * s, y * s)
            p.rotate(math.degrees(angle))
            grad = QtGui.QLinearGradient(0, 0, 0, -length * s)
            grad.setColorAt(0, _qc(c, a))
            grad.setColorAt(1, _qc(c, 0))
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QBrush(grad))
            path = QtGui.QPainterPath(QtCore.QPointF(-w * s * 0.15, 0))
            path.lineTo(w * s * 0.15, 0)
            path.lineTo(w * s, -length * s)
            path.lineTo(-w * s, -length * s)
            path.closeSubpath()
            p.drawPath(path)
            p.restore()
        elif kind == "rays":
            _, x, y, r, n, turn, c, a = op
            p.save()
            p.translate(x * s, y * s)
            p.rotate(math.degrees(turn))
            grad = QtGui.QRadialGradient(0, 0, r * s)
            grad.setColorAt(0, _qc(c, a))
            grad.setColorAt(1, _qc(c, 0))
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QBrush(grad))
            half = math.pi / n / 2
            path = QtGui.QPainterPath()
            for i in range(n):
                a0 = 2 * math.pi * i / n
                path.moveTo(0, 0)
                path.lineTo(math.cos(a0 - half) * r * s, math.sin(a0 - half) * r * s)
                path.lineTo(math.cos(a0 + half) * r * s, math.sin(a0 + half) * r * s)
                path.closeSubpath()
            p.drawPath(path)
            p.restore()
        elif kind == "ring":
            _, x, y, r, w, c, a = op
            p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            p.setPen(QtGui.QPen(_qc(c, a), w * s))
            p.drawEllipse(QtCore.QPointF(x * s, y * s), r * s, r * s)
        elif kind in ("block", "confetti"):
            _, x, y, size, rot, c, a = op
            p.save()
            p.translate(x * s, y * s)
            p.rotate(rot)
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.setBrush(_qc(c, a))
            if kind == "block":
                h = size * s / 2
                p.drawRect(QtCore.QRectF(-h, -h, 2 * h, 2 * h))
                p.setBrush(_qc((255, 255, 255), 110 / 255 * a))
                p.drawRect(QtCore.QRectF(-h, -h, 2 * h, h * 0.6))
            else:
                p.drawRect(QtCore.QRectF(-size * s / 2, -size * s / 4, size * s, size * s / 2))
            p.restore()
        elif kind == "star":
            _, x, y, size, rot, c, a = op
            p.save()
            p.translate(x * s, y * s)
            p.rotate(rot)
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.setBrush(_qc((255, 255, 255), a))
            r, w = size * s, size * s * 0.22
            path = QtGui.QPainterPath()
            for px_, py_ in ((0, -r), (w, -w), (r, 0), (w, w), (0, r), (-w, w), (-r, 0), (-w, -w)):
                if path.elementCount() == 0:
                    path.moveTo(px_, py_)
                else:
                    path.lineTo(px_, py_)
            path.closeSubpath()
            p.drawPath(path)
            p.setBrush(_qc(c, 200 / 255 * a))
            p.drawEllipse(QtCore.QPointF(0, 0), w, w)
            p.restore()
        elif kind == "medal":
            _, x, y, size, turn, a = op
            p.save()
            p.translate(x * s, y * s)
            rx, ry = max(0.15, turn) * size * s, size * s
            p.setPen(QtGui.QPen(_qc(MEDAL[2], a), max(1.0, 1.6 * s)))
            p.setBrush(_qc(MEDAL[0], a))
            p.drawEllipse(QtCore.QPointF(0, 0), rx, ry)
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.setBrush(_qc(MEDAL[1], a))
            p.drawEllipse(QtCore.QPointF(-rx * 0.3, -ry * 0.35), rx * 0.35, ry * 0.3)
            p.restore()
        elif kind == "text":
            _, text, x, y, px, scale, colors, a = op
            if a <= 0:
                continue
            font = _title_font(px, s)
            p.save()
            p.setOpacity(max(0.0, min(1.0, a)))
            _outlined_text(p, text, font, x * s, y * s, scale,
                           ((0, (255, 255, 255)), (0.45, colors[0]), (1, colors[1])), colors[0], (20, 10, 40), 4,
                           s, W)
            p.restore()
        elif kind == "band":
            _, slide, y, h, word, px, stripe, glow, pop = op
            p.save()
            p.translate(slide * s, 0)
            top, bottom, skew = (y - h / 2) * s, (y + h / 2) * s, 40 * s
            band = QtGui.QPainterPath(QtCore.QPointF(-60 * s + skew, top))
            band.lineTo(W + 60 * s + skew, top)
            band.lineTo(W + 60 * s - skew, bottom)
            band.lineTo(-60 * s - skew, bottom)
            band.closeSubpath()
            grad = QtGui.QLinearGradient(0, top, 0, bottom)
            grad.setColorAt(0, QtGui.QColor(40, 0, 10, 235))
            grad.setColorAt(0.5, QtGui.QColor(150, 0, 30, 235))
            grad.setColorAt(1, QtGui.QColor(40, 0, 10, 235))
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QBrush(grad))
            p.drawPath(band)
            p.setClipPath(band)
            p.setBrush(QtGui.QColor(255, 255, 255, 28))   # stripes running along it
            step = 46 * s
            off = (stripe * s) % step
            x = -2 * step + off - 60 * s
            while x < W + 120 * s:
                stripe_path = QtGui.QPainterPath(QtCore.QPointF(x, top))
                stripe_path.lineTo(x + step * 0.5, top)
                stripe_path.lineTo(x + step * 0.5 - 2 * skew, bottom)
                stripe_path.lineTo(x - 2 * skew, bottom)
                stripe_path.closeSubpath()
                p.drawPath(stripe_path)
                x += step
            p.setClipping(False)
            p.setPen(QtGui.QPen(_qc(MEDAL[0]), 5 * s))   # gold edges
            p.drawLine(QtCore.QPointF(-60 * s + skew, top), QtCore.QPointF(W + 60 * s + skew, top))
            p.drawLine(QtCore.QPointF(-60 * s - skew, bottom), QtCore.QPointF(W + 60 * s - skew, bottom))
            font = _band_font(px, s)
            _outlined_text(p, word, font, W / 2, y * s, pop,
                           ((0, (255, 255, 255)), (0.35, MEDAL[0]), (0.7, (255, 140, 0)), (1, (255, 60, 0))),
                           glow, (90, 0, 0), 6, s, W + 1e9)
            p.restore()
        elif kind == "frame":
            _, phase, a, px = op
            n = FRAME_SEGMENTS
            per = 2 * (W + H)
            w = px * s
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            for i in range(n):
                p.setBrush(_qc(hue(i / n + phase), a * (0.55 + 0.45 * (math.sin(i * 1.7 + phase * 12) > 0))))
                d0, d1 = per * i / n, per * (i + 0.8) / n
                for rect in _frame_rects(d0, d1, W, H, w):
                    p.drawRect(rect)


def _paint_reels(p, x, y, positions, glow, a, s):
    """Three slot reels side by side, centred on (x, y) reference px."""
    from PyQt6 import QtCore, QtGui
    n = len(REEL_SYMBOLS)
    total = 3 * REEL_W + 2 * 8
    left = min(max(x - total / 2, 8), SCREEN_W - 8 - total)
    p.save()
    p.setOpacity(max(0.0, min(1.0, a)))
    # the cabinet
    cab = QtCore.QRectF((left - 10) * s, (y - REEL_H / 2 - 10) * s, (total + 20) * s, (REEL_H + 20) * s)
    p.setPen(QtGui.QPen(_qc(MEDAL[0]), 4 * s))
    p.setBrush(QtGui.QColor(30, 0, 10, 235))
    p.drawRoundedRect(cab, 10 * s, 10 * s)
    for i, pos in enumerate(positions):
        box = QtCore.QRectF((left + i * (REEL_W + 8)) * s, (y - REEL_H / 2) * s, REEL_W * s, REEL_H * s)
        grad = QtGui.QLinearGradient(0, box.top(), 0, box.bottom())
        grad.setColorAt(0, QtGui.QColor(150, 150, 150))
        grad.setColorAt(0.5, QtGui.QColor(255, 255, 255))
        grad.setColorAt(1, QtGui.QColor(150, 150, 150))
        p.setPen(QtCore.Qt.PenStyle.NoPen)
        p.setBrush(QtGui.QBrush(grad))
        p.drawRect(box)
        p.save()
        p.setClipRect(box)
        base = math.floor(pos)
        frac = pos - base
        for k in (-1, 0, 1):
            sym = REEL_SYMBOLS[int(base + k) % n]
            cy = (y + (k - frac) * REEL_H * 0.9) * s
            color = (220, 0, 30) if sym == "7" else ((40, 40, 200) if sym == "BAR" else (230, 150, 0))
            _outlined_text(p, sym, _title_font(REEL_PX, s), box.center().x(), cy, REEL_SCALE.get(sym, 1.0),
                           ((0, color), (1, color)), (255, 255, 255), (20, 20, 20), 3, s, 1e9)
        p.restore()
    if glow > 0:   # the win: the cabinet's lights blinking
        p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        p.setPen(QtGui.QPen(_qc(MEDAL[1], glow), 7 * s))
        p.drawRoundedRect(cab.adjusted(-4 * s, -4 * s, 4 * s, 4 * s), 13 * s, 13 * s)
    p.restore()


def _frame_rects(d0, d1, W, H, w):
    """The pieces of the screen's edge between d0 and d1 px along it (clockwise from the top left)."""
    from PyQt6 import QtCore
    out = []
    edges = ((0, W, lambda a, b: QtCore.QRectF(a, 0, b - a, w)),
             (W, W + H, lambda a, b: QtCore.QRectF(W - w, a - W, w, b - a)),
             (W + H, 2 * W + H, lambda a, b: QtCore.QRectF(2 * W + H - b, H - w, b - a, w)),
             (2 * W + H, 2 * (W + H), lambda a, b: QtCore.QRectF(0, 2 * (W + H) - b, w, b - a)))
    for e0, e1, make in edges:
        a, b = max(d0, e0), min(d1, e1)
        if a < b:
            out.append(make(a, b))
    return out
