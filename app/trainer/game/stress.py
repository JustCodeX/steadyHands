"""Stress: wrong quiz answers make the rest of the round harder."""
from __future__ import annotations

from ..core.config import QuizConfig


class Stress:
    """A level from 0 to `max_stress`. Each level speeds up the instrument
    (harder to steer) and the bleeding timers."""

    def __init__(self, cfg: QuizConfig) -> None:
        self.cfg = cfg
        self.level = 0

    def reset(self) -> None:
        self.level = 0

    def worse(self) -> None:
        self.level = min(self.cfg.max_stress, self.level + 1)

    def better(self) -> None:
        self.level = max(0, self.level - 1)

    @property
    def speed_factor(self) -> float:
        return 1.0 + self.level * self.cfg.stress_speed_step

    @property
    def bleed_factor(self) -> float:
        return 1.0 + self.level * self.cfg.stress_bleed_step
