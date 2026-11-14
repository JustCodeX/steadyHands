"""Render the pictures for the pitch from the real app (no display needed).

Run from app/ with the app's venv:
    cd app && .venv/bin/python ../pitch/make_media.py

Writes into pitch/media/: menu, a BIS alarm in level 4, the nurse's read-back
after "Propofol 50", the result card, and the patient and instrument sprites.
The result card shows an example round (time, contacts and steadiness are set
here, the order is real).
"""
from __future__ import annotations

import os
import random
import sys
import time
from pathlib import Path

OUT = Path(__file__).resolve().parent / "media"
APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))
os.chdir(APP)
os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame  # noqa: E402

from trainer.audio.sound_service import SoundService  # noqa: E402
from trainer.core.config import AudioConfig, DisplayConfig, load  # noqa: E402
from trainer.core.event_bus import EventBus  # noqa: E402
from trainer.core.events import CommandEvent, McuStatus  # noqa: E402
from trainer.game.engine import GameEngine  # noqa: E402
from trainer.game.level import LevelCatalog  # noqa: E402
from trainer.ui.art.instrument_art import InstrumentArt  # noqa: E402
from trainer.ui.art.patient_art import PatientArt  # noqa: E402
from trainer.ui.renderer import Renderer  # noqa: E402

LEVEL = 3  # Shrapnel: BIS and SpO2
SEEDS = range(6, 40)  # the first seed whose first episode is BIS


def shots(seed: int) -> bool:
    """Play level 4 with this seed. False if its first episode is not BIS."""
    cfg = load()
    bus = EventBus()
    eng = GameEngine(bus, cfg.game, LevelCatalog(cfg.levels_dir), 1024, 600, cfg.quiz, None, cfg.vitals, random.Random(seed))
    SoundService(bus, AudioConfig(enabled=False))
    r = Renderer(bus, DisplayConfig(fullscreen=False, driver="dummy"))
    r.start()
    eng.start()
    bus.publish(McuStatus(connected=True))
    bus.dispatch()
    pending: dict[str, pygame.Surface] = {}

    def advance(seconds: float) -> None:
        for _ in range(int(seconds * 30)):
            eng.tick(1 / 30)
            bus.dispatch()

    def shot(name: str) -> None:
        bus.dispatch()
        r.draw(time.monotonic())
        pending[name] = r.screen.copy()

    eng.enter_menu()
    eng._menu_index = LEVEL
    advance(0.5)
    shot("menu.png")
    eng.start_round(LEVEL)
    for _ in range(600):
        advance(0.5)
        if eng.vitals.alarm_raised():
            break
    if eng.vitals.episode != "bis":
        r.stop()
        return False
    advance(2.5)
    shot("alarm.png")
    amount = float(round(eng.vitals.vitals["bis"].need / 10) * 10)
    bus.publish(CommandEvent(word="propofol", confidence=1.0, amount=amount))
    bus.dispatch()
    advance(0.4)
    shot("readback.png")
    advance(6)
    # an example round for the result card
    eng.metrics.started_t = time.monotonic() - 52.4
    eng.metrics.calls_correct = 3
    eng.metrics._jitter_sq_sum, eng.metrics._jitter_n = (0.12 * (1 - 0.86)) ** 2, 1
    eng.patient.contacts = 1
    eng.end_round(True)
    advance(0.3)
    shot("result.png")
    for name, surface in pending.items():
        pygame.image.save(surface, str(OUT / name))
        print("saved", name, f"(seed {seed}, propofol {amount:g} mg)" if name == "readback.png" else "")
    r.stop()
    return True


def sprites() -> None:
    patient, tools = PatientArt(), InstrumentArt()
    for mood in ("asleep", "alarmed", "happy"):
        pygame.image.save(patient.face(mood, 320), str(OUT / f"face-{mood}.png"))
    pygame.image.save(patient.body(900), str(OUT / "patient-body.png"))
    for word in ("forceps", "clamp", "swab", "scalpel"):
        pygame.image.save(tools.icon(word, 160), str(OUT / f"tool-{word}.png"))
    print("saved sprites")


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    if not any(shots(seed) for seed in SEEDS):
        sys.exit("no seed with a BIS episode first")
    sprites()
