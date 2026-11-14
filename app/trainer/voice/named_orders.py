"""Orders by name only: "Propofol!" -> propofol at the standard dose."""
from __future__ import annotations

import re

from .command_matcher import CommandMatcher
from .interpreter import Match, OrderInterpreter


class NamedOrders(OrderInterpreter):
    """Every drug named outright in the text, without an amount. No model:
    the minimum version (criterion T3), and Needle's fallback."""

    def __init__(self, treatments: dict[str, list[str]]) -> None:
        self.treatments = treatments
        self._patterns = [
            (word, re.compile(rf"\b{re.escape(phrase.lower())}\b")) for word, phrases in treatments.items() for phrase in phrases
        ]

    def orders(self, text: str) -> list[Match]:
        text = CommandMatcher.normalise(text)
        named: list[tuple[int, str]] = []
        for word, pattern in self._patterns:
            hit = pattern.search(text)
            if hit and word not in {w for _, w in named}:
                named.append((hit.start(), word))
        return [Match(word=word, score=1.0) for _, word in sorted(named)]

    def names(self, text: str) -> set[str]:
        return {m.word for m in self.orders(text)}

    def phrases(self) -> list[str]:
        return [p for phrases in self.treatments.values() for p in phrases]
