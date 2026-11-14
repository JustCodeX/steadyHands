"""The patient: heart rate rises with every contact and settles again.

A life is lost by a wall contact or by a crisis on the vitals monitor; the
two are counted apart for the training feedback."""
from __future__ import annotations


class Patient:
    def __init__(self, base_rate: int = 72, per_contact: int = 22, decay_per_s: float = 4.0) -> None:
        self.base_rate = base_rate
        self.per_contact = per_contact
        self.decay_per_s = decay_per_s
        self.heart_rate = float(base_rate)
        self.contacts = 0
        self.crises = 0

    def reset(self) -> None:
        self.heart_rate = float(self.base_rate)
        self.contacts = 0
        self.crises = 0

    @property
    def lives_lost(self) -> int:
        return self.contacts + self.crises

    def on_crisis(self) -> None:
        self.crises += 1
        self.heart_rate = min(180.0, self.heart_rate + self.per_contact)

    def on_contact(self) -> None:
        self.contacts += 1
        self.heart_rate = min(180.0, self.heart_rate + self.per_contact)

    def startle(self, bpm: int) -> None:
        """The heart rate jumps without a contact (a wrong quiz answer)."""
        self.heart_rate = min(180.0, self.heart_rate + bpm)

    def update(self, dt: float) -> None:
        if self.heart_rate > self.base_rate:
            self.heart_rate = max(float(self.base_rate), self.heart_rate - self.decay_per_s * dt)

    def awake(self, max_lives: int) -> bool:
        return self.lives_lost >= max_lives
