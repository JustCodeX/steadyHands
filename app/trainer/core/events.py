"""Every message on the EventBus is one of these dataclasses.

They are the interface tables from PLAN.md written as classes. Events carry
numbers and short identifiers only: never audio, never transcripts.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum


class VoiceState(Enum):
    """What the voice system is doing. Values match StatusLed.h on the MCU."""

    OFF = 0
    LISTENING = 1
    PROCESSING = 2
    SPEAKING = 3


class GameState(Enum):
    IDLE = "idle"
    MENU = "menu"
    PLAYING = "playing"
    PAUSED = "paused"
    RESULT = "result"


@dataclass(kw_only=True)
class Event:
    """Base class. `t` is the monotonic time the event was created."""

    t: float = field(default_factory=time.monotonic)


# --- MCU <-> Linux -----------------------------------------------------------


@dataclass(kw_only=True)
class InputFrame(Event):
    """One input snapshot, 50 Hz from the MCU (or from the keyboard in dev mode)."""

    tilt_x: float = 0.0
    tilt_y: float = 0.0
    knob: int = 0
    buttons: int = 0
    distance_mm: int = 0  # position mode: ToF X (left wall)
    distance_y_mm: int = 0  # position mode: ToF Y (top wall)
    sensors_ok: int = 0
    seq: int = 0
    source: str = "mcu"

    BTN_A = 1 << 0
    BTN_B = 1 << 1
    BTN_C = 1 << 2
    BTN_KNOB = 1 << 3

    # sensors_ok bits, mirroring firmware/lib/Core/InputFrame.h
    SENSOR_TILT = 1 << 0
    SENSOR_KNOB = 1 << 1
    SENSOR_BUTTONS = 1 << 2
    SENSOR_DISTANCE = 1 << 3
    SENSOR_TOF_X = 1 << 4
    SENSOR_TOF_Y = 1 << 5
    SENSOR_TOF_CLASH = 1 << 6

    @property
    def a(self) -> bool:
        return bool(self.buttons & self.BTN_A)

    @property
    def b(self) -> bool:
        return bool(self.buttons & self.BTN_B)

    @property
    def c(self) -> bool:
        return bool(self.buttons & self.BTN_C)

    @property
    def knob_pressed(self) -> bool:
        return bool(self.buttons & self.BTN_KNOB)


@dataclass(kw_only=True)
class McuStatus(Event):
    """Published by McuLink when the link comes up or goes quiet."""

    connected: bool
    detail: str = ""


# --- Voice <-> game ----------------------------------------------------------


@dataclass(kw_only=True)
class CommandEvent(Event):
    """A recognised command word with its confidence (0..1)."""

    word: str
    confidence: float = 1.0
    speech_end_t: float | None = None  # when the speaker stopped, for latency


@dataclass(kw_only=True)
class MisheardEvent(Event):
    """Speech was detected but no command matched well enough."""

    reason: str = "no_match"  # "no_match" | "low_confidence"
    speech_end_t: float | None = None


@dataclass(kw_only=True)
class VoiceStateChanged(Event):
    state: VoiceState


@dataclass(kw_only=True)
class AsrDebugEvent(Event):
    """Debug only: what the recogniser heard, for the on-screen ASR panel.

    Published only with `voice.debug_asr = true` — the one deliberate
    exception to the "never transcripts" rule above, for testing.
    """

    text: str
    confidence: float = 0.0
    outcome: str = "partial"  # "partial" | "command" | "low_confidence" | "no_match" | "empty"
    word: str = ""  # the matched command, if any


@dataclass(kw_only=True)
class ListenRequest(Event):
    """Game -> voice: listen only while a round runs."""

    on: bool


# --- Game -> sound / display -------------------------------------------------


@dataclass(kw_only=True)
class GameEvent(Event):
    """Something happened in the game. `kind` selects the patient line."""

    kind: str  # hit, item_out, win, lose, pardon, help, wrong_tool, bleed_timeout, tool_changed, repeat, ...
    detail: str = ""


@dataclass(kw_only=True)
class RoundResult(Event):
    level_name: str
    won: bool
    time_s: float
    contacts: int
    steadiness: float  # 0..100, higher is steadier
    calls_correct: int
    calls_wrong: int
    steady_uses: int


@dataclass(kw_only=True)
class PlaybackStarted(Event):
    pass


@dataclass(kw_only=True)
class PlaybackFinished(Event):
    pass


# --- UI and system -----------------------------------------------------------


@dataclass(kw_only=True)
class KeyEvent(Event):
    """A keyboard key went down or up (dev mode and demo fallback)."""

    key: str  # pygame key name, e.g. "left", "space", "1"
    down: bool


@dataclass(kw_only=True)
class QuitRequest(Event):
    pass


@dataclass(kw_only=True)
class IdleChanged(Event):
    idle: bool


@dataclass(kw_only=True)
class TargetView:
    """A target as the renderer needs it."""

    id: str
    x: int
    y: int
    needs: str
    done: bool
    timer_left: float | None
    timer_s: float | None = None  # full length of the timer, for the countdown ring


@dataclass(kw_only=True)
class GameSnapshot(Event):
    """Everything the renderer needs to draw one frame, published every tick."""

    state: GameState
    mode: str
    level_name: str
    level_dir: str
    x: float
    y: float
    tool: str
    targets: list[TargetView]
    time_left: float
    contacts: int
    max_contacts: int
    heart_rate: int
    last_command: str
    message: str
    steady: bool
    lit: bool
    dark_zones: list[tuple[int, int, int, int]]
    pending_call: str
    menu_levels: list[str]
    menu_index: int
    result: RoundResult | None
    mcu_connected: bool
    tools: tuple[str, ...] = ()  # every instrument, in knob order
    hover_target: str = ""  # id of the target under the instrument
    dwell: float = 0.0  # 0..1 progress of the hands-free grab
    sensitivity: float = 1.0
    sensitivity_range: tuple[float, float] = (0.3, 2.0)
    tool_radius: int = 9
    light_left: float = 0.0  # seconds of light remaining
