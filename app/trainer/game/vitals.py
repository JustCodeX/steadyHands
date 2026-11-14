"""The vitals monitor: oxygen saturation, depth of anaesthesia, blood pressure.

At random times one value goes wrong. The surgeon orders a drug and an
amount ("Propofol 40"); the nurse gives exactly that, and the monitor
answers in proportion. The model is linear, so the monitor tells the
player the dose: each tile shows its dose card ("10 mg: -6"), and the
deviation divided by it is the amount the patient needs.

- Too little helps part of the way: the value settles short, still in
  alarm, and the nurse says where it stands. Give more (titration).
- Too much overshoots into the opposite alarm (too deep, pressure too high)
  for a while; far over and critical for a few seconds is a crisis.
- The wrong drug, or one nobody needed, brings only its own effects.
- Every drug also has side effects on the other values (propofol lowers the
  blood pressure, adrenaline lightens the anaesthesia and raises the pulse).
- Oxygen is a setting (FiO2 %), not a dose: the saturation recovers once
  the setting covers what the episode needs. Far more than needed is
  counted as too much. The nurse weans it back once the patient is stable.

Medically simplified on purpose: adrenaline stands in for whatever
vasopressor an anaesthetist would choose, the doses and gains are rounded
for a 60-second round, and the patient's need is drawn at random.
"""
from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, field
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
    worse: int  # the direction an episode drives it: -1 falling, +1 rising
    alarm: float  # beyond this, on the episode's side, the alarm starts
    critical: float
    treatment: str  # the drug (command word) that fixes an episode
    drug_unit: str  # what the amount is in: "%", "mg", "µg"
    gain: float  # value change per unit of drug (towards normal during an episode)
    need: tuple[float, float]  # range of the amount an episode needs
    settle_per_s: float  # how fast the body returns to normal on its own
    low: float
    high: float
    over_alarm: float | None = None  # the opposite side: too deep, too high (None: none)
    over_critical: float | None = None

    def status(self, value: float) -> VitalStatus:
        if (value - self.critical) * self.worse > 0:
            return VitalStatus.CRITICAL
        if self.over_critical is not None and (value - self.over_critical) * self.worse < 0:
            return VitalStatus.CRITICAL
        if (value - self.alarm) * self.worse > 0:
            return VitalStatus.ALARM
        if self.over_alarm is not None and (value - self.over_alarm) * self.worse < 0:
            return VitalStatus.ALARM
        return VitalStatus.NORMAL

    def over(self, value: float) -> bool:
        """Beyond normal on the opposite side of an episode (too deep, too high)."""
        return (value - self.normal) * self.worse < 0 and self.status(value) is not VitalStatus.NORMAL

    def dose_card(self) -> str:
        """What 10 units do, for the tile: the rule the player doses by."""
        change = round(10 * self.gain * -self.worse)
        sign = "+" if change > 0 else "−"
        if self.key == "spo2":
            return f"O2 +10%: {sign}{abs(change)}"
        return f"10 {self.drug_unit}: {sign}{abs(change)}"


SPECS: dict[str, VitalSpec] = {
    # FiO2 needed 52-95 %; at 30 % the saturation sits 98 - 0.3 x (need - FiO2)
    "spo2": VitalSpec("spo2", "SpO2", "%", 98, -1, 92, 86, "oxygen", "%", 0.3, (52, 95), 0.6, 60, 100),
    # an episode needs 30-80 mg; untreated BIS 63-93
    "bis": VitalSpec("bis", "BIS", "", 45, +1, 62, 75, "propofol", "mg", 0.6, (30, 80), 1.0, 10, 99, over_alarm=30, over_critical=20),
    # an episode needs 16-37 µg; untreated systolic 88-46
    "bp": VitalSpec("bp", "BP", "mmHg", 120, -1, 90, 75, "adrenaline", "µg", 2.0, (16, 37), 2.0, 40, 220, over_alarm=160, over_critical=180),
}
KINDS = tuple(SPECS)
DRUG_OF = {s.treatment: s.key for s in SPECS.values()}  # drug -> the value it treats

# Side effects per unit of drug: the change of the other values.
SIDE_EFFECTS: dict[str, dict[str, float]] = {
    "oxygen": {},
    "propofol": {"bp": -0.3},  # deeper anaesthesia lowers the blood pressure
    "adrenaline": {"bis": +0.3},  # and makes the patient lighter (the pulse: GameEngine)
}
# How far a wrong drug makes the episode worse, in the episode drug's units.
WRONG_JUMP: dict[str, float] = {"spo2": 10.0, "bis": 10.0, "bp": 5.0}
FIO2_TOO_MUCH = 30.0  # FiO2 this far above the need counts as too much oxygen


class TreatmentResult(Enum):
    CORRECT = "correct"  # the value settles inside its band
    PARTIAL = "partial"  # not enough: it settles short, still in alarm
    OVERDOSE = "overdose"  # too much: the opposite alarm, or far more oxygen than needed
    WRONG = "wrong"  # a value was in trouble, this drug was not its treatment
    UNNEEDED = "unneeded"  # nothing was in trouble
    ALREADY = "already"  # the same order again within a moment (heard twice), or oxygen turned down: no effect


@dataclass(frozen=True)
class TreatmentOutcome:
    result: TreatmentResult
    treatment: str
    amount: float
    vital: str = ""  # the value it was meant for (correct, partial, overdose) or the one in trouble (wrong)

    @property
    def counts_right(self) -> bool:
        return self.result is TreatmentResult.CORRECT

    @property
    def counts_wrong(self) -> bool:
        return self.result in (TreatmentResult.OVERDOSE, TreatmentResult.WRONG, TreatmentResult.UNNEEDED)


@dataclass(frozen=True)
class VitalsEvent:
    kind: str  # "alarm" | "over" (opposite-side alarm) | "reminder" | "still" | "crisis" | "stable"
    vital: str
    value: int


@dataclass
class Effect:
    offset: float  # change of the value while it lasts
    left_s: float


@dataclass
class Vital:
    spec: VitalSpec
    value: float = 0.0
    need: float = 0.0  # what the running episode needs (0: none)
    given: float = 0.0  # what was given for it (doses; oxygen uses the monitor's FiO2)
    effects: list[Effect] = field(default_factory=list)
    speed: float = 0.0  # how fast the value moves to its target now
    trend: int = 0

    def __post_init__(self) -> None:
        self.value = float(self.spec.normal)

    def episode_offset(self, fio2: float) -> float:
        """How far the episode alone keeps the value from normal (worse side positive)."""
        s = self.spec
        if self.need <= 0:
            return 0.0
        if s.key == "spo2":
            return s.gain * max(0.0, self.need - fio2)
        return s.gain * (self.need - self.given)

    def target(self, fio2: float) -> float:
        s = self.spec
        value = s.normal + s.worse * self.episode_offset(fio2) + sum(e.offset for e in self.effects)
        return min(s.high, max(s.low, value))

    @property
    def status(self) -> VitalStatus:
        return self.spec.status(self.value)

    def update(self, dt: float, fio2: float) -> None:
        for e in self.effects:
            e.left_s -= dt
        self.effects = [e for e in self.effects if e.left_s > 0]
        target = self.target(fio2)
        rate = max(self.speed, self.spec.settle_per_s)
        step = min(abs(target - self.value), rate * dt)
        before = self.value
        self.value += step if target > self.value else -step
        diff = self.value - before
        self.trend = 0 if abs(diff) < 1e-9 else (1 if diff > 0 else -1)

    def settled(self, fio2: float) -> bool:
        return abs(self.target(fio2) - self.value) < 0.5


class VitalsMonitor:
    """One episode at a time. `update` returns what the nurse should say."""

    def __init__(self, cfg: VitalsConfig, rng: random.Random | None = None) -> None:
        self.cfg = cfg
        self._rng = rng or random.Random()
        self.reset(0, ())

    # --- round ---------------------------------------------------------------

    def reset(self, episodes: int, kinds: Sequence[str]) -> None:
        unknown = [k for k in kinds if k not in SPECS]
        if unknown:
            raise ValueError(f"unknown vital: {unknown}")
        self.vitals: dict[str, Vital] = {k: Vital(s) for k, s in SPECS.items()}
        self.fio2 = float(self.cfg.fio2_baseline)
        self._limit = episodes if self.cfg.enabled else 0
        self._kinds = tuple(kinds) or KINDS
        self._started = 0
        self._next_in = self.cfg.first_after_s
        self._alarmed: dict[str, float] = {}  # vital -> seconds since its alarm (or since the last order for it)
        self._side: dict[str, str] = {}  # vital -> "alarm" or "over": the side it was last announced on
        self._reminded: set[str] = set()
        self._critical_for: dict[str, float] = {}
        self._waiting_still: set[str] = set()  # a partial order: say where it settles
        self._last_order: dict[str, tuple[float, float]] = {}  # drug -> (amount, seconds ago)
        self.episode: str = ""  # the vital with a running episode, "" if none
        self.correct = 0
        self.wrong = 0
        self.overdoses = 0
        self.crises = 0

    @property
    def active(self) -> bool:
        """This round has episodes at all."""
        return self._limit > 0

    def alarm_open(self) -> bool:
        """An episode runs, or a value is outside its band."""
        return bool(self.episode) or any(v.status is not VitalStatus.NORMAL for v in self.vitals.values())

    def alarm_raised(self) -> bool:
        """The nurse has announced the episode and waits for an order."""
        return bool(self.episode) and self._side.get(self.episode) == "alarm"

    # --- time ----------------------------------------------------------------

    def update(self, dt: float, time_left: float, blocked: bool = False) -> list[VitalsEvent]:
        """Advance by `dt`. `blocked`: something else waits for an answer (a
        quiz question), so no new episode starts."""
        events: list[VitalsEvent] = []
        for drug, (amount, ago) in list(self._last_order.items()):
            self._last_order[drug] = (amount, ago + dt)
        for v in self.vitals.values():
            v.update(dt, self.fio2)
        self._wean(dt)
        self._maybe_start(dt, time_left, blocked)
        for key, v in self.vitals.items():
            status, value = v.status, round(v.value)
            if status is VitalStatus.NORMAL:
                self._critical_for.pop(key, None)
                heading_out = v.spec.status(v.target(self.fio2)) is not VitalStatus.NORMAL  # passing through on its way to an overshoot
                if key in self._side and key != self.episode and not heading_out:
                    del self._side[key]
                    self._alarmed.pop(key, None)
                    self._reminded.discard(key)
                    self._waiting_still.discard(key)
                    events.append(VitalsEvent("stable", key, value))
                continue
            side = "over" if v.spec.over(v.value) else "alarm"
            if self._side.get(key) != side:
                self._side[key] = side
                self._alarmed[key] = 0.0
                events.append(VitalsEvent(side, key, value))
            else:
                self._alarmed[key] = self._alarmed.get(key, 0.0) + dt
            if key in self._waiting_still and v.settled(self.fio2):
                self._waiting_still.discard(key)
                events.append(VitalsEvent("still", key, value))
            if key == self.episode and key not in self._reminded and self._alarmed[key] >= self.cfg.reminder_s:
                self._reminded.add(key)
                events.append(VitalsEvent("reminder", key, value))
            if status is VitalStatus.CRITICAL:
                self._critical_for[key] = self._critical_for.get(key, 0.0) + dt
                if self._critical_for[key] >= self.cfg.crisis_after_s:
                    events.append(VitalsEvent("crisis", key, value))
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
        v = self.vitals[key]
        lo, hi = v.spec.need
        v.need = float(round(self._rng.uniform(lo, hi)))
        v.given = 0.0
        v.speed = abs(v.spec.normal - v.spec.critical) / (self.cfg.drift_to_critical_s * self._rng.uniform(0.8, 1.2))
        self.episode = key
        self._started += 1

    def _end_episode(self, key: str) -> None:
        v = self.vitals[key]
        v.need = v.given = 0.0
        if self.episode == key:
            self.episode = ""
            lo, hi = self.cfg.interval_s
            self._next_in = self._rng.uniform(lo, hi)

    def _wean(self, dt: float) -> None:
        """Once the saturation is stable again, the nurse takes the oxygen back down."""
        if self.episode == "spo2" or self.fio2 <= self.cfg.fio2_baseline:
            return
        if self.vitals["spo2"].status is VitalStatus.NORMAL:
            self.fio2 = max(float(self.cfg.fio2_baseline), self.fio2 - self.cfg.wean_per_s * dt)

    def _crisis(self, key: str) -> None:
        """The value stayed critical: the team steps in, it costs a life."""
        self.crises += 1
        v = self.vitals[key]
        v.effects.clear()
        self._critical_for.pop(key, None)
        self._waiting_still.discard(key)
        self._end_episode(key)
        v.speed = abs(v.spec.normal - v.value) / self.cfg.recover_s

    # --- orders ----------------------------------------------------------------

    def order(self, drug: str, amount: float) -> TreatmentOutcome:
        """The nurse gives `amount` of `drug` (oxygen: sets FiO2 to `amount` %)."""
        if drug not in DRUG_OF:
            raise ValueError(f"unknown drug: {drug}")
        last = self._last_order.get(drug)
        if last is not None and last[0] == amount and last[1] < self.cfg.repeat_window_s:
            return TreatmentOutcome(TreatmentResult.ALREADY, drug, amount, DRUG_OF[drug])
        self._last_order[drug] = (amount, 0.0)
        if drug == "oxygen":
            outcome = self._oxygen(amount)
        else:
            outcome = self._dose(drug, DRUG_OF[drug], amount)
        if outcome.result is not TreatmentResult.ALREADY:
            for key, per_unit in SIDE_EFFECTS[drug].items():
                v = self.vitals[key]
                v.effects.append(Effect(per_unit * amount, self.cfg.effect_s))
        if outcome.counts_right:
            self.correct += 1
        elif outcome.counts_wrong:
            self.wrong += 1
        if outcome.result is TreatmentResult.OVERDOSE:
            self.overdoses += 1
        return outcome

    def _speed_up(self, v: Vital) -> None:
        """After an order the value reaches its new target in about recover_s."""
        v.speed = max(v.speed, abs(v.target(self.fio2) - v.value) / self.cfg.recover_s)

    def _dose(self, drug: str, own: str, amount: float) -> TreatmentOutcome:
        v = self.vitals[own]
        s = v.spec
        if self.episode == own:
            v.given += amount
            excess = v.given - v.need
            settles = s.normal - s.worse * s.gain * excess
            if s.status(settles) is VitalStatus.NORMAL:
                self._end_episode(own)
                self._speed_up(v)
                return TreatmentOutcome(TreatmentResult.CORRECT, drug, amount, own)
            if excess < 0:  # still short of the need
                self._alarmed[own] = 0.0  # the reminder clock starts again
                self._reminded.discard(own)
                self._waiting_still.add(own)
                self._speed_up(v)
                return TreatmentOutcome(TreatmentResult.PARTIAL, drug, amount, own)
            # too much: the episode is over, the excess overshoots for a while
            self._end_episode(own)
            v.effects.append(Effect(-s.worse * s.gain * excess, self.cfg.effect_s))
            self._speed_up(v)
            return TreatmentOutcome(TreatmentResult.OVERDOSE, drug, amount, own)
        # nobody needed this drug: its own effect pushes the value the other way
        v.effects.append(Effect(-s.worse * s.gain * amount, self.cfg.effect_s))
        self._speed_up(v)
        return self._not_for_this(drug, amount)

    def _oxygen(self, percent: float) -> TreatmentOutcome:
        v = self.vitals["spo2"]
        before = self.fio2
        self.fio2 = float(percent)
        if self.episode == "spo2":
            self._speed_up(v)
            if v.spec.status(v.target(self.fio2)) is VitalStatus.NORMAL:
                too_much = self.fio2 > v.need + FIO2_TOO_MUCH
                self._end_episode("spo2")
                return TreatmentOutcome(TreatmentResult.OVERDOSE if too_much else TreatmentResult.CORRECT, "oxygen", percent, "spo2")
            self._alarmed["spo2"] = 0.0
            self._reminded.discard("spo2")
            self._waiting_still.add("spo2")
            return TreatmentOutcome(TreatmentResult.PARTIAL, "oxygen", percent, "spo2")
        if self.fio2 <= before:
            return TreatmentOutcome(TreatmentResult.ALREADY, "oxygen", percent, "spo2")  # turning it down does no harm
        return self._not_for_this("oxygen", percent)

    def _not_for_this(self, drug: str, amount: float) -> TreatmentOutcome:
        if self.episode:  # another value is in trouble: it gets worse meanwhile
            v = self.vitals[self.episode]
            v.need += WRONG_JUMP[self.episode]
            self._speed_up(v)
            return TreatmentOutcome(TreatmentResult.WRONG, drug, amount, self.episode)
        return TreatmentOutcome(TreatmentResult.UNNEEDED, drug, amount)
