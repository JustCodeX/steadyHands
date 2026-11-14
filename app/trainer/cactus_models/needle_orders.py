"""The nurse's orders in free speech: "give him 30 milligrams of propofol"
-> propofol, 30. Needle reads the drug and the amount.

Needle only decides these orders. Every older command stays on the Vosk
grammar (docs/needle-integration.md)."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from ..game.actions import MODEL_ACTIONS, ActionCatalog
from ..voice.interpreter import Match, OrderInterpreter
from ..voice.named_orders import NamedOrders
from .needle_agent import RUNTIME_GATE, NeedleAgent

log = logging.getLogger(__name__)

SYSTEM = "device: anaesthesia station in a surgical training game; the user is the surgeon giving orders to the nurse; locale: en-US"


class NeedleOrders(OrderInterpreter):
    """A drug must be named; Needle reads its amount.

    - The model runs only when a drug is named (the tools' triggers,
      `require_trigger`): other speech costs no model run (criterion C3).
    - An amount the model invents (not in the text) is dropped by
      NeedleAgent; a drug named without a usable amount is an order at the
      standard dose (amount None), as is every named drug when the model fails.
    - Two drugs in one sentence are two orders."""

    def __init__(
        self,
        treatments: dict[str, list[str]],
        weights: str | Path,
        catalog: ActionCatalog | None = None,
        min_confidence: float = RUNTIME_GATE,
        agent: NeedleAgent | None = None,
        require_trigger: bool = True,
    ) -> None:
        self._names = NamedOrders(treatments)
        self._catalog = catalog or ActionCatalog(MODEL_ACTIONS)
        self._agent = agent or NeedleAgent(weights, SYSTEM, self._catalog.schemas, min_confidence)
        self.require_trigger = require_trigger
        self._triggers = [re.compile(t, re.IGNORECASE) for a in self._catalog.actions() for t in a.triggers]
        self._agent.load()  # fail at start-up, where the caller can fall back

    @property
    def agent(self) -> NeedleAgent:
        return self._agent

    def orders(self, text: str) -> list[Match]:
        if not text.strip():
            return []
        named = self._names.orders(text)
        if self.require_trigger and not self.triggered(text):
            return named  # a drug named outright still counts (standard dose); otherwise nothing
        try:
            calls = self._agent.calls(self.sentence(text))
        except Exception:
            log.exception("Needle failed; the drugs named get the standard dose")
            return named
        orders: list[Match] = []
        for call in calls:
            word = self._catalog.command_word(call.name, call.arguments)
            if word is not None and word not in {o.word for o in orders}:
                orders.append(Match(word=word, score=call.confidence, amount=self._catalog.amount(call.name, call.arguments)))
        given = {o.word for o in orders}
        return orders + [n for n in named if n.word not in given]

    @staticmethod
    def sentence(text: str) -> str:
        """Whistle often leaves off the final full stop; the model reads the
        amount more reliably with it ("Push 10 micrograms of adrenaline")."""
        text = text.strip()
        return text if text[-1:] in ".!?" else text + "."

    def triggered(self, text: str) -> bool:
        return any(t.search(text) for t in self._triggers)

    def phrases(self) -> list[str]:
        return self._names.phrases()

    def unload(self) -> None:
        self._agent.unload()
