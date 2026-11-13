"""The wall-contact buzz plays in the game; the MCU only shows the tool on the button LEDs when asked."""
import array

from trainer.audio.clip_library import ClipLibrary
from trainer.audio.sound_service import BUZZ_RATE, SFX_BUZZ, SoundService, make_buzz_bytes
from trainer.core.config import AudioConfig, McuConfig
from trainer.core.event_bus import EventBus
from trainer.core.events import GameEvent
from trainer.hardware.mcu_link import McuLink


def _captured_speech(tmp_path, monkeypatch):
    service = SoundService(EventBus(), AudioConfig(), clips=ClipLibrary(tmp_path))
    calls = []
    monkeypatch.setattr(service, "speak", lambda ids, interrupt=False: calls.append((list(ids), interrupt)))
    return service, calls


def test_buzz_is_signed_16_bit_mono_of_the_requested_length():
    data = make_buzz_bytes()
    samples = array.array("h")
    samples.frombytes(data)
    assert len(samples) == int(BUZZ_RATE * 0.35)
    assert max(abs(s) for s in samples) > 1000  # audible
    assert abs(samples[-1]) < 200  # faded out at the end, no click


def test_wall_contact_plays_buzz_before_the_ouch_line(tmp_path, monkeypatch):
    service, calls = _captured_speech(tmp_path, monkeypatch)
    service._on_game_event(GameEvent(kind="hit"))
    ids, interrupt = calls[-1]
    assert ids[0] == SFX_BUZZ
    assert ids[1].startswith("ouch_")
    assert interrupt is True


def test_other_events_do_not_buzz(tmp_path, monkeypatch):
    service, calls = _captured_speech(tmp_path, monkeypatch)
    for kind in ("bleed_timeout", "item_out", "win"):
        service._on_game_event(GameEvent(kind=kind))
    assert calls, "the patient lines still play"
    assert all(SFX_BUZZ not in ids for ids, _ in calls)


def _captured_notifies(monkeypatch, cfg):
    link = McuLink(EventBus(), cfg)
    sent = []
    monkeypatch.setattr(link, "_notify", lambda method, *args: sent.append((method, *args)))
    return link, sent


def test_mcu_gets_no_command_for_game_events_by_default(monkeypatch):
    link, sent = _captured_notifies(monkeypatch, McuConfig())
    link._on_game_event(GameEvent(kind="hit"))
    link._on_game_event(GameEvent(kind="bleed_timeout"))
    link._on_game_event(GameEvent(kind="tool_changed", detail="swab"))
    assert sent == []


def test_tool_leds_show_the_tool_and_a_wall_contact_sends_nothing(monkeypatch):
    link, sent = _captured_notifies(monkeypatch, McuConfig(tool_leds=True))
    link._on_game_event(GameEvent(kind="hit"))
    assert sent == []  # a wall contact sends nothing to the MCU
    link._on_game_event(GameEvent(kind="tool_changed", detail="swab"))
    link._on_game_event(GameEvent(kind="win"))
    assert sent == [("leds", 0b010), ("leds", 0)]
