"""Transcript -> command word, behind one small interface.

The keyword matcher is the default. A tool-calling model (Needle) is a further
subclass selected with `voice.interpreter`; see docs/needle-integration.md.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass
class Match:
    word: str  # a key of the command table, e.g. "clamp" or "new game"
    score: float  # 0..1


class CommandInterpreter(ABC):
    @abstractmethod
    def interpret(self, text: str, allowed: Sequence[str] | None = None) -> Match | None:
        """Map the transcript of one speech segment to a command word.

        `allowed` lists the command words that make sense right now; None means
        all of them. Return None when the speech is not a command."""

    @abstractmethod
    def phrases(self) -> list[str]:
        """Every phrase a vocabulary-restricted recogniser must be able to hear."""

    def unload(self) -> None:  # noqa: B027
        """Free model memory, if any."""
