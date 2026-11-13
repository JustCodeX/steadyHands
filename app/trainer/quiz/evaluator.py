"""Spoken answer -> one of the question's options, behind an interface.

The keyword evaluator is the default. A tool-calling model (Needle) is a
further subclass: the options become the enum of an `answer(choice)` tool.
See docs/needle-integration.md.
"""
from __future__ import annotations

import difflib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .question import Question


@dataclass
class Verdict:
    choice: str | None  # an option id; None when the answer names no single option
    score: float = 0.0  # 0..1


class AnswerEvaluator(ABC):
    @abstractmethod
    def evaluate(self, question: Question, text: str) -> Verdict:
        """Decide which option the transcript of a spoken answer means."""

    def unload(self) -> None:  # noqa: B027
        """Free model memory, if any."""


class KeywordEvaluator(AnswerEvaluator):
    """Looks for the options' phrases in the answer. No model.

    An answer that names exactly one option means that option. One that names
    none, or several, is unclear, so the player is asked again. A word that is
    one option's phrase is never also counted as a near miss of another option
    ("lamp" is the light, not a misheard "clamp")."""

    FUZZY_MIN_LENGTH = 5  # short words ("no", "yes", "four") must match exactly

    def __init__(self, fuzzy_threshold: float = 0.82) -> None:
        self.fuzzy_threshold = fuzzy_threshold

    @staticmethod
    def normalise(text: str) -> str:
        return re.sub(r"[^a-z ]+", " ", text.lower()).strip()

    def evaluate(self, question: Question, text: str) -> Verdict:
        text = self.normalise(text)
        if not text:
            return Verdict(None)
        named = {option: self._score(phrases, text) for option, phrases in question.options.items()}
        named = {option: score for option, score in named.items() if score > 0}
        exact = {option: score for option, score in named.items() if score == 1.0}
        named = exact or named
        if len(named) != 1:
            return Verdict(None)
        (choice, score), = named.items()
        return Verdict(choice, score)

    def _score(self, phrases: tuple[str, ...], text: str) -> float:
        best = 0.0
        tokens = text.split()
        for phrase in phrases:
            if re.search(rf"\b{re.escape(phrase)}\b", text):
                return 1.0
            if len(phrase) < self.FUZZY_MIN_LENGTH or " " in phrase:
                continue
            score = max(difflib.SequenceMatcher(None, phrase, token).ratio() for token in tokens)
            if score >= self.fuzzy_threshold:
                best = max(best, score)
        return best
