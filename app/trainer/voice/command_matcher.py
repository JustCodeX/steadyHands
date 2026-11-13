"""Maps a transcript to one command word, or to nothing."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass


@dataclass
class Match:
    word: str
    score: float  # 0..1


class CommandMatcher:
    def __init__(self, commands: dict[str, list[str]], threshold: float = 0.75) -> None:
        self.commands = commands
        self.threshold = threshold
        self._phrases = [(phrase.lower(), word) for word, phrases in commands.items() for phrase in phrases]

    def phrases(self) -> list[str]:
        return [p for p, _ in self._phrases]

    @staticmethod
    def normalise(text: str) -> str:
        return re.sub(r"[^a-z ]+", " ", text.lower()).strip()

    def match(self, text: str) -> Match | None:
        text = self.normalise(text)
        if not text:
            return None
        best: Match | None = None
        tokens = text.split()
        for phrase, word in self._phrases:
            # exact phrase inside the transcript wins outright
            if re.search(rf"\b{re.escape(phrase)}\b", text):
                return Match(word=word, score=1.0)
            # otherwise fuzzy against the whole text and against each token
            candidates = [text] + tokens
            score = max(difflib.SequenceMatcher(None, phrase, c).ratio() for c in candidates)
            if best is None or score > best.score:
                best = Match(word=word, score=score)
        if best is not None and best.score >= self.threshold:
            return best
        return None
