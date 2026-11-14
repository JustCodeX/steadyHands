"""A Needle model with a fixed set of tools: text in, one tool call out."""
from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .runtime import load_cactus

log = logging.getLogger(__name__)

RUNTIME_GATE = 0.1  # the runtime moves calls below this confidence to "suppressed_calls"


@dataclass
class ToolCall:
    name: str
    arguments: dict = field(default_factory=dict)
    confidence: float = 1.0


def tool_schema(name: str, description: str, parameters: dict[str, tuple[Sequence[str], str]] | None = None) -> dict:
    """A tool in the runtime's flat JSON form. `parameters`: name -> (allowed values, help text)."""
    properties = {p: {"type": "string", "enum": list(values), "description": help_text} for p, (values, help_text) in (parameters or {}).items()}
    return {
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": properties, "required": list(properties)},
    }


class NeedleAgent:
    """The model picks at most one of the tools for a piece of text.

    Uses `complete()`, which returns the calls the model proposes without
    executing anything. (`run()` would execute them and then run the model a
    second time on their results, which doubles the latency and reports the
    second turn's confidence.)

    Rungs and other non-published weights run in a worker process of the
    runtime's own, so each agent costs one process (about 90 MB on the board).
    """

    def __init__(
        self,
        weights: str | Path,
        system: str,
        tools: Sequence[dict] | Callable[[], Sequence[dict]],
        min_confidence: float = RUNTIME_GATE,
    ) -> None:
        self.weights = Path(weights)
        self.system = system
        self.min_confidence = min_confidence
        self._tools = tools
        self._agent = None
        self._warned_uncalibrated = False
        self.peak_ram_mb = 0.0  # the most the engine reported for one call (its "peak_ram_mb")

    def load(self) -> None:
        """Load the model. Raises if the package or the weights are missing."""
        if self._agent is not None:
            return
        if not self.weights.is_file():
            raise FileNotFoundError(f"Needle weights not found at {self.weights}")
        cactus = load_cactus()
        tools = list(self._tools() if callable(self._tools) else self._tools)
        # auto_date off: the game has no use for the date, and it costs prompt tokens on every call
        self._agent = cactus.Cactus(tools=json.dumps(tools), system=self.system, weights=str(self.weights), auto_date=False)
        log.info("Needle loaded from %s with %d tools", self.weights.name, len(tools))

    def call(self, text: str) -> ToolCall | None:
        """The tool call the model makes for `text`, or None: no tool fits,
        the model was not sure enough, or it called for two different things."""
        self.load()
        self._agent.reset()  # each text stands alone; old context makes the model refuse
        result = self._agent.complete(text)
        self.peak_ram_mb = max(self.peak_ram_mb, float(result.get("peak_ram_mb") or 0.0))
        confidence = result.get("confidence")
        calls = list(result.get("function_calls") or [])
        if not calls and self.min_confidence < RUNTIME_GATE:
            calls = list(result.get("suppressed_calls") or [])
        calls = [(str(c.get("name")), dict(c.get("arguments") or {})) for c in calls]
        if not calls or any(c != calls[0] for c in calls):
            return None
        if confidence is None:  # weights without a confidence head (e.g. LoRA builds): no gate possible
            if not self._warned_uncalibrated:
                log.warning("%s reports no confidence; every call counts", self.weights.name)
                self._warned_uncalibrated = True
            confidence = 1.0
        confidence = float(confidence)
        if confidence < self.min_confidence:
            return None
        name, arguments = calls[0]
        return ToolCall(name=name, arguments=arguments, confidence=min(1.0, confidence))

    def calls(self, text: str) -> list[ToolCall]:
        """Every call the model makes for `text` (an order can hold two).

        A call with an argument the runtime flags as ungrounded (a number
        that is not in the text, i.e. invented) is dropped: "Propofol." or
        "his sats look good now" give no order. Two calls to the same tool
        are a correction ("20, no wait, 30"): the last one counts."""
        self.load()
        self._agent.reset()  # each text stands alone; old context makes the model refuse
        result = self._agent.complete(text)
        self.peak_ram_mb = max(self.peak_ram_mb, float(result.get("peak_ram_mb") or 0.0))
        calls = list(result.get("function_calls") or [])
        if not calls and self.min_confidence < RUNTIME_GATE:
            calls = list(result.get("suppressed_calls") or [])
        confidence = self._confidence(result)
        if confidence < self.min_confidence:
            return []
        ungrounded = {str(path) for path in (result.get("validation") or {}).get("ungrounded") or []}
        kept: dict[str, ToolCall] = {}
        for c in calls:
            name = str(c.get("name"))
            if any(path.startswith(name + ".") for path in ungrounded):
                continue
            kept.pop(name, None)  # a later call to the same tool replaces the earlier one
            kept[name] = ToolCall(name=name, arguments=dict(c.get("arguments") or {}), confidence=min(1.0, confidence))
        return list(kept.values())

    def _confidence(self, result: dict) -> float:
        confidence = result.get("confidence")
        if confidence is None:  # weights without a confidence head (e.g. LoRA builds): no gate possible
            if not self._warned_uncalibrated:
                log.warning("%s reports no confidence; every call counts", self.weights.name)
                self._warned_uncalibrated = True
            return 1.0
        return float(confidence)

    def unload(self) -> None:
        agent, self._agent = self._agent, None
        if agent is not None:
            agent.close()  # ends the worker process
