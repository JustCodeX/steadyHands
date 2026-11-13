"""A Needle model with a fixed set of tools: text in, one tool call out."""
from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .runtime import load_cactus

log = logging.getLogger(__name__)

Record = Callable[[str, dict], None]


@dataclass
class ToolCall:
    name: str
    arguments: dict = field(default_factory=dict)
    confidence: float = 1.0


def plain_tool(name: str, description: str, record: Record) -> Callable:
    """A tool without parameters."""

    def tool():
        record(name, {})

    tool.__name__ = tool.__qualname__ = name
    tool.__doc__ = description
    return tool


def choice_tool(name: str, description: str, parameter_help: str, choices: Sequence[str], record: Record) -> Callable:
    """A tool with one parameter, `choice`, that takes one of `choices`."""

    def tool(choice: str):
        record(name, {"choice": choice})

    tool.__name__ = tool.__qualname__ = name
    tool.__annotations__ = {"choice": Literal[tuple(choices)]}
    tool.__doc__ = f"{description}\n\nArgs:\n    choice: {parameter_help}\n"
    return tool


class NeedleAgent:
    """The model picks at most one of the tools for a piece of text.

    The runtime executes the tool it picks, so each tool just records that it
    was called (`build_tools` gets the recorder). A call the runtime holds
    back for low confidence is never executed, and so counts as no call."""

    def __init__(
        self,
        weights: str | Path,
        system: str,
        build_tools: Callable[[Record], list[Callable]],
        min_confidence: float = 0.1,
    ) -> None:
        self.weights = Path(weights)
        self.system = system
        self.min_confidence = min_confidence
        self._build_tools = build_tools
        self._agent = None
        self._calls: list[tuple[str, dict]] = []

    def load(self) -> None:
        """Load the model. Raises if the package or the weights are missing."""
        if self._agent is not None:
            return
        if not self.weights.is_file():
            raise FileNotFoundError(f"Needle weights not found at {self.weights}")
        cactus = load_cactus()
        tools = [cactus.tool(fn) for fn in self._build_tools(self._record)]
        self._agent = cactus.Cactus(tools=tools, system=self.system, weights=str(self.weights))
        log.info("Needle loaded from %s with %d tools", self.weights.name, len(tools))

    def _record(self, name: str, arguments: dict) -> None:
        self._calls.append((name, dict(arguments)))

    def call(self, text: str) -> ToolCall | None:
        """The tool call the model makes for `text`, or None: no tool fits,
        the model was not sure enough, or it called for two different things."""
        self.load()
        self._agent.reset()  # each text stands alone; old context makes the model refuse
        self._calls.clear()
        result = self._agent.run(text)
        calls = list(self._calls)
        self._calls.clear()
        if not calls or any(c != calls[0] for c in calls):
            return None
        try:
            confidence = float(result["confidence"])
        except (KeyError, TypeError, ValueError):
            confidence = 1.0
        if confidence < self.min_confidence:
            return None
        name, arguments = calls[0]
        return ToolCall(name=name, arguments=arguments, confidence=min(1.0, confidence))

    def unload(self) -> None:
        self._agent = None
