"""Entry point: python -m trainer [options]

Wires the services together. Every flag only decides which services exist;
the services themselves never know about each other.
"""
from __future__ import annotations

import argparse
import logging
import sys

from .audio.sound_service import SoundService
from .core.app import App
from .core.config import load
from .core.event_bus import EventBus
from .game.engine import GameEngine
from .game.level import LevelCatalog
from .quiz.question import QuestionBank
from .hardware.keyboard_input import KeyboardInput
from .hardware.mcu_link import McuLink
from .system.metrics_logger import MetricsLogger
from .system.power_manager import PowerManager
from .ui.renderer import Renderer
from .voice.voice_service import (
    VoiceService,
    build_answer_recognizer,
    build_evaluator,
    build_interpreter,
    build_recognizer,
)

log = logging.getLogger(__name__)


def load_questions(cfg) -> QuestionBank:
    """The quiz questions, or none when the quiz is off or the file is unusable."""
    if not cfg.quiz.enabled:
        return QuestionBank()
    try:
        return QuestionBank.load(cfg.quiz.questions_file)
    except (OSError, ValueError, KeyError) as exc:
        log.error("no quiz questions (%s); the quiz is off", exc)
        return QuestionBank()


def build_app(cfg, *, mcu: bool, voice: bool, sound: bool, keyboard: bool, display: bool) -> App:
    bus = EventBus()
    app = App(bus)
    levels = LevelCatalog(cfg.levels_dir)
    questions = load_questions(cfg)
    app.register(GameEngine(bus, cfg.game, levels, cfg.display.width, cfg.display.height, cfg.quiz, questions))
    if display:
        app.register(Renderer(bus, cfg.display))
    if keyboard:
        app.register(KeyboardInput(bus))
    if mcu:
        app.register(McuLink(bus, cfg.mcu))
    if sound:
        app.register(SoundService(bus, cfg.audio))
    if voice:
        interpreter = build_interpreter(cfg.voice, cfg.commands)
        recognizer = build_recognizer(cfg.voice, interpreter.phrases())
        app.register(
            VoiceService(
                bus,
                cfg.voice,
                cfg.commands,
                recognizer=recognizer,
                interpreter=interpreter,
                questions=questions,
                answer_recognizer=build_answer_recognizer(cfg.voice, questions),
                evaluator=build_evaluator(cfg.voice),
            )
        )
    app.register(PowerManager(bus, cfg.system, cfg.game.deadzone_g))
    app.register(MetricsLogger(bus, cfg.system))
    return app


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="trainer", description="Steady Hands surgeon trainer")
    p.add_argument("--config", help="TOML file with overrides")
    p.add_argument("--windowed", action="store_true", help="window instead of fullscreen")
    p.add_argument("--no-mcu", action="store_true", help="do not connect to the MCU (keyboard only)")
    p.add_argument("--no-voice", action="store_true", help="disable the microphone pipeline")
    p.add_argument("--no-sound", action="store_true", help="disable audio output")
    p.add_argument("--no-keyboard", action="store_true", help="ignore keyboard input")
    p.add_argument("--headless", action="store_true", help="no window (SDL dummy driver), for tests")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    cfg = load(args.config)
    if args.windowed:
        cfg.display.fullscreen = False
    if args.headless:
        cfg.display.driver = "dummy"
        cfg.display.fullscreen = False

    app = build_app(
        cfg,
        mcu=cfg.mcu.enabled and not args.no_mcu,
        voice=cfg.voice.enabled and not args.no_voice,
        sound=cfg.audio.enabled and not args.no_sound,
        keyboard=not args.no_keyboard,
        display=True,
    )
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
