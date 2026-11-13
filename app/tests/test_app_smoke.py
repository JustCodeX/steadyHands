"""Starts the whole app headless (no MCU, no voice, no sound) for a few steps."""
from pathlib import Path

from trainer.__main__ import build_app
from trainer.core.config import load
from trainer.core.events import KeyEvent, GameState


def test_app_runs_headless(tmp_path):
    cfg = load()
    cfg.display.driver = "dummy"
    cfg.display.fullscreen = False
    cfg.levels_dir = str(Path(__file__).resolve().parents[2] / "levels")
    cfg.system.metrics_log = str(tmp_path / "m.csv")
    app = build_app(cfg, mcu=False, voice=False, sound=False, keyboard=True, display=True)
    app.start()
    try:
        for _ in range(5):
            app.step(1 / 60)
        engine = app.services[0]
        assert engine.state is GameState.MENU
        app.bus.publish(KeyEvent(key="n", down=True))
        for _ in range(5):
            app.step(1 / 60)
        assert engine.state is GameState.PLAYING
        app.bus.publish(KeyEvent(key="right", down=True))
        for _ in range(30):
            app.step(1 / 60)
        assert engine.x > engine.level.start[0]
    finally:
        app.stop()
    assert (tmp_path / "m.csv").exists()
