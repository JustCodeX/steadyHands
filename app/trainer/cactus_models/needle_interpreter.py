"""Commands in free speech: "something to stop the bleeding" -> clamp."""
from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from ..game.actions import ActionCatalog, GameAction
from ..voice.command_matcher import CommandMatcher
from ..voice.interpreter import CommandInterpreter, Match
from .needle_agent import NeedleAgent, Record, choice_tool, plain_tool

log = logging.getLogger(__name__)

SYSTEM = "device: surgical training game; the user is a surgeon who calls for instruments and gives short commands; locale: en-US"


def action_tools(catalog: ActionCatalog, record: Record) -> list[Callable]:
    tools = []
    for action in catalog.actions():
        if not action.parameters:
            tools.append(plain_tool(action.name, action.description, record))
            continue
        (values,) = action.parameters.values()  # the tool shape has room for one parameter
        tools.append(choice_tool(action.name, action.description, "one of " + ", ".join(values), values, record))
    return tools


class NeedleInterpreter(CommandInterpreter):
    """The keyword matcher first; Needle only for speech that contains no
    command phrase. A plain "Clamp!" never waits for the model.

    With free speech the matcher's fuzzy guess is not trusted ("last night"
    is close to "light"): there the model decides, and "no tool" means the
    speech was not a command. The guess is only the fallback if the model
    itself fails."""

    def __init__(
        self,
        commands: dict[str, list[str]],
        weights: str | Path,
        catalog: ActionCatalog | None = None,
        min_confidence: float = 0.1,
        agent: NeedleAgent | None = None,
    ) -> None:
        self._keywords = CommandMatcher(commands)
        self._catalog = catalog or ActionCatalog()
        self._agent = agent or NeedleAgent(weights, SYSTEM, lambda record: action_tools(self._catalog, record), min_confidence)
        self._agent.load()  # fail at start-up, where the caller can fall back

    def interpret(self, text: str, allowed: Sequence[str] | None = None) -> Match | None:
        hit = self._keywords.interpret(text, allowed)
        if hit is not None and hit.score == 1.0:
            return hit
        if not text.strip():
            return None
        try:
            call = self._agent.call(text)
        except Exception:
            log.exception("Needle failed on a command; keyword result used")
            return hit
        if call is None:
            return None
        word = self._catalog.command_word(call.name, self._arguments(call.name, call.arguments))
        if word is None or (allowed is not None and word not in allowed):
            return None
        return Match(word=word, score=call.confidence)

    def _arguments(self, name: str, arguments: dict) -> dict:
        """The tool's one parameter is called `choice`; the catalogue has its own name for it."""
        action: GameAction | None = self._catalog.get(name)
        if action is None or not action.parameters or "choice" not in arguments:
            return arguments
        (parameter,) = action.parameters
        return {parameter: arguments["choice"]}

    def phrases(self) -> list[str]:
        return self._keywords.phrases()

    def unload(self) -> None:
        self._agent.unload()
