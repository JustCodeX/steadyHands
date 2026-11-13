import random

import pytest

from trainer.core.config import VitalsConfig
from trainer.game.vitals import SPECS, TreatmentResult, VitalsMonitor, VitalStatus


def monitor(episodes=3, kinds=("spo2",), **cfg) -> VitalsMonitor:
    m = VitalsMonitor(VitalsConfig(**cfg), rng=random.Random(4))
    m.reset(episodes, kinds)
    return m


def run(m: VitalsMonitor, seconds: float, dt: float = 0.1, time_left: float = 100.0, blocked: bool = False) -> list:
    events = []
    for _ in range(round(seconds / dt)):
        events += m.update(dt, time_left, blocked)
    return events


def kinds(events) -> list[str]:
    return [e.kind for e in events]


def test_values_start_normal_and_the_thresholds_match_the_plan():
    m = monitor()
    assert {k: v.value for k, v in m.vitals.items()} == {"spo2": 98, "bis": 45, "bp": 120}
    assert SPECS["spo2"].status(91) is VitalStatus.ALARM and SPECS["spo2"].status(85) is VitalStatus.CRITICAL
    assert SPECS["bis"].status(63) is VitalStatus.ALARM and SPECS["bis"].status(76) is VitalStatus.CRITICAL
    assert SPECS["bp"].status(89) is VitalStatus.ALARM and SPECS["bp"].status(74) is VitalStatus.CRITICAL
    assert not m.alarm_open()


def test_an_episode_drifts_raises_an_alarm_then_a_reminder_then_a_crisis():
    m = monitor(first_after_s=2.0)
    assert run(m, 1.9) == [] and m.episode == ""
    events = run(m, 12.0)
    assert m.episode == "spo2" and m.vitals["spo2"].trend == -1
    assert kinds(events) == ["alarm"]
    assert events[0].vital == "spo2" and 90 <= events[0].value <= 92
    events = run(m, 6.0)
    assert kinds(events) == ["reminder"]  # once, with the value
    events = []
    for _ in range(200):
        events = m.update(0.1, 100.0)
        if events:
            break
    assert kinds(events) == ["crisis"]
    assert m.crises == 1 and m.episode == ""
    run(m, 3.5)
    assert m.vitals["spo2"].status is VitalStatus.NORMAL  # the team stepped in


def test_the_right_instruction_stops_the_drift_and_the_value_recovers():
    m = monitor(first_after_s=0.0)
    run(m, 9.0)
    assert m.alarm_open()
    out = m.treat("oxygen")
    assert (out.result, out.vital) == (TreatmentResult.CORRECT, "spo2")
    assert m.correct == 1 and m.episode == ""
    assert not m.alarm_open()  # recovering: the nurse waits no longer
    events = run(m, 3.5)
    assert kinds(events) == ["stable"] and m.vitals["spo2"].value == pytest.approx(98)
    assert m.treat("oxygen").result is TreatmentResult.UNNEEDED


def test_saying_it_twice_while_it_recovers_is_harmless():
    m = monitor(first_after_s=0.0)
    run(m, 9.0)
    m.treat("oxygen")
    again = m.treat("oxygen")
    assert again.result is TreatmentResult.ALREADY and (m.correct, m.wrong) == (1, 0)


def test_a_wrong_instruction_brings_its_side_effects_and_makes_the_episode_worse():
    m = monitor(kinds=("spo2",), first_after_s=0.0)
    run(m, 9.0)
    spo2, bp = m.vitals["spo2"].value, m.vitals["bp"].value
    out = m.treat("anaesthesia")
    assert (out.result, out.vital) == (TreatmentResult.WRONG, "spo2")
    assert m.vitals["spo2"].value == pytest.approx(spo2 - 3)  # the drifting value jumps the wrong way
    assert m.vitals["bp"].value == pytest.approx(bp - 12)  # deeper anaesthesia lowers the pressure
    assert m.wrong == 1 and m.episode == "spo2"  # still drifting


def test_an_unneeded_instruction_also_counts_and_can_cause_its_own_alarm():
    m = monitor(episodes=0)
    out = m.treat("anaesthesia")
    assert out.result is TreatmentResult.UNNEEDED and m.wrong == 1
    m.treat("anaesthesia")
    m.treat("anaesthesia")  # three times: the pressure falls below the alarm line
    events = run(m, 0.1)
    assert [(e.kind, e.vital) for e in events] == [("alarm", "bp")]
    assert m.treat("adrenaline").result is TreatmentResult.CORRECT
    assert m.vitals["bis"].value == pytest.approx(45 + 8 - 0.1, abs=0.2)  # adrenaline makes him lighter


def test_one_episode_at_a_time_and_none_while_blocked_or_near_the_end():
    m = monitor(episodes=5, kinds=("bis", "bp"), first_after_s=1.0)
    run(m, 5.0, blocked=True)
    assert m.episode == ""  # a quiz question waits for its answer
    run(m, 5.0, time_left=10.0)
    assert m.episode == ""  # too close to the end of the round
    run(m, 0.2)
    first = m.episode
    assert first in ("bis", "bp")
    run(m, 5.0)
    assert m.episode == first and sum(v.drift > 0 for v in m.vitals.values()) == 1


def test_a_level_without_episodes_never_alarms_and_the_monitor_can_be_switched_off():
    assert run(monitor(episodes=0, first_after_s=0.0), 60.0) == []
    off = monitor(episodes=3, first_after_s=0.0, enabled=False)
    assert not off.active and run(off, 60.0) == []
    with pytest.raises(ValueError):
        monitor(kinds=("temperature",))
    with pytest.raises(ValueError):
        monitor().treat("aspirin")


def test_the_same_seed_gives_the_same_round():
    a, b = monitor(episodes=4, kinds=("spo2", "bis", "bp")), monitor(episodes=4, kinds=("spo2", "bis", "bp"))
    seen_a, seen_b = [], []
    for m, seen in ((a, seen_a), (b, seen_b)):
        for _ in range(4):
            run(m, 30.0)
            seen.append(m.episode)
            if m.troubled():
                m.treat(SPECS[m.troubled()[0]].treatment)
    assert seen_a == seen_b
