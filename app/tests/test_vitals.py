import random

import pytest

from trainer.core.config import VitalsConfig
from trainer.game.vitals import SPECS, TreatmentResult, VitalsMonitor, VitalStatus

FAST = dict(first_after_s=0.0, drift_to_critical_s=10.0, reminder_s=5.0, crisis_after_s=4.0, recover_s=3.0, effect_s=8.0)


def monitor(episodes=3, kinds=("bis",), **cfg) -> VitalsMonitor:
    m = VitalsMonitor(VitalsConfig(**{**FAST, **cfg}), rng=random.Random(4))
    m.reset(episodes, kinds)
    return m


def run(m: VitalsMonitor, seconds: float, dt: float = 0.1, time_left: float = 100.0, blocked: bool = False) -> list:
    events = []
    for _ in range(round(seconds / dt)):
        events += m.update(dt, time_left, blocked)
    return events


def kinds(events) -> list[str]:
    return [e.kind for e in events]


def episode(kind: str, need: float, seconds: float = 12.0) -> VitalsMonitor:
    """A running episode of `kind` that needs `need`, after `seconds` of drift."""
    m = monitor(kinds=(kind,))
    m.update(0.1, 100.0)
    assert m.episode == kind
    m.vitals[kind].need = need
    run(m, seconds)
    return m


def test_values_start_normal_and_the_bands_have_two_sides():
    m = monitor()
    assert {k: v.value for k, v in m.vitals.items()} == {"spo2": 98, "bis": 45, "bp": 120}
    assert SPECS["spo2"].status(91) is VitalStatus.ALARM and SPECS["spo2"].status(85) is VitalStatus.CRITICAL
    assert SPECS["bis"].status(63) is VitalStatus.ALARM and SPECS["bis"].status(76) is VitalStatus.CRITICAL
    assert SPECS["bis"].status(29) is VitalStatus.ALARM and SPECS["bis"].status(19) is VitalStatus.CRITICAL  # too deep
    assert SPECS["bp"].status(89) is VitalStatus.ALARM and SPECS["bp"].status(170) is VitalStatus.ALARM  # too high
    assert SPECS["bis"].over(25) and not SPECS["bis"].over(70)
    assert [SPECS[k].dose_card() for k in ("spo2", "bis", "bp")] == ["O2 +10%: +3", "10 mg: −6", "10 µg: +20"]
    assert not m.alarm_open()


def test_the_deviation_tells_the_dose():
    m = episode("bis", need=50, seconds=30)
    assert m.vitals["bis"].value == pytest.approx(45 + 0.6 * 50)  # untreated it settles here: (75 - 45) / 0.6 = 50 mg
    out = m.order("propofol", 50)
    assert (out.result, out.vital) == (TreatmentResult.CORRECT, "bis") and m.correct == 1 and m.episode == ""
    events = run(m, 3.5)
    assert "stable" in kinds(events) and m.vitals["bis"].value == pytest.approx(45, abs=0.5)


def test_too_little_settles_short_and_the_nurse_says_where_then_titrate():
    m = episode("bis", need=50)
    out = m.order("propofol", 20)
    assert out.result is TreatmentResult.PARTIAL and m.episode == "bis"
    events = run(m, 5.0)
    still = [e for e in events if e.kind == "still"]
    assert len(still) == 1 and still[0].value == round(45 + 0.6 * 30)  # 63: still beyond the alarm line
    assert m.order("propofol", 30).result is TreatmentResult.CORRECT
    assert (m.correct, m.wrong) == (1, 0)  # titrating is not wrong


def test_too_much_overshoots_into_the_opposite_alarm_for_a_while():
    m = episode("bis", need=40)
    out = m.order("propofol", 70)  # 30 mg too much: 45 - 18 = 27, too deep
    assert out.result is TreatmentResult.OVERDOSE and (m.wrong, m.overdoses) == (1, 1)
    events = run(m, 3.5)
    assert kinds(events) == ["over"] and events[0].vital == "bis"  # no "stable" on the way through
    events = run(m, 8.0)
    assert "stable" in kinds(events) and m.crises == 0  # it wears off


def test_far_too_much_is_a_crisis():
    m = episode("bis", need=30)
    m.order("propofol", 120)  # 90 mg too much: BIS 10, critical
    events = run(m, 8.0)
    assert "crisis" in kinds(events) and m.crises == 1


def test_oxygen_is_a_setting_and_weaned_back():
    m = episode("spo2", need=68, seconds=20)
    assert m.vitals["spo2"].value == pytest.approx(98 - 0.3 * (68 - 30))  # 86.6: needs 68 % FiO2
    assert m.order("oxygen", 40).result is TreatmentResult.PARTIAL and m.fio2 == 40
    run(m, 4.0)
    assert m.vitals["spo2"].value == pytest.approx(98 - 0.3 * 28)  # 89.6, still short
    assert m.order("oxygen", 60).result is TreatmentResult.CORRECT
    run(m, 4.0)
    assert m.vitals["spo2"].status is VitalStatus.NORMAL
    run(m, 12.0)
    assert m.fio2 == 30  # the nurse took it back down


def test_far_more_oxygen_than_needed_counts_as_too_much():
    m = episode("spo2", need=55)
    out = m.order("oxygen", 100)
    assert out.result is TreatmentResult.OVERDOSE and m.episode == "" and m.overdoses == 1
    assert m.order("oxygen", 30).result is TreatmentResult.ALREADY  # turning it down does no harm


def test_the_wrong_drug_brings_its_own_effects_and_the_episode_gets_worse():
    m = episode("spo2", need=70)
    need, bp_target = m.vitals["spo2"].need, m.vitals["bp"].target(m.fio2)
    out = m.order("propofol", 30)
    assert (out.result, out.vital) == (TreatmentResult.WRONG, "spo2") and m.wrong == 1
    assert m.vitals["spo2"].need == need + 10
    assert m.vitals["bp"].target(m.fio2) == pytest.approx(bp_target - 9)  # propofol lowers the pressure
    assert m.vitals["bis"].target(m.fio2) == pytest.approx(45 - 18)  # and deepens a patient who did not need it


def test_an_unneeded_dose_counts_and_too_much_of_it_is_a_crisis():
    m = monitor(episodes=0)
    assert m.order("adrenaline", 10).result is TreatmentResult.UNNEEDED and m.wrong == 1
    run(m, 7.0)
    m.order("adrenaline", 35)  # 120 + 70: far too high
    events = run(m, 8.0)
    assert ("over", "bp") in [(e.kind, e.vital) for e in events] and m.crises == 1


def test_the_same_order_twice_in_a_moment_counts_once():
    m = episode("bis", need=80)
    m.order("propofol", 20)
    assert m.order("propofol", 20).result is TreatmentResult.ALREADY
    assert m.vitals["bis"].given == 20
    run(m, 2.5)
    assert m.order("propofol", 20).result is TreatmentResult.PARTIAL  # later it is a new order


def test_an_episode_untreated_alarms_reminds_and_ends_in_a_crisis():
    m = monitor(episodes=1, kinds=("bp",))
    m.update(0.1, 100.0)
    m.vitals["bp"].need = 36  # untreated systolic 48: critical
    events = run(m, 30.0)
    assert kinds(events)[:3] == ["alarm", "reminder", "crisis"]
    assert m.crises == 1 and m.episode == ""


def test_the_nurse_asks_only_once_she_raised_the_alarm():
    m = monitor(kinds=("bis",))
    m.update(0.1, 100.0)
    m.vitals["bis"].need = 60
    run(m, 2.0)
    assert m.alarm_open() and not m.alarm_raised()  # drifting, not announced yet
    run(m, 10.0)
    assert m.alarm_raised()


def test_one_episode_at_a_time_and_none_while_blocked_or_near_the_end():
    m = monitor(episodes=5, kinds=("bis", "bp"), first_after_s=1.0)
    run(m, 5.0, blocked=True)
    assert m.episode == ""
    run(m, 5.0, time_left=10.0)
    assert m.episode == ""
    run(m, 0.2)
    assert m.episode in ("bis", "bp")
    assert sum(v.need > 0 for v in m.vitals.values()) == 1


def test_a_level_without_episodes_never_alarms_and_the_monitor_can_be_switched_off():
    assert run(monitor(episodes=0), 60.0) == []
    off = monitor(episodes=3, enabled=False)
    assert not off.active and run(off, 60.0) == []
    with pytest.raises(ValueError):
        monitor(kinds=("temperature",))
    with pytest.raises(ValueError):
        monitor().order("aspirin", 10)


@pytest.mark.parametrize("kind", ["spo2", "bis", "bp"])
def test_the_standard_dose_fits_about_half_of_the_episodes(kind):
    cfg = VitalsConfig()
    spec = SPECS[kind]
    rng = random.Random(7)
    fixed = 0
    for _ in range(200):
        m = VitalsMonitor(VitalsConfig(**FAST), rng=rng)
        m.reset(1, (kind,))
        m.update(0.1, 100.0)
        lo, hi = spec.need
        m.vitals[kind].need = float(round(rng.uniform(lo, hi)))
        fixed += m.order(spec.treatment, cfg.standard_doses[spec.treatment]).result is TreatmentResult.CORRECT
    assert 0.35 <= fixed / 200 <= 0.65, fixed


def test_every_episode_raises_an_alarm_untreated():
    for kind, spec in SPECS.items():
        for need in spec.need:
            m = monitor(kinds=(kind,))
            m.update(0.1, 100.0)
            m.vitals[kind].need = need
            assert "alarm" in kinds(run(m, 25.0)), (kind, need)


def test_the_same_seed_gives_the_same_round():
    def play():
        m = monitor(episodes=4, kinds=("spo2", "bis", "bp"))
        seen = []
        for _ in range(4):
            run(m, 30.0)
            seen.append((m.episode, m.vitals[m.episode].need if m.episode else 0))
            if m.episode:
                spec = SPECS[m.episode]
                m.order(spec.treatment, m.vitals[m.episode].need if m.episode != "spo2" else 100)
        return seen

    assert play() == play()
