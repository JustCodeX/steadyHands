"""Game modes decide how a tool call becomes a tool change."""
from __future__ import annotations

from abc import ABC, abstractmethod


class GameMode(ABC):
    name: str = ""

    @abstractmethod
    def on_tool_call(self, word: str, now: float) -> bool:
        """Return True when the instrument should be handed over now."""

    def pending(self) -> str:
        return ""

    def reset(self) -> None:  # noqa: B027
        pass


class SoloMode(GameMode):
    """One player: a call hands the instrument over at once."""

    name = "solo"

    def on_tool_call(self, word: str, now: float) -> bool:
        return True


class CoopMode(GameMode):
    """Two players: the surgeon calls, the assistant repeats the call into the
    headset. The instrument is handed over when the same word is heard twice
    within the call-back window (closed-loop communication)."""

    name = "co-op"

    def __init__(self, window_s: float = 5.0) -> None:
        self.window_s = window_s
        self._pending: str = ""
        self._pending_t: float = 0.0

    def on_tool_call(self, word: str, now: float) -> bool:
        if self._pending == word and now - self._pending_t <= self.window_s:
            self._pending = ""
            return True
        self._pending = word
        self._pending_t = now
        return False

    def pending(self) -> str:
        return self._pending

    def expire(self, now: float) -> None:
        if self._pending and now - self._pending_t > self.window_s:
            self._pending = ""

    def reset(self) -> None:
        self._pending = ""
