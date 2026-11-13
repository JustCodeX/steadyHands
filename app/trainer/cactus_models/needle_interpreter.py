"""Treatments in free speech: "he can't breathe" -> oxygen.

Needle only decides the vitals-monitor treatments. Every older command stays
on the Vosk grammar (docs/needle-integration.md)."""
from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from pathlib import Path

from ..game.actions import MODEL_ACTIONS, ActionCatalog
from ..voice.command_matcher import CommandMatcher
from ..voice.interpreter import CommandInterpreter, Match
from .needle_agent import RUNTIME_GATE, NeedleAgent

log = logging.getLogger(__name__)

SYSTEM = (
    "device: surgical training game; the user is the surgeon. They call for instruments and "
    "tell the nurse how to treat the patient; locale: en-US"
)


class NeedleInterpreter(CommandInterpreter):
    """The treatment phrases first; Needle only for speech that contains
    none. "Adrenaline!" never waits for the model.

    The matcher's fuzzy guess is never used: a wrong treatment harms the
    patient, so "no tool", or a model that fails, means no treatment.

    `require_trigger`: the model only runs when one of the tools' triggers
    matches the text. Measured 14 Nov 2026 on the published rungs: without
    this gate every rung called a tool for most talk (23 to 38 of 39
    sentences), and the confidence of those calls was as high as that of
    right ones, so no threshold separates them. Speech without a trigger
    word costs no model run (criterion C3)."""

    def __init__(
        self,
        commands: dict[str, list[str]],
        weights: str | Path,
        catalog: ActionCatalog | None = None,
        min_confidence: float = RUNTIME_GATE,
        agent: NeedleAgent | None = None,
        require_trigger: bool = True,
    ) -> None:
        self._keywords = CommandMatcher(commands)
        self._catalog = catalog or ActionCatalog(MODEL_ACTIONS)
        self._agent = agent or NeedleAgent(weights, SYSTEM, self._catalog.schemas, min_confidence)
        self.require_trigger = require_trigger
        self._triggers = [re.compile(t, re.IGNORECASE) for a in self._catalog.actions() for t in a.triggers]
        self._agent.load()  # fail at start-up, where the caller can fall back

    def interpret(self, text: str, allowed: Sequence[str] | None = None) -> Match | None:
        hit = self._keywords.interpret(text, allowed)
        if hit is not None and hit.score == 1.0:
            return hit
        if not text.strip():
            return None
        if self.require_trigger and not self.triggered(text):
            return None
        try:
            call = self._agent.call(text)
        except Exception:
            log.exception("Needle failed; no treatment")
            return None
        if call is None:
            return None
        word = self._catalog.command_word(call.name, call.arguments)
        if word is None or (allowed is not None and word not in allowed):
            return None
        return Match(word=word, score=call.confidence)

    def triggered(self, text: str) -> bool:
        return any(t.search(text) for t in self._triggers)

    def phrases(self) -> list[str]:
        return self._keywords.phrases()

    def unload(self) -> None:
        self._agent.unload()
