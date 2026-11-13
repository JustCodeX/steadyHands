"""Training metrics for one round."""
from __future__ import annotations

import math
import time

from ..core.events import RoundResult


class TrainingMetrics:
    # Jitter (RMS of tilt change per frame, in g) that maps to a steadiness of 0.
    JITTER_FOR_ZERO = 0.12

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.started_t: float | None = None
        self.ended_t: float | None = None
        self.contacts = 0
        self.calls_correct = 0
        self.calls_wrong = 0
        self.steady_uses = 0
        self.questions_correct = 0
        self.questions_wrong = 0
        self.treatments_correct = 0
        self.treatments_wrong = 0
        self.crises = 0
        self._jitter_sq_sum = 0.0
        self._jitter_n = 0
        self._last_tilt: tuple[float, float] | None = None
        self._last_moving = False

    def start(self, now: float | None = None) -> None:
        self.reset()
        self.started_t = now if now is not None else time.monotonic()

    def end(self, now: float | None = None) -> None:
        self.ended_t = now if now is not None else time.monotonic()

    def elapsed(self, now: float | None = None) -> float:
        if self.started_t is None:
            return 0.0
        end = self.ended_t if self.ended_t is not None else (now if now is not None else time.monotonic())
        return max(0.0, end - self.started_t)

    def add_tilt(self, tilt_x: float, tilt_y: float, moving: bool) -> None:
        """Feed every input frame. Jitter counts only while the player keeps
        moving: the first frame after standing still is the start of a move,
        not shakiness."""
        if self._last_tilt is not None and moving and self._last_moving:
            dx = tilt_x - self._last_tilt[0]
            dy = tilt_y - self._last_tilt[1]
            self._jitter_sq_sum += dx * dx + dy * dy
            self._jitter_n += 1
        self._last_tilt = (tilt_x, tilt_y)
        self._last_moving = moving

    def jitter_rms(self) -> float:
        if self._jitter_n == 0:
            return 0.0
        return math.sqrt(self._jitter_sq_sum / self._jitter_n)

    def steadiness(self) -> float:
        """0..100: 100 is perfectly smooth."""
        score = 100.0 * (1.0 - self.jitter_rms() / self.JITTER_FOR_ZERO)
        return max(0.0, min(100.0, score))

    def result(self, level_name: str, won: bool) -> RoundResult:
        return RoundResult(
            level_name=level_name,
            won=won,
            time_s=round(self.elapsed(), 1),
            contacts=self.contacts,
            steadiness=round(self.steadiness(), 1),
            calls_correct=self.calls_correct,
            calls_wrong=self.calls_wrong,
            steady_uses=self.steady_uses,
            questions_correct=self.questions_correct,
            questions_wrong=self.questions_wrong,
            treatments_correct=self.treatments_correct,
            treatments_wrong=self.treatments_wrong,
            crises=self.crises,
        )
