"""Decides when the patient asks a question and keeps the answer window."""
from __future__ import annotations

import random
from enum import Enum

from ..core.config import QuizConfig
from ..core.events import AnswerEvent
from ..quiz.question import Question, QuestionBank


class QuizStep(Enum):
    NONE = "none"
    ASK = "ask"  # a new question is open: `pending` holds it
    TIMEOUT = "timeout"  # the window ran out: `last` holds the question


class QuizOutcome(Enum):
    IGNORED = "ignored"  # no open question, or an answer to an older one
    CORRECT = "correct"
    WRONG = "wrong"
    UNCLEAR = "unclear"  # ask the player to say it again


class QuizDirector:
    def __init__(self, cfg: QuizConfig, bank: QuestionBank | None = None, rng: random.Random | None = None) -> None:
        self.cfg = cfg
        self.bank = bank or QuestionBank()
        self._rng = rng or random.Random()
        self._deck: list[Question] = []
        self.pending: Question | None = None
        self.last: Question | None = None
        self.reset(0)

    def reset(self, limit: int, topics: list[str] | None = None) -> None:
        """Start a round that asks at most `limit` questions."""
        self.pending = None
        self.last = None
        self.correct = 0
        self.wrong = 0
        self._limit = limit if self.cfg.enabled else 0
        self._topics = topics
        self._asked = 0
        self._unclear = 0
        self._next_in = self.cfg.first_after_s
        self._window_left = 0.0

    # --- time ------------------------------------------------------------------

    def tick(self, dt: float, speaking: bool, time_left: float) -> QuizStep:
        """Call once per frame of a running round. `speaking` is True while a
        patient line plays: the microphone is off then, so the window waits."""
        if self.pending is not None:
            if not speaking:
                self._window_left -= dt
            if self._window_left <= 0:
                self.wrong += 1
                self._close()
                return QuizStep.TIMEOUT
            return QuizStep.NONE
        if self._asked >= self._limit:
            return QuizStep.NONE
        self._next_in -= dt
        if self._next_in > 0 or speaking or time_left < self.cfg.min_time_left_s:
            return QuizStep.NONE
        question = self._draw()
        if question is None:
            self._limit = 0
            return QuizStep.NONE
        self.pending = question
        self._asked += 1
        self._unclear = 0
        self._window_left = self.cfg.answer_window_s
        return QuizStep.ASK

    def window_fraction(self) -> float:
        if self.pending is None:
            return 0.0
        return max(0.0, min(1.0, self._window_left / max(1e-6, self.cfg.answer_window_s)))

    # --- answers ---------------------------------------------------------------

    def answer(self, ev: AnswerEvent) -> QuizOutcome:
        if self.pending is None or ev.question_id not in ("", self.pending.id):
            return QuizOutcome.IGNORED
        if ev.unclear:
            self._unclear += 1
            if self._unclear < self.cfg.unclear_limit:
                return QuizOutcome.UNCLEAR
        elif ev.correct:
            self.correct += 1
            self._close()
            return QuizOutcome.CORRECT
        self.wrong += 1
        self._close()
        return QuizOutcome.WRONG

    def abandon(self) -> bool:
        """Drop the open question without counting it (the round ended).
        Returns True if there was one."""
        if self.pending is None:
            return False
        self._close()
        return True

    def _close(self) -> None:
        self.last = self.pending
        self.pending = None
        self._next_in = self.cfg.interval_s

    # --- choosing --------------------------------------------------------------

    def _draw(self) -> Question | None:
        """A random question, never the same one twice until all were asked."""
        candidates = self.bank.for_topics(self._topics)
        if not candidates:
            return None
        ids = {q.id for q in candidates}
        self._deck = [q for q in self._deck if q.id in ids]
        if not self._deck:
            self._deck = list(candidates)
            self._rng.shuffle(self._deck)
        return self._deck.pop()
