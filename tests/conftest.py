"""Shared test setup: the tests never make a sound.

演出強化's sounds and the announcer's voice are real QSoundEffects: a test with
the effects on played them out loud on the machine running the tests (user:
"the sound effects went off with nothing done and the effects off" — it was
the tests). Here every test gets silent stand-ins instead."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT / "scripts", ROOT / "hud"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


class SilentSounds:
    def preload(self, *args, **kwargs):
        pass

    def play(self, *args, **kwargs):
        pass

    def say(self, *args, **kwargs):
        pass


@pytest.fixture(autouse=True)
def no_sound(monkeypatch):
    try:
        import dopamine
    except Exception:   # (a test run without Qt: nothing to keep quiet)
        yield
        return
    monkeypatch.setattr(dopamine, "shared_sounds", lambda: SilentSounds())
    monkeypatch.setattr(dopamine, "shared_announcer", lambda: SilentSounds())
    yield
