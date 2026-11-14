"""Matching free transcription against the command list.

Whistle transcribes freely, so the text has to be reduced to one of our
commands. Two things make this robust enough for a noisy hall:

- the vocabulary is tiny and the words were picked to sound unlike each other,
- a near-miss is better rejected than guessed: below the threshold the game
  shows "?" and the patient asks "Pardon?" (PLAN.md, "Misheard speech").
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

# Command word -> what it does. The words are deliberately dissimilar.
COMMANDS = {
    "forceps": "grab",
    "swab": "clear_blood",
    "clamp": "stop_bleeding",
    "scalpel": "open_passage",
    "light": "light",
    "steady": "precision",
    "cancel": "undo",
    "repeat": "repeat",
    "help": "help",
    "pause": "pause",
    "continue": "continue",
}

# Things the recogniser reliably hears instead of a command. Whistle
# transcribes freely, so a command can come back as two ordinary words that
# sound right but read wrong - "forceps" becomes "four steps". Measured on
# the board, not guessed; add to this list as the hall testing turns up more.
ALIASES = {
    "four steps": "forceps",
    "foresees": "forceps",
    "force ups": "forceps",
    "swap": "swab",
    "clamped": "clamp",
    "scalp el": "scalpel",
    "ready": "steady",
}

# Below this, we deliberately recognise nothing. Measured: at 0.75 the French
# "pas" in ordinary speech matched "pause" and paused the game, which in
# co-op - where the players talk constantly - is unacceptable.
CONFIDENCE_THRESHOLD = 0.82

# A candidate much shorter than the command it matched is almost always a
# coincidence ("pas" vs "pause"), so require comparable length.
MAX_LENGTH_DIFFERENCE = 2


@dataclass
class CommandEvent:
    """A recognised command, or a deliberate non-recognition."""

    command: str | None
    action: str | None
    confidence: float
    heard: str

    @property
    def recognised(self):
        return self.command is not None


class CommandMatcher:
    def __init__(self, commands=None, threshold=CONFIDENCE_THRESHOLD, aliases=None):
        self.commands = commands or COMMANDS
        self.threshold = threshold
        self.aliases = ALIASES if aliases is None else aliases

    def match(self, transcript):
        """Pick the best command in the transcript, or none."""
        text = transcript.text if hasattr(transcript, "text") else str(transcript)
        lowered = text.lower()

        # A known mis-transcription counts as the command itself.
        for phrase, command in self.aliases.items():
            if phrase in lowered:
                return CommandEvent(command, self.commands[command], 1.0, text)

        words = re.findall(r"[a-z]+", lowered)
        # Compare single words and adjacent pairs joined together, because a
        # command is often split in two: "four steps" -> "foursteps".
        candidates = words + [a + b for a, b in zip(words, words[1:])]

        best, score = None, 0.0
        for candidate in candidates:
            for command in self.commands:
                if abs(len(candidate) - len(command)) > MAX_LENGTH_DIFFERENCE:
                    continue
                ratio = difflib.SequenceMatcher(None, candidate, command).ratio()
                if ratio > score:
                    best, score = command, ratio

        if best is None or score < self.threshold:
            return CommandEvent(None, None, score, text)
        return CommandEvent(best, self.commands[best], score, text)
