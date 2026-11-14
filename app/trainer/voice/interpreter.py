"""Transcript -> command word, and transcript -> orders, behind two small interfaces.

CommandInterpreter: the older commands (the keyword matcher).
OrderInterpreter: the nurse's orders, a drug and, if said, an amount
("Propofol 30"). The keyword version only hears the drug's name; the Needle
version also reads the amount (docs/needle-integration.md).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass
class Match:
    word: str  # a key of the command table, e.g. "clamp" or "new game"
    score: float  # 0..1
    amount: float | None = None  # for an order: the amount said; None = not said (standard dose)


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


class OrderInterpreter(ABC):
    @abstractmethod
    def orders(self, text: str) -> list[Match]:
        """Every order in the text, in the order given: [] if it names no drug."""

    @abstractmethod
    def phrases(self) -> list[str]:
        """The drug names, for a vocabulary-restricted recogniser."""

    def unload(self) -> None:  # noqa: B027
        """Free model memory, if any."""
