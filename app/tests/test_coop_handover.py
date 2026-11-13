"""Co-op: the surgeon calls by voice, the assistant hands over with knob and button C."""
import json

import pytest

from trainer.core.config import GameConfig
from trainer.core.event_bus import EventBus
from trainer.core.events import CommandEvent, GameEvent, InputFrame
from trainer.game.collision_map import CollisionMap
from trainer.game.engine import GameEngine
from trainer.game.level import Level, LevelCatalog
from trainer.game.modes import CoopMode, SoloMode


def test_coop_mode_accepts_only_the_called_instrument_within_the_window():
    mode = CoopMode(window_s=8.0)
    mode.reset("forceps")
    assert mode.on_handover("forceps", 0.0).tool == ""  # nothing was called
    assert mode.on_tool_call("clamp", 1.0) is False  # a call alone hands nothing over
    assert mode.on_tool_call("clamp", 2.0) is False  # saying it twice does not either
    assert mode.pending() == "clamp" and mode.selection() == "forceps"
    assert mode.on_handover("forceps", 3.0).wrong  # the assistant offers the forceps
    assert mode.pending() == "clamp"  # the call stays open
    assert mode.on_manual_select("forceps", 2) == ""  # the knob moves the choice, not the instrument
    assert mode.selection() == "clamp"
    handover = mode.on_handover("forceps", 4.0)
    assert (handover.tool, handover.confirmed, handover.wrong) == ("clamp", True, False)
    assert mode.pending() == ""
    mode.on_tool_call("swab", 10.0)
    mode.on_manual_select("forceps", -1)
    assert mode.selection() == "swab"
    assert mode.on_handover("clamp", 18.5).tool == ""  # too late: the call has run out
    assert mode.pending() == ""


def test_solo_mode_changes_the_instrument_directly():
    mode = SoloMode()
    assert mode.on_tool_call("clamp", 0.0) is True
    assert mode.on_manual_select("forceps", 1) == "swab"
    assert mode.on_manual_select("forceps", -1) == "scalpel"
    assert mode.on_handover("swab", 0.0).tool == "clamp"
    assert mode.selection() == "" and mode.pending() == ""


class OpenCatalog(LevelCatalog):
    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        self.dir = tmp_path / "01-test"
        self.dir.mkdir()
        (self.dir / "level.json").write_text(
            json.dumps({"name": "Test", "time_limit_s": 60, "start": [20, 60], "targets": [{"id": "bleed", "position": [160, 60], "needs": "clamp"}]})
        )

    def load(self, index):
        return Level.load(self.dir, mask=CollisionMap(200, 120, bytearray(200 * 120)))


@pytest.fixture
def coop(tmp_path):
    bus = EventBus()
    eng = GameEngine(bus, GameConfig(), OpenCatalog(tmp_path), 200, 120)
    eng.seen = []
    bus.subscribe(GameEvent, eng.seen.append)
    eng.start()
    eng.toggle_mode()
    assert eng.mode.name == "co-op"
    eng.start_round()
    eng.bus_ = bus
    return eng


def kinds(eng):
    eng.bus_.dispatch()
    return [e.kind for e in eng.seen]


def press(eng, button, knob=0):
    eng.on_input(InputFrame(buttons=button, knob=knob))
    eng.on_input(InputFrame(buttons=0, knob=knob))


def test_surgeon_calls_and_the_assistant_hands_over(coop):
    coop.on_input(InputFrame(knob=0))
    coop.on_command(CommandEvent(word="clamp"))
    assert coop.tool.word == "forceps"  # the call alone changes nothing
    snap = coop.snapshot()
    assert (snap.pending_call, snap.nurse_selection) == ("clamp", "forceps")
    coop.on_input(InputFrame(knob=2))  # forceps -> swab -> clamp
    assert coop.tool.word == "forceps" and coop.snapshot().nurse_selection == "clamp"
    press(coop, InputFrame.BTN_C, knob=2)
    assert coop.tool.word == "clamp"
    assert coop.metrics.calls_correct == 1 and coop.metrics.calls_wrong == 0
    assert coop.snapshot().pending_call == ""
    assert "tool_changed" in kinds(coop)


def test_handing_over_the_wrong_instrument_counts_as_a_wrong_call(coop):
    coop.on_input(InputFrame(knob=0))
    coop.on_command(CommandEvent(word="clamp"))
    coop.on_input(InputFrame(knob=1))  # the assistant picks the swab
    press(coop, InputFrame.BTN_C, knob=1)
    assert coop.tool.word == "forceps"
    assert coop.metrics.calls_wrong == 1
    assert kinds(coop)[-1] == "wrong_tool"
    assert coop.snapshot().pending_call == "clamp"  # the surgeon is still waiting


def test_without_a_call_the_assistant_cannot_change_the_instrument(coop):
    coop.on_input(InputFrame(knob=0))
    coop.on_input(InputFrame(knob=2))
    press(coop, InputFrame.BTN_C, knob=2)
    assert coop.tool.word == "forceps"
    assert coop.metrics.calls_wrong == 0
    assert coop.message == "No instrument was called"


def test_a_new_round_puts_the_assistants_choice_back_on_the_forceps(coop):
    coop.on_input(InputFrame(knob=0))
    coop.on_input(InputFrame(knob=3))
    assert coop.snapshot().nurse_selection == "scalpel"
    coop.on_command(CommandEvent(word="new game"))
    assert coop.snapshot().nurse_selection == "forceps"


def test_solo_knob_and_button_c_still_change_the_instrument(tmp_path):
    bus = EventBus()
    eng = GameEngine(bus, GameConfig(), OpenCatalog(tmp_path), 200, 120)
    eng.start()
    eng.start_round()
    eng.on_input(InputFrame(knob=0))
    eng.on_input(InputFrame(knob=1))
    assert eng.tool.word == "swab"
    eng.on_input(InputFrame(buttons=InputFrame.BTN_C, knob=1))
    assert eng.tool.word == "clamp"
    assert eng.snapshot().nurse_selection == ""
