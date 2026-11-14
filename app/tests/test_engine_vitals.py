"""The vitals monitor inside a round: orders with amounts, the standard dose,
lives, the result, and one open turn at a time with the quiz."""
import json
import random

from trainer.core.config import GameConfig, QuizConfig, VitalsConfig
from trainer.core.event_bus import EventBus
from trainer.core.events import CommandEvent, GameEvent, GameState, QuestionAsked, RoundResult
from trainer.game.collision_map import CollisionMap
from trainer.game.engine import GameEngine
from trainer.game.level import Level, LevelCatalog
from trainer.quiz import QuestionBank
from trainer.quiz.question import Question

VCFG = VitalsConfig(first_after_s=1.0, interval_s=(30.0, 30.0), drift_to_critical_s=10.0, reminder_s=3.0, crisis_after_s=2.0, min_time_left_s=5.0)


class VitalsCatalog(LevelCatalog):
    def __init__(self, tmp_path, vitals=None, quiz=None):
        super().__init__(tmp_path)
        self.dir = tmp_path / "01-test"
        self.dir.mkdir()
        data = {"name": "Test", "time_limit_s": 120, "start": [20, 60], "targets": [{"id": "splinter", "position": [160, 60], "needs": "forceps"}]}
        if vitals is not None:
            data["vitals"] = vitals
        if quiz is not None:
            data["quiz"] = quiz
        (self.dir / "level.json").write_text(json.dumps(data))

    def load(self, index):
        return Level.load(self.dir, mask=CollisionMap(200, 120, bytearray(200 * 120)))


def make(tmp_path, vitals=None, quiz=None, quiz_cfg=None, questions=None):
    bus = EventBus()
    eng = GameEngine(bus, GameConfig(), VitalsCatalog(tmp_path, vitals, quiz), 200, 120, quiz_cfg, questions, VCFG, random.Random(1))
    eng.seen = []
    for kind in (GameEvent, RoundResult, QuestionAsked):
        bus.subscribe(kind, eng.seen.append)
    eng.start()
    eng.start_round()
    return bus, eng


def start_episode(bus, eng, need, seconds=1.2):
    """Run until the episode starts, then fix how much it needs."""
    run(bus, eng, seconds)
    assert eng.vitals.episode
    eng.vitals.vitals[eng.vitals.episode].need = need


def order(bus, eng, word, amount=None):
    bus.publish(CommandEvent(word=word, confidence=0.9, amount=amount))
    bus.dispatch()


def run(bus, eng, seconds, dt=0.1):
    for _ in range(round(seconds / dt)):
        eng.tick(dt)
    bus.dispatch()


def game_events(eng, prefix=""):
    return [(e.kind, e.detail) for e in eng.seen if isinstance(e, GameEvent) and e.kind.startswith(prefix)]


def test_a_level_without_a_vitals_block_has_no_monitor(tmp_path):
    bus, eng = make(tmp_path)
    run(bus, eng, 30.0)
    assert game_events(eng, "vital") == [] and eng.snapshot().vitals == []


def test_alarm_then_the_right_dose_by_voice(tmp_path):
    bus, eng = make(tmp_path, vitals={"episodes": 1, "kinds": ["bp"]})
    start_episode(bus, eng, need=25)  # untreated systolic 70: needs 25 µg
    run(bus, eng, 8.0)
    snap = eng.snapshot()
    assert [v.key for v in snap.vitals] == ["spo2", "bis", "bp"]
    assert [v.dose_card for v in snap.vitals] == ["O2 +10%: +3", "10 mg: −6", "10 µg: +20"]
    assert snap.vitals[0].setting == "FiO2 30%" and snap.vitals[1].setting == ""
    alarms = game_events(eng, "vital_alarm")
    assert len(alarms) == 1 and alarms[0][1].startswith("bp:")
    assert snap.vitals_alarm and eng.available_commands() == ["oxygen", "propofol", "adrenaline"]  # what "help" says now
    order(bus, eng, "adrenaline", 25)
    assert game_events(eng, "treatment") == [("treatment", "adrenaline:correct:bp:25:")]
    run(bus, eng, 4.0)
    assert game_events(eng, "vital_stable") and not eng.snapshot().vitals_alarm
    eng.end_round(won=True)
    bus.dispatch()
    result = next(e for e in eng.seen if isinstance(e, RoundResult))
    assert (result.treatments_correct, result.treatments_wrong, result.overdoses, result.crises) == (1, 0, 0, 0)


def test_no_amount_means_the_standard_dose_which_can_fall_short(tmp_path):
    bus, eng = make(tmp_path, vitals={"episodes": 1, "kinds": ["bp"]})
    start_episode(bus, eng, need=30)
    run(bus, eng, 6.0)
    order(bus, eng, "adrenaline")  # standard: 10 µg, 20 short
    assert game_events(eng, "treatment") == [("treatment", "adrenaline:partial:bp:10:standard")]
    assert "not enough" in eng.message
    run(bus, eng, 4.0)
    still = game_events(eng, "vital_still")
    assert len(still) == 1 and still[0][1] == "bp:80"  # 120 - 2 x 20
    order(bus, eng, "adrenaline", 20)
    assert game_events(eng, "treatment")[-1] == ("treatment", "adrenaline:correct:bp:20:")


def test_a_wrong_drug_is_named_counted_and_moves_the_pulse(tmp_path):
    bus, eng = make(tmp_path, vitals={"episodes": 1, "kinds": ["spo2"]})
    start_episode(bus, eng, need=65)
    run(bus, eng, 8.0)
    pulse = eng.patient.heart_rate
    order(bus, eng, "adrenaline", 10)
    assert game_events(eng, "treatment") == [("treatment", "adrenaline:wrong:spo2:10:")]
    assert eng.patient.heart_rate == pulse + 8  # 0.8 bpm per microgram
    assert "did not help" in eng.message
    order(bus, eng, "oxygen", 70)
    eng.end_round(won=False)
    bus.dispatch()
    result = next(e for e in eng.seen if isinstance(e, RoundResult))
    assert (result.treatments_correct, result.treatments_wrong) == (1, 1)


def test_an_overdose_is_counted_and_announced(tmp_path):
    bus, eng = make(tmp_path, vitals={"episodes": 1, "kinds": ["bis"]})
    start_episode(bus, eng, need=40)
    run(bus, eng, 8.0)
    order(bus, eng, "propofol", 75)
    assert game_events(eng, "treatment") == [("treatment", "propofol:overdose:bis:75:")]
    run(bus, eng, 4.0)
    assert [d for _, d in game_events(eng, "vital_over")][0].startswith("bis:")
    eng.end_round(won=False)
    bus.dispatch()
    result = next(e for e in eng.seen if isinstance(e, RoundResult))
    assert (result.treatments_wrong, result.overdoses) == (1, 1)


def test_no_order_ends_in_a_crisis_that_costs_a_life(tmp_path):
    bus, eng = make(tmp_path, vitals={"episodes": 1, "kinds": ["spo2"]})
    start_episode(bus, eng, need=95)  # untreated 78.5 %: critical
    run(bus, eng, 20.0)
    kinds = [k for k, _ in game_events(eng, "vital")]
    assert kinds[:3] == ["vital_alarm", "vital_reminder", "vital_crisis"]
    assert eng.patient.crises == 1 and eng.patient.contacts == 0
    snap = eng.snapshot()
    assert snap.crises == 1 and snap.contacts == 0


def test_crises_and_wall_contacts_share_the_lives(tmp_path):
    bus, eng = make(tmp_path, vitals={"episodes": 1, "kinds": ["spo2"]})
    eng.patient.on_contact()
    eng.patient.on_contact()
    start_episode(bus, eng, need=95)
    run(bus, eng, 20.0)
    assert eng.state is GameState.RESULT  # 2 contacts + 1 crisis = 3 lives
    result = next(e for e in eng.seen if isinstance(e, RoundResult))
    assert (result.contacts, result.crises, result.won) == (2, 1, False)


def test_orders_outside_a_round_do_nothing(tmp_path):
    bus, eng = make(tmp_path, vitals={"episodes": 1})
    eng.end_round(won=False)
    order(bus, eng, "oxygen", 60)
    assert game_events(eng, "treatment") == []


def test_no_question_while_an_alarm_is_open_and_no_episode_while_a_question_is(tmp_path):
    bank = QuestionBank([Question(id="q1", text="Which?", options={"yes": ["yes"], "no": ["no"]}, correct="yes")])
    quiz_cfg = QuizConfig(enabled=True, first_after_s=3.0, interval_s=100.0, answer_window_s=60.0, min_time_left_s=5.0)
    bus, eng = make(tmp_path, vitals={"episodes": 2, "kinds": ["spo2"]}, quiz={"count": 1}, quiz_cfg=quiz_cfg, questions=bank)
    start_episode(bus, eng, need=70)
    run(bus, eng, 9.0)  # the episode started at 1 s and runs before the question is due
    assert eng.vitals.alarm_open() and eng.quiz.pending is None
    assert not [e for e in eng.seen if isinstance(e, QuestionAsked)]
    order(bus, eng, "oxygen", 70)
    run(bus, eng, 6.0)  # the saturation recovers, then the quiz clock runs on: 2 of its 3 s were left
    assert eng.quiz.pending is not None  # the question comes once the nurse is done
    run(bus, eng, 40.0)
    assert eng.vitals.episode == "" and eng.vitals._started == 1  # and no second episode while it is open
