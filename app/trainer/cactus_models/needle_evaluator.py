"""Quiz answers that name no option in so many words:
"the thing you cut with" -> scalpel."""
from __future__ import annotations

import logging
from pathlib import Path

from ..quiz.evaluator import AnswerEvaluator, KeywordEvaluator, Verdict
from ..quiz.question import Question
from . import needle_agent
from .needle_agent import NeedleAgent, Record, choice_tool

log = logging.getLogger(__name__)


def answer_tool(question: Question, record: Record):
    options = "; ".join(f"{option} ({', '.join(phrases[:3])})" for option, phrases in question.options.items())
    return choice_tool(
        "answer",
        "Record which of the possible answers the player gave. Do not call this if the player named none of them.",
        f"the answer the player means. Possible answers: {options}",
        list(question.options),
        record,
    )


class NeedleEvaluator(AnswerEvaluator):
    """The keyword evaluator first. Needle only when the answer names none of
    the options' phrases. An answer that names two options stays unclear:
    there the recognisers disagreed, or the player did, and a guess could
    turn a right answer into a wrong one."""

    def __init__(self, weights: str | Path, min_confidence: float = 0.1, agent_factory=None) -> None:
        self.weights = Path(weights)
        self.min_confidence = min_confidence
        self._keywords = KeywordEvaluator()
        self._agent_factory = agent_factory or self._make_agent
        self._question_id: str | None = None
        self._agent: NeedleAgent | None = None
        if agent_factory is None:
            # fail at start-up, where the caller can fall back, not at the first question
            if not self.weights.is_file():
                raise FileNotFoundError(f"Needle weights not found at {self.weights}")
            needle_agent.load_cactus()

    def _make_agent(self, question: Question) -> NeedleAgent:
        system = f"quiz in a surgical training game. The player was asked: {question.text} locale: en-US"
        return NeedleAgent(self.weights, system, lambda record: [answer_tool(question, record)], self.min_confidence)

    def prepare(self, question: Question) -> None:
        """Build the agent for this question while the patient is still asking it."""
        if self._question_id == question.id and self._agent is not None:
            return
        self._question_id, self._agent = question.id, None
        try:
            agent = self._agent_factory(question)
            agent.load()
            self._agent = agent
        except Exception as exc:
            log.error("Needle unavailable for this question (%s); keyword evaluation only", exc)

    def evaluate(self, question: Question, text: str) -> Verdict:
        verdict = self._keywords.evaluate(question, text)
        if verdict.choice is not None or verdict.named or not text.strip():
            return verdict
        self.prepare(question)
        if self._agent is None:
            return verdict
        try:
            call = self._agent.call(text)
        except Exception:
            log.exception("Needle failed on an answer; keyword result used")
            return verdict
        choice = call.arguments.get("choice") if call is not None else None
        if choice not in question.options:
            return verdict
        return Verdict(choice, call.confidence)

    def unload(self) -> None:
        self._agent = None
        self._question_id = None
