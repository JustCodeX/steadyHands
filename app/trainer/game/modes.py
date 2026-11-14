"""Game modes decide how a tool call becomes a tool change, and what the
knob and button C do during a round."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..core.config import TOOL_WORDS


@dataclass
class Handover:
    """What button C leads to."""

    tool: str = ""  # the instrument to hand over now; "" for none
    confirmed: bool = False  # it answers a spoken call
    wrong: bool = False  # the assistant offered another instrument than the one called


class GameMode(ABC):
    name: str = ""

    @abstractmethod
    def on_tool_call(self, word: str, now: float) -> bool:
        """A spoken call. Return True when the instrument should be handed over now."""

    @abstractmethod
    def on_manual_select(self, current: str, step: int) -> str:
        """The knob turned by `step`. Return the instrument to switch to now, or ""."""

    @abstractmethod
    def on_handover(self, current: str, now: float) -> Handover:
        """Button C was pressed."""

    def pending(self) -> str:
        """The instrument that was called and not handed over yet."""
        return ""

    def selection(self) -> str:
        """The instrument the assistant has ready, if the mode has an assistant."""
        return ""

    def expire(self, now: float) -> None:  # noqa: B027
        pass

    def reset(self, current: str = TOOL_WORDS[0]) -> None:  # noqa: B027
        pass

    @staticmethod
    def _step(word: str, step: int) -> str:
        return TOOL_WORDS[(TOOL_WORDS.index(word) + step) % len(TOOL_WORDS)]


class SoloMode(GameMode):
    """One player: a call, the knob and button C all change the instrument at once."""

    name = "solo"

    def on_tool_call(self, word: str, now: float) -> bool:
        return True

    def on_manual_select(self, current: str, step: int) -> str:
        return self._step(current, step)

    def on_handover(self, current: str, now: float) -> Handover:
        return Handover(tool=self._step(current, 1))


class CoopMode(GameMode):
    """Two players, as in an operating room. The surgeon wears the headset,
    steers and calls for an instrument. The assistant has the knob and the
    buttons: the knob picks an instrument from the tray, button C hands it
    over. Only the instrument that was called is accepted, and only within
    the call window (closed-loop communication)."""

    name = "co-op"

    def __init__(self, window_s: float = 8.0) -> None:
        self.window_s = window_s
        self._pending: str = ""
        self._pending_t: float = 0.0
        self._selection: str = TOOL_WORDS[0]

    def on_tool_call(self, word: str, now: float) -> bool:
        self._pending = word
        self._pending_t = now
        return False

    def on_manual_select(self, current: str, step: int) -> str:
        self._selection = self._step(self._selection, step)
        return ""

    def on_handover(self, current: str, now: float) -> Handover:
        self.expire(now)
        if not self._pending:
            return Handover()
        if self._selection != self._pending:
            return Handover(wrong=True)
        self._pending = ""
        return Handover(tool=self._selection, confirmed=True)

    def pending(self) -> str:
        return self._pending

    def selection(self) -> str:
        return self._selection

    def expire(self, now: float) -> None:
        if self._pending and now - self._pending_t > self.window_s:
            self._pending = ""

    def reset(self, current: str = TOOL_WORDS[0]) -> None:
        self._pending = ""
        self._selection = current
