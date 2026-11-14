"""The vitals monitor: oxygen saturation, depth of anaesthesia, blood pressure.

At random times one value starts to drift. The surgeon tells the nurse what
to give; the right treatment stops the drift and the value recovers, a wrong
one only brings its side effects, and the drifting value gets worse on top.
Every treatment acts on all three values (a small physiology table, not
special rules), so a wrong instruction harms the patient by itself.

Medically simplified on purpose: adrenaline stands in for whatever
vasopressor an anaesthetist would choose, and the numbers are rounded.
"""
from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from ..core.config import VitalsConfig


class VitalStatus(Enum):
    NORMAL = "normal"
    ALARM = "alarm"
    CRITICAL = "critical"


@dataclass(frozen=True)
class VitalSpec:
    key: str
    label: str  # as on the monitor
    unit: str
    normal: float
    alarm: float  # the alarm starts beyond this value
    critical: float
    worse: int  # -1: falling is bad, +1: rising is bad
    treatment: str  # the command word that fixes it
    settle_per_s: float  # how fast the body returns to normal on its own, outside an episode
    low: float
    high: float

    def status(self, value: float) -> VitalStatus:
        if (value - self.critical) * self.worse > 0:
            return VitalStatus.CRITICAL
        if (value - self.alarm) * self.worse > 0:
            return VitalStatus.ALARM
        return VitalStatus.NORMAL


SPECS: dict[str, VitalSpec] = {
    "spo2": VitalSpec("spo2", "SpO2", "%", 98, 92, 86, -1, "oxygen", 0.6, 60, 100),
    "bis": VitalSpec("bis", "BIS", "", 45, 62, 75, +1, "anaesthesia", 1.0, 20, 99),
    "bp": VitalSpec("bp", "BP", "mmHg", 120, 90, 75, -1, "adrenaline", 2.0, 40, 200),
}
KINDS = tuple(SPECS)

# Treatment -> change of each value when it is given (the physiology table).
# Positive numbers raise the value.
EFFECTS: dict[str, dict[str, float]] = {
    "oxygen": {},
    "anaesthesia": {"bp": -12.0},  # deeper anaesthesia lowers the blood pressure
    "adrenaline": {"bis": +8.0},  # and makes the patient lighter (and the pulse jump, see GameEngine)
}
# How far a drifting value jumps the wrong way when the instruction was wrong.
WRONG_JUMP: dict[str, float] = {"spo2": 3.0, "bis": 6.0, "bp": 10.0}


class TreatmentResult(Enum):
    CORRECT = "correct"  # it fixed a value that was in trouble
    WRONG = "wrong"  # a value was in trouble, this was not its treatment
    UNNEEDED = "unneeded"  # nothing was in trouble
    ALREADY = "already"  # its value is already recovering from this treatment: no effect, not counted


@dataclass(frozen=True)
class TreatmentOutcome:
    result: TreatmentResult
    treatment: str
    vital: str = ""  # the value it fixed (correct) or the one still in trouble (wrong)


@dataclass(frozen=True)
class VitalsEvent:
    kind: str  # "alarm" | "reminder" | "crisis" | "stable"
    vital: str
    value: int


class Vital:
    def __init__(self, spec: VitalSpec) -> None:
        self.spec = spec
        self.reset()

    def reset(self) -> None:
        self.value = float(self.spec.normal)
        self.drift = 0.0  # units per second, in the "worse" direction; 0 = not drifting
        self.recover_per_s = 0.0  # > 0 while it comes back after a treatment
        self.trend = 0  # -1, 0, +1: where the value went in the last update

    @property
    def status(self) -> VitalStatus:
        return self.spec.status(self.value)

    @property
    def recovering(self) -> bool:
        return self.recover_per_s > 0

    @property
    def in_trouble(self) -> bool:
        """Drifting, or beyond the alarm line and not already coming back."""
        return self.drift > 0 or (self.status is not VitalStatus.NORMAL and not self.recovering)

    def change(self, delta: float) -> None:
        self.value = min(self.spec.high, max(self.spec.low, self.value + delta))

    def update(self, dt: float) -> None:
        before = self.value
        gap = self.spec.normal - self.value
        if self.drift > 0:
            self.change(self.spec.worse * self.drift * dt)
        elif self.recover_per_s > 0 or abs(gap) > 1e-6:
            rate = self.recover_per_s or self.spec.settle_per_s
            step = min(abs(gap), rate * dt)
            self.change(step if gap > 0 else -step)
            if abs(self.spec.normal - self.value) < 1e-6:
                self.recover_per_s = 0.0
        diff = self.value - before
        self.trend = 0 if abs(diff) < 1e-9 else (1 if diff > 0 else -1)


class VitalsMonitor:
    """One episode at a time. `update` returns what the nurse should say."""

    def __init__(self, cfg: VitalsConfig, rng: random.Random | None = None) -> None:
        self.cfg = cfg
        self._rng = rng or random.Random()
        self.vitals: dict[str, Vital] = {k: Vital(s) for k, s in SPECS.items()}
        self.reset(0, ())

    # --- round ---------------------------------------------------------------

    def reset(self, episodes: int, kinds: Sequence[str]) -> None:
        unknown = [k for k in kinds if k not in SPECS]
        if unknown:
            raise ValueError(f"unknown vital: {unknown}")
        for v in self.vitals.values():
            v.reset()
        self._limit = episodes if self.cfg.enabled else 0
        self._kinds = tuple(kinds) or KINDS
        self._started = 0
        self._next_in = self.cfg.first_after_s
        self._alarmed: dict[str, float] = {}  # vital -> seconds since its alarm
        self._reminded: set[str] = set()
        self._critical_for: dict[str, float] = {}
        self.episode: str = ""  # the vital that is drifting, "" if none
        self.correct = 0
        self.wrong = 0
        self.crises = 0

    @property
    def active(self) -> bool:
        """This round has episodes at all."""
        return self._limit > 0

    def alarm_open(self) -> bool:
        """A value is in trouble and waits for an instruction."""
        return any(v.in_trouble for v in self.vitals.values())

    def alarm_raised(self) -> bool:
        """The nurse has announced a value that still waits for its treatment.
        (A value can drift for a few seconds before it crosses the alarm line;
        the player is only asked for an instruction once she said so.)"""
        return any(key in self._alarmed and self.vitals[key].in_trouble for key in self.vitals)

    def troubled(self) -> list[str]:
        return [k for k, v in self.vitals.items() if v.in_trouble]

    # --- time ----------------------------------------------------------------

    def update(self, dt: float, time_left: float, blocked: bool = False) -> list[VitalsEvent]:
        """Advance by `dt`. `blocked`: something else waits for an answer (a
        quiz question), so no new episode starts."""
        events: list[VitalsEvent] = []
        for v in self.vitals.values():
            v.update(dt)
        self._maybe_start(dt, time_left, blocked)
        for key, v in self.vitals.items():
            status = v.status
            if status is VitalStatus.NORMAL and v.drift == 0:
                if key in self._alarmed:
                    del self._alarmed[key]
                    self._reminded.discard(key)
                    self._critical_for.pop(key, None)
                    events.append(VitalsEvent("stable", key, round(v.value)))
                continue
            if status is VitalStatus.NORMAL:
                continue  # drifting, not yet beyond the alarm line
            if key not in self._alarmed:
                self._alarmed[key] = 0.0
                events.append(VitalsEvent("alarm", key, round(v.value)))
                continue
            self._alarmed[key] += dt
            if key not in self._reminded and self._alarmed[key] >= self.cfg.reminder_s:
                self._reminded.add(key)
                events.append(VitalsEvent("reminder", key, round(v.value)))
            if status is VitalStatus.CRITICAL:
                self._critical_for[key] = self._critical_for.get(key, 0.0) + dt
                if self._critical_for[key] >= self.cfg.crisis_after_s:
                    events.append(VitalsEvent("crisis", key, round(v.value)))
                    self._crisis(key)
            else:
                self._critical_for.pop(key, None)
        return events

    def _maybe_start(self, dt: float, time_left: float, blocked: bool) -> None:
        if self.episode or self._started >= self._limit or self.alarm_open():
            return
        self._next_in -= dt
        if self._next_in > 0 or blocked or time_left < self.cfg.min_time_left_s:
            return
        key = self._rng.choice(self._kinds)
        spec = SPECS[key]
        span = abs(spec.normal - spec.critical)
        seconds = self.cfg.drift_to_critical_s * self._rng.uniform(0.8, 1.2)
        self.vitals[key].drift = span / seconds
        self.vitals[key].recover_per_s = 0.0
        self.episode = key
        self._started += 1

    def _end_episode(self, key: str) -> None:
        if self.episode == key:
            self.episode = ""
            lo, hi = self.cfg.interval_s
            self._next_in = self._rng.uniform(lo, hi)

    def _crisis(self, key: str) -> None:
        """The value stayed critical: the team steps in, it costs a life."""
        self.crises += 1
        v = self.vitals[key]
        v.drift = 0.0
        v.recover_per_s = abs(v.spec.normal - v.value) / self.cfg.recover_s
        self._critical_for.pop(key, None)
        self._end_episode(key)

    # --- instructions ----------------------------------------------------------

    def treat(self, treatment: str) -> TreatmentOutcome:
        if treatment not in EFFECTS:
            raise ValueError(f"unknown treatment: {treatment}")
        troubled = self.troubled()
        fixed = next((k for k in troubled if SPECS[k].treatment == treatment), "")
        if not fixed:
            again = next((k for k, v in self.vitals.items() if v.recovering and SPECS[k].treatment == treatment), "")
            if again:  # said twice, or heard twice: harmless
                return TreatmentOutcome(TreatmentResult.ALREADY, treatment, again)
        for key, delta in EFFECTS[treatment].items():
            self.vitals[key].change(delta)
        if fixed:
            v = self.vitals[fixed]
            v.drift = 0.0
            v.recover_per_s = max(1e-3, abs(v.spec.normal - v.value)) / self.cfg.recover_s
            self._end_episode(fixed)
            self.correct += 1
            return TreatmentOutcome(TreatmentResult.CORRECT, treatment, fixed)
        self.wrong += 1
        if troubled:
            worst = self.episode if self.episode in troubled else troubled[0]
            v = self.vitals[worst]
            v.change(v.spec.worse * WRONG_JUMP[worst])
            return TreatmentOutcome(TreatmentResult.WRONG, treatment, worst)
        return TreatmentOutcome(TreatmentResult.UNNEEDED, treatment)
