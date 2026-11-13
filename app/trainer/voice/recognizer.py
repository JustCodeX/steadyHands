"""Speech-to-text behind one small interface, so engines can be swapped (D2)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Transcript:
    text: str
    confidence: float  # 0..1


class SpeechRecognizer(ABC):
    @abstractmethod
    def accept(self, pcm_int16: bytes) -> None:
        """Feed 16 kHz mono int16 audio of the current segment."""

    @abstractmethod
    def finish(self) -> Transcript:
        """End the segment and return what was heard."""

    def reset(self) -> None:  # noqa: B027
        pass

    def unload(self) -> None:  # noqa: B027
        pass


class NullRecognizer(SpeechRecognizer):
    """Hears nothing. Used when no model is installed or in tests."""

    def accept(self, pcm_int16: bytes) -> None:
        pass

    def finish(self) -> Transcript:
        return Transcript(text="", confidence=0.0)
