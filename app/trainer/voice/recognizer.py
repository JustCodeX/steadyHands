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

    def partial(self) -> str:
        """Best guess for the running segment; "" if the engine has none."""
        return ""

    def set_vocabulary(self, phrases: list[str]) -> None:  # noqa: B027
        """Narrow a restricted recogniser to these phrases (the options of the
        open quiz question). Recognisers with an open vocabulary ignore it."""

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


class EnsembleRecognizer(SpeechRecognizer):
    """Several recognisers hear the same audio; what each heard is joined.

    For quiz answers: an open-vocabulary recogniser follows whole sentences
    but mishears rare words ("clamp" becomes "plan"); a restricted one knows
    the words but loses them inside a sentence. Together they name the option
    more often, and when they contradict each other the answer names two
    options, which the evaluator treats as unclear."""

    def __init__(self, members: list[SpeechRecognizer]) -> None:
        self.members = list(members)

    def accept(self, pcm_int16: bytes) -> None:
        for member in self.members:
            member.accept(pcm_int16)

    def finish(self) -> Transcript:
        heard = [t for t in (member.finish() for member in self.members) if t.text]
        if not heard:
            return Transcript(text="", confidence=0.0)
        return Transcript(text=" ".join(t.text for t in heard), confidence=max(t.confidence for t in heard))

    def partial(self) -> str:
        return " ".join(p for p in (member.partial() for member in self.members) if p)

    def set_vocabulary(self, phrases: list[str]) -> None:
        for member in self.members:
            member.set_vocabulary(phrases)

    def reset(self) -> None:
        for member in self.members:
            member.reset()

    def unload(self) -> None:
        for member in self.members:
            member.unload()
