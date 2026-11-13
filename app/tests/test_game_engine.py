import json
import time

import pytest

from trainer.core.config import GameConfig
from trainer.core.event_bus import EventBus
from trainer.core.events import CommandEvent, GameEvent, GameState, InputFrame, ListenRequest, MisheardEvent, RoundResult
from trainer.game.collision_map import CollisionMap
from trainer.game.engine import GameEngine
from trainer.game.level import Level, LevelCatalog
from trainer.game.metrics import TrainingMetrics


class OpenCatalog(LevelCatalog):
    """One level with an open map: a 200x120 corridor, targets inside."""

    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        self.dir = tmp_path / "01-test"
        self.dir.mkdir()
        (self.dir / "level.json").write_text(
            json.dumps(
                {
                    "name": "Test",
                    "time_limit_s": 30,
                    "start": [20, 60],
                    "targets": [
                        {"id": "splinter", "position": [100, 60], "needs": "forceps"},
                        {"id": "bleed", "position": [160, 60], "needs": "clamp", "timer_s": 5},
                    ],
                }
            )
        )

    def load(self, index):
        walls = bytearray(200 * 120)
        for y in range(120):
            for x in range(200):
                if y < 10 or y > 110:
                    walls[y * 200 + x] = 1
        return Level.load(self.dir, mask=CollisionMap(200, 120, walls))


@pytest.fixture
def engine(tmp_path):
    bus = EventBus()
    cfg = GameConfig(speed_px_per_s=100.0, grab_dwell_s=0.5, contact_cooldown_s=0.1)
    eng = GameEngine(bus, cfg, OpenCatalog(tmp_path), width=200, height=120)
    events = []
    bus.subscribe(GameEvent, events.append)
    bus.subscribe(RoundResult, events.append)
    bus.subscribe(ListenRequest, events.append)
    eng.start()
    eng.events = events
    eng.bus_ = bus
    return eng


def kinds(engine):
    engine.bus_.dispatch()
    return [e.kind for e in engine.events if isinstance(e, GameEvent)]


def test_menu_to_round_with_button_a(engine):
    assert engine.state is GameState.MENU
    engine.on_input(InputFrame(buttons=InputFrame.BTN_A))
    assert engine.state is GameState.PLAYING
    assert "round_started" in kinds(engine)
    assert any(isinstance(e, ListenRequest) and e.on for e in engine.events)


def test_tilt_moves_and_wall_contact_is_a_hit(engine):
    engine.start_round()
    x0 = engine.x
    engine.on_input(InputFrame(tilt_x=1.0))
    engine.tick(0.5)
    assert engine.x > x0
    # push up into the wall at y<10
    for _ in range(40):
        engine.on_input(InputFrame(tilt_y=-1.0))
        engine.tick(0.1)
        time.sleep(0.003)
    assert engine.patient.contacts >= 1
    assert "hit" in kinds(engine)


def test_three_contacts_lose(engine):
    engine.start_round()
    for _ in range(3):
        engine._contact(time.monotonic() + 10 * _)  # bypass cooldown deterministically
    engine.tick(0.01)
    engine.bus_.dispatch()
    assert engine.state is GameState.RESULT
    result = [e for e in engine.events if isinstance(e, RoundResult)][0]
    assert result.won is False and result.contacts == 3


def test_voice_tool_change_and_cancel(engine):
    engine.start_round()
    engine.on_command(CommandEvent(word="clamp"))
    assert engine.tool.word == "clamp" and engine.metrics.calls_correct == 1
    engine.on_command(CommandEvent(word="cancel"))
    assert engine.tool.word == "forceps"
    assert kinds(engine).count("tool_changed") == 2


def test_hands_free_grab_and_win(engine):
    engine.start_round()
    engine.x, engine.y = 100.0, 60.0  # over the splinter with forceps
    engine.tick(0.1)
    engine.tick(0.6)  # dwell exceeded
    assert engine.level.targets[0].done
    assert "item_out" in kinds(engine)
    engine.on_command(CommandEvent(word="clamp"))
    engine.x, engine.y = 160.0, 60.0
    engine.tick(0.1)
    engine.tick(0.6)
    assert engine.state is GameState.RESULT
    assert "win" in kinds(engine)


def test_wrong_tool_counts(engine):
    engine.start_round()
    engine.x, engine.y = 160.0, 60.0  # bleeding needs clamp, we hold forceps
    engine.on_input(InputFrame(buttons=InputFrame.BTN_A))
    assert engine.metrics.calls_wrong == 1
    assert "wrong_tool" in kinds(engine)


def test_bleeding_timer_counts_as_contact(engine):
    engine.start_round()
    engine.x, engine.y = 20.0, 60.0
    for _ in range(60):
        engine.tick(0.1)
    assert engine.patient.contacts >= 1
    assert "bleed_timeout" in kinds(engine)


def test_misheard_twice_gives_help(engine):
    engine.start_round()
    engine.on_misheard(MisheardEvent())
    engine.on_misheard(MisheardEvent())
    k = kinds(engine)
    assert k.count("pardon") == 1 and "help" in k


def test_metrics_steadiness():
    m = TrainingMetrics()
    m.start(0.0)
    m.add_tilt(0.0, 0.0, moving=False)  # at rest, then a step to full tilt: not jitter
    for i in range(100):
        m.add_tilt(0.5, 0.0, moving=True)
    assert m.steadiness() == 100.0
    m2 = TrainingMetrics()
    m2.start(0.0)
    for i in range(100):
        m2.add_tilt(0.3 if i % 2 else -0.3, 0.0, moving=True)
    assert m2.steadiness() < 20.0
    m2.end(48.0)
    r = m2.result("L", True)
    assert r.time_s == 48.0


# --- controls without voice: knob and buttons --------------------------------


def turn_knob(engine, position, buttons=0):
    engine.on_input(InputFrame(knob=position, buttons=buttons))


def test_knob_selects_the_tool_in_a_round(engine):
    engine.start_round()
    turn_knob(engine, 0)
    assert engine.tool.word == "forceps"
    turn_knob(engine, 1)
    assert engine.tool.word == "swab"
    turn_knob(engine, 3)  # two clicks between two frames: two tools on
    assert engine.tool.word == "scalpel"
    turn_knob(engine, 4)
    assert engine.tool.word == "forceps"  # wraps around
    turn_knob(engine, 3)
    assert engine.tool.word == "scalpel"  # and backwards
    assert engine.sensitivity == 1.0  # the knob no longer changes the speed while playing
    assert engine.metrics.calls_correct == 0  # choosing by hand is not a voice call


def test_knob_sets_the_speed_while_paused(engine):
    engine.start_round()
    turn_knob(engine, 0)
    engine.pause()
    turn_knob(engine, 5)
    assert engine.sensitivity == pytest.approx(1.0 + 5 * engine.cfg.knob_sensitivity_per_step)
    assert engine.tool.word == "forceps"
    assert engine.snapshot().sensitivity == engine.sensitivity


def test_knob_press_switches_on_the_light(engine):
    engine.start_round()
    turn_knob(engine, 0, buttons=InputFrame.BTN_KNOB)
    assert "light" not in kinds(engine)  # this level has no dark zone
    engine.level.dark_zones = [(0, 0, 50, 50)]
    turn_knob(engine, 0)
    turn_knob(engine, 0, buttons=InputFrame.BTN_KNOB)
    assert "light" in kinds(engine)
    snap = engine.snapshot()
    assert snap.lit and snap.light_left > 0


def test_snapshot_reports_hover_and_dwell(engine):
    engine.start_round()
    engine.x, engine.y = 160.0, 60.0  # over the bleeding, holding forceps
    engine.tick(0.1)
    snap = engine.snapshot()
    assert snap.hover_target == "bleed" and snap.dwell == 0.0
    assert snap.tools == ("forceps", "swab", "clamp", "scalpel")
    engine.x, engine.y = 100.0, 60.0  # over the splinter: the right tool
    engine.tick(0.1)
    engine.tick(0.25)
    snap = engine.snapshot()
    assert snap.hover_target == "splinter" and 0.4 < snap.dwell < 0.6


def test_winning_selects_the_next_level(engine):
    engine.levels.names = lambda: ["one", "two", "three"]
    engine.start_round(0)
    for target in engine.level.targets:
        target.done = True
    engine.tick(0.1)
    assert engine.state is GameState.RESULT
    assert engine.snapshot().menu_index == 1
