"""diag_summary.py: the last few matches in server.log, cut down to a short text.

For "the numbers looked wrong" reports from users who can't send a file (an X
DM takes text only, 10,000 characters): the tray menu copies this to the
clipboard, and it's pasted as it is. Per match and per side: what was counted,
the banners that were let go because no clear flash came before them, the
flashes dismissed, and the best T-SPIN match scores, which together show where
a side's clears were missed. No player names (they're in server.log, not here).
"""
import re
from collections import Counter
from pathlib import Path

MAX_MATCHES = 5
MAX_CHARS = 9000      # an X DM holds 10,000

_STAMP = re.compile(r"^(\d{4})-(\d\d)-(\d\d) (\d\d:\d\d:\d\d),\d+ \w+ (.*)$")
_EVENT = re.compile(r"^\[(left|right)\] t=[\d.]+ (\w+) lines=(\d+) \((.*?)\) ren_source=(\w+)")
_IGNORED = re.compile(r"^\[(left|right)\] t=[\d.]+ (\w+) banner ignored")
_DISMISSED = re.compile(r"^\[(left|right)\] flash at t=[\d.]+ dismissed")
_PC_IGNORED = re.compile(r"^\[(left|right)\] PERFECT CLEAR banner at t=[\d.]+ ignored")
_NO_LINE = re.compile(r"^\[(left|right)\] t=[\d.]+ T-SPIN( Mini)? \(no line\)")
_PEAK = re.compile(r"^\[debug tspin peak (left|right)\] (\{.*\})")
_PEAK_SCORE = re.compile(r"'(tspin_\w+)': \(([\d.]+),")
_UNCLASSIFIED = re.compile(r"^\[line_clear_detector\] unclassified delta=")
_START = re.compile(r"^resetting match state \((.*?)\)")
_END = re.compile(r"^match concluded \((.*?)\)")
_BLACK = re.compile(r"^screen went black")
_SOURCE = re.compile(r"^reading the game from (.*)$")
_SCALE = re.compile(r"^capture profile changed")
_HIDDEN = re.compile(r"^match screen not visible \((.*?)\)")

KIND_SHORT = {"clear_1": "1", "clear_2": "2", "clear_3": "3", "clear_4": "4",
              "tspin_single": "TSS", "tspin_double": "TSD", "tspin_triple": "TST",
              "tspin_mini": "TSM", "tspin_mini_single": "TSMS", "tspin_mini_double": "TSMD"}
ORDER = list(KIND_SHORT)


def _short(kind):
    return KIND_SHORT.get(kind, kind)


def _counts(counter):
    keys = sorted(counter, key=lambda k: (ORDER.index(k) if k in ORDER else 99, k))
    return " ".join(f"{_short(k)}x{counter[k]}" for k in keys) or "-"


class _Side:
    def __init__(self):
        self.kinds = Counter()
        self.sources = Counter()
        self.lines = 0
        self.pc = 0
        self.ignored = Counter()
        self.pc_ignored = 0
        self.dismissed = 0
        self.no_line = 0
        self.peak = {}

    def text(self):
        peak = " ".join(f"{_short(k)}{v:.2f}" for k, v in sorted(self.peak.items(), key=lambda kv: ORDER.index(kv[0])
                                                                   if kv[0] in ORDER else 99))
        src = " ".join(f"{k.replace('flash_', 'f_')}{v}" for k, v in sorted(self.sources.items()))
        return (f"count {_counts(self.kinds)} (lines {self.lines}{', PC' + str(self.pc) if self.pc else ''})"
                f" | src {src or '-'}"
                f" | let go {_counts(self.ignored)}{', PC' + str(self.pc_ignored) if self.pc_ignored else ''}"
                f" | dismissed {self.dismissed} | TS no line {self.no_line}"
                f" | TS peak {peak or '-'}")


class _Match:
    def __init__(self, when, how, source):
        self.when = when
        self.how = how
        self.source = source
        self.end = None
        self.last = when
        self.sides = {"left": _Side(), "right": _Side()}
        self.unclassified = 0
        self.rescaled = 0
        self.hidden = Counter()

    def empty(self):
        return not any(s.kinds or s.ignored or s.dismissed for s in self.sides.values())

    def text(self, n):
        start, last = self.when[1], self.last[1]
        secs = _seconds(last) - _seconds(start)
        if secs < 0:
            secs += 24 * 3600
        hidden = " ".join(f"{k}x{v}" for k, v in sorted(self.hidden.items()))
        head = (f"#{n} {self.when[0]} {start} {secs}s from:{self.source or '?'}"
                f" start:{self.how} end:{self.end or '-'}"
                + (f" unclassified:{self.unclassified}" if self.unclassified else "")
                + (f" rescaled:{self.rescaled}" if self.rescaled else "")
                + (f" hidden:{hidden}" if hidden else ""))
        return "\n".join([head, " L " + self.sides["left"].text(), " R " + self.sides["right"].text()])


def _seconds(hms):
    h, m, s = (int(x) for x in hms.split(":"))
    return h * 3600 + m * 60 + s


def matches(lines):
    """The matches in these log lines (oldest first)."""
    found, cur, source = [], None, None
    for raw in lines:
        m = _STAMP.match(raw.rstrip("\n"))
        if not m:
            continue
        when, msg = (f"{m.group(2)}/{m.group(3)}", m.group(4)), m.group(5)
        s = _SOURCE.match(msg)
        if s:
            source = "camera" + s.group(1).split("camera", 1)[1] if "camera" in s.group(1) else "PC"
            source = source.replace(" ", "")
            continue
        s = _START.match(msg)
        if s:
            cur = _Match(when, s.group(1).split(" — ")[0][:40], source)
            found.append(cur)
            continue
        if cur is None:
            continue
        s = _END.match(msg)
        if s:
            if cur.end is None:
                cur.end, cur.last = s.group(1)[:30], when
            continue
        if _BLACK.match(msg):
            cur.end = cur.end or "black screen"
            continue
        if cur.end is not None:
            continue          # after the end: the result screen, not the match
        s = _EVENT.match(msg)
        if s:
            cur.last = when
            side = cur.sides[s.group(1)]
            side.kinds[s.group(2)] += 1
            side.lines += int(s.group(3))
            side.sources[s.group(5)] += 1
            if "PERFECT CLEAR" in s.group(4):
                side.pc += 1
            continue
        s = _IGNORED.match(msg)
        if s:
            cur.last = when
            cur.sides[s.group(1)].ignored[s.group(2)] += 1
            continue
        s = _PC_IGNORED.match(msg)
        if s:
            cur.sides[s.group(1)].pc_ignored += 1
            continue
        s = _DISMISSED.match(msg)
        if s:
            cur.sides[s.group(1)].dismissed += 1
            continue
        s = _NO_LINE.match(msg)
        if s:
            cur.sides[s.group(1)].no_line += 1
            continue
        s = _PEAK.match(msg)
        if s:
            peak = cur.sides[s.group(1)].peak
            for kind, score in _PEAK_SCORE.findall(s.group(2)):
                peak[kind] = max(peak.get(kind, 0.0), float(score))
            continue
        if _UNCLASSIFIED.match(msg):
            cur.unclassified += 1
        elif _SCALE.match(msg):
            cur.rescaled += 1
        else:
            s = _HIDDEN.match(msg)
            if s:
                cur.hidden[s.group(1)] += 1
    return found


def log_files(log_dir):
    """server.log and its older parts, oldest first."""
    log_dir = Path(log_dir)
    parts = sorted(log_dir.glob("server.log.*"),
                   key=lambda p: int(p.suffix[1:]) if p.suffix[1:].isdigit() else 0, reverse=True)
    return [p for p in parts if p.suffix[1:].isdigit()] + [log_dir / "server.log"]


def _read_lines(paths, budget=3_000_000):
    """The last `budget` characters or so of these files, as lines (oldest first):
    enough for many matches without reading 20 MB."""
    chunks = []
    for p in reversed(paths):
        try:
            data = p.read_bytes()
        except OSError:
            continue
        if len(data) > budget:
            data = data[-budget:]
            data = data[data.find(b"\n") + 1:]
        chunks.append(data.decode("utf-8", "replace"))
        budget -= len(data)
        if budget <= 0:
            break
    return "".join(reversed(chunks)).splitlines()


def summary(log_dir, version="", count=MAX_MATCHES):
    log_dir = Path(log_dir)
    found = [m for m in matches(_read_lines(log_files(log_dir))) if not m.empty()]
    status = ""
    try:
        status_lines = (log_dir / "last_status.txt").read_text(encoding="utf-8").splitlines()
        status = " / ".join(l.strip() for l in status_lines[:3] if l.strip())
    except OSError:
        pass
    head = f"PPTetrics {version} diagnostic" + (f"\nstatus: {status}" if status else "")
    if not found:
        return head + "\n(no matches in the log yet)"
    body = []
    recent = found[-count:]
    for i, m in enumerate(reversed(recent), 1):     # newest first
        body.append(m.text(i))
    text = head + "\n" + "\n".join(body)
    while len(text) > MAX_CHARS and len(body) > 1:
        body.pop()
        text = head + "\n" + "\n".join(body)
    return text[:MAX_CHARS]


if __name__ == "__main__":
    import sys
    root = Path(__file__).resolve().parents[1]
    print(summary(sys.argv[1] if len(sys.argv) > 1 else root / "logs"))
