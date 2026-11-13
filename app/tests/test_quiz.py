import json
import random

import pytest

from trainer.audio.lines import all_lines
from trainer.audio.phrase_builder import PhraseBuilder
from trainer.core.config import GameConfig, QuizConfig
from trainer.core.event_bus import EventBus
from trainer.core.events import (
    AnswerEvent,
    CommandEvent,
    GameEvent,
    GameState,
    PlaybackFinished,
    PlaybackStarted,
    QuestionAsked,
    QuestionClosed,
    RoundResult,
)
from trainer.game.collision_map import CollisionMap
from trainer.game.engine import GameEngine
from trainer.game.level import Level, LevelCatalog
from trainer.game.quiz_director import QuizDirector, QuizOutcome, QuizStep
from trainer.game.stress import Stress
from trainer.quiz import Question, QuestionBank


def make_bank(n=3):
    return QuestionBank(
        [
            Question(id=f"q{i}", text=f"Question {i}?", options={"clamp": ("clamp",), "swab": ("swab",)}, correct="clamp", explain="Clamp.")
            for i in range(n)
        ]
    )


CFG = QuizConfig(first_after_s=2.0, interval_s=3.0, answer_window_s=4.0, min_time_left_s=5.0)


# --- QuizDirector ----------------------------------------------------------------


def test_director_asks_after_the_first_delay_and_then_at_intervals():
    d = QuizDirector(CFG, make_bank(), random.Random(1))
    d.reset(limit=2)
    assert d.tick(1.9, speaking=False, time_left=60) is QuizStep.NONE
    assert d.tick(0.2, speaking=False, time_left=60) is QuizStep.ASK
    first = d.pending
    assert d.answer(AnswerEvent(question_id=first.id, correct=True)) is QuizOutcome.CORRECT
    assert d.pending is None and d.last is first
    assert d.tick(2.9, speaking=False, time_left=60) is QuizStep.NONE
    assert d.tick(0.2, speaking=False, time_left=60) is QuizStep.ASK
    assert d.pending.id != first.id  # no repeat before every question was asked
    d.answer(AnswerEvent(correct=False))
    assert (d.correct, d.wrong) == (1, 1)
    assert d.tick(10.0, speaking=False, time_left=60) is QuizStep.NONE  # the limit is reached


def test_director_waits_while_the_patient_speaks_and_near_the_end():
    d = QuizDirector(CFG, make_bank(), random.Random(1))
    d.reset(limit=1)
    assert d.tick(3.0, speaking=True, time_left=60) is QuizStep.NONE
    assert d.tick(0.1, speaking=False, time_left=4.0) is QuizStep.NONE  # too close to the end
    assert d.tick(0.1, speaking=False, time_left=60) is QuizStep.ASK
    # the answer window does not run while the question is being spoken
    assert d.tick(10.0, speaking=True, time_left=60) is QuizStep.NONE
    assert d.window_fraction() == 1.0
    assert d.tick(2.0, speaking=False, time_left=60) is QuizStep.NONE
    assert d.window_fraction() == pytest.approx(0.5)
    assert d.tick(2.1, speaking=False, time_left=60) is QuizStep.TIMEOUT
    assert d.wrong == 1 and d.pending is None


def test_second_unclear_answer_counts_as_wrong_and_stale_answers_are_ignored():
    d = QuizDirector(CFG, make_bank(), random.Random(1))
    d.reset(limit=1)
    assert d.answer(AnswerEvent(correct=True)) is QuizOutcome.IGNORED  # nothing is open
    d.tick(2.1, speaking=False, time_left=60)
    assert d.answer(AnswerEvent(question_id="another", correct=True)) is QuizOutcome.IGNORED
    assert d.answer(AnswerEvent(unclear=True)) is QuizOutcome.UNCLEAR
    assert d.pending is not None
    assert d.answer(AnswerEvent(unclear=True)) is QuizOutcome.WRONG
    assert d.wrong == 1


def test_director_never_asks_without_questions_or_when_disabled():
    for director in (QuizDirector(CFG), QuizDirector(QuizConfig(enabled=False), make_bank())):
        director.reset(limit=3)
        assert director.tick(100.0, speaking=False, time_left=60) is QuizStep.NONE


def test_stress_is_bounded_and_scales_speed_and_bleeding():
    s = Stress(QuizConfig(max_stress=2, stress_speed_step=0.1, stress_bleed_step=0.5))
    assert (s.speed_factor, s.bleed_factor) == (1.0, 1.0)
    for _ in range(5):
        s.worse()
    assert s.level == 2 and s.speed_factor == pytest.approx(1.2) and s.bleed_factor == pytest.approx(2.0)
    for _ in range(5):
        s.better()
    assert s.level == 0


# --- GameEngine with a quiz ---------------------------------------------------------


class OpenCatalog(LevelCatalog):
    def __init__(self, tmp_path, quiz=None):
        super().__init__(tmp_path)
        self.dir = tmp_path / "01-test"
        self.dir.mkdir()
        data = {
            "name": "Test",
            "time_limit_s": 60,
            "start": [20, 60],
            "targets": [{"id": "bleed", "position": [160, 60], "needs": "clamp", "timer_s": 10}],
        }
        if quiz is not None:
            data["quiz"] = quiz
        (self.dir / "level.json").write_text(json.dumps(data))

    def load(self, index):
        return Level.load(self.dir, mask=CollisionMap(200, 120, bytearray(200 * 120)))


def make_engine(tmp_path, quiz=None, quiz_cfg=CFG):
    bus = EventBus()
    eng = GameEngine(bus, GameConfig(speed_px_per_s=100.0), OpenCatalog(tmp_path, quiz), 200, 120, quiz_cfg, make_bank())
    eng.seen = []
    for kind in (GameEvent, RoundResult, QuestionAsked, QuestionClosed):
        bus.subscribe(kind, eng.seen.append)
    eng.start()
    eng.start_round()
    return bus, eng


def kinds(bus, eng):
    bus.dispatch()
    return [e.kind if isinstance(e, GameEvent) else type(e).__name__ for e in eng.seen]


def test_engine_asks_and_a_correct_answer_closes_the_question(tmp_path):
    bus, eng = make_engine(tmp_path)
    eng.tick(1.0)
    assert eng.snapshot().question_text == ""
    eng.tick(1.5)
    snap = eng.snapshot()
    assert snap.question_text.startswith("Question") and snap.question_left == 1.0
    assert kinds(bus, eng)[-2:] == ["QuestionAsked", "question"]
    asked = [e for e in eng.seen if isinstance(e, QuestionAsked)][0]
    bus.publish(AnswerEvent(question_id=asked.question_id, correct=True))
    assert kinds(bus, eng)[-2:] == ["QuestionClosed", "quiz_correct"]
    assert eng.snapshot().question_text == "" and eng.stress.level == 0


def test_a_wrong_answer_costs_time_and_raises_stress(tmp_path):
    bus, eng = make_engine(tmp_path)
    eng.tick(2.5)
    before = eng.time_left
    rate = eng.patient.heart_rate
    eng.on_answer(AnswerEvent(correct=False))
    assert eng.time_left == pytest.approx(before - CFG.wrong_time_penalty_s)
    assert eng.patient.heart_rate == rate + CFG.wrong_heart_rate_bump
    assert eng.stress.level == 1 and eng.snapshot().stress == 1
    assert kinds(bus, eng)[-2:] == ["QuestionClosed", "quiz_wrong"]
    assert eng.patient.contacts == 0  # a wrong answer is not a wall contact


def test_stress_makes_the_instrument_faster_and_the_bleeding_shorter(tmp_path):
    from trainer.core.events import InputFrame

    bus, eng = make_engine(tmp_path, quiz={"count": 0})
    eng.on_input(InputFrame(tilt_x=1.0))
    eng.tick(0.1)
    calm_step = eng.x - 20.0
    timer = eng.level.targets[0].timer_left
    eng.stress.worse()
    eng.stress.worse()
    x = eng.x
    eng.tick(0.1)
    assert eng.x - x == pytest.approx(calm_step * 1.3, rel=0.02)
    assert timer - eng.level.targets[0].timer_left == pytest.approx(0.1 * 1.5)


def test_no_answer_in_time_is_wrong_and_the_window_waits_for_the_patient(tmp_path):
    bus, eng = make_engine(tmp_path)
    eng.tick(2.5)
    bus.publish(PlaybackStarted())
    bus.dispatch()
    eng.tick(10.0)  # the question is being spoken
    assert eng.snapshot().question_left == 1.0
    bus.publish(PlaybackFinished())
    bus.dispatch()
    eng.tick(4.1)
    assert kinds(bus, eng)[-2:] == ["QuestionClosed", "quiz_timeout"]
    assert eng.stress.level == 1


def test_unclear_answer_asks_again_and_repeat_says_the_question_again(tmp_path):
    bus, eng = make_engine(tmp_path)
    eng.tick(2.5)
    eng.on_answer(AnswerEvent(unclear=True))
    assert kinds(bus, eng)[-1] == "pardon" and eng.quiz.pending is not None
    eng.on_command(CommandEvent(word="repeat"))
    bus.dispatch()
    last = [e for e in eng.seen if isinstance(e, GameEvent)][-1]
    assert (last.kind, last.detail) == ("question", eng.quiz.pending.id)


def test_result_counts_the_answers_and_an_open_question_ends_with_the_round(tmp_path):
    bus, eng = make_engine(tmp_path)
    eng.tick(2.5)
    eng.on_answer(AnswerEvent(correct=True))
    eng.tick(3.1)  # the next question is open
    assert eng.quiz.pending is not None
    eng.end_round(won=False)
    bus.dispatch()
    result = [e for e in eng.seen if isinstance(e, RoundResult)][0]
    assert (result.questions_correct, result.questions_wrong) == (1, 0)
    assert eng.quiz.pending is None
    assert sum(isinstance(e, QuestionClosed) for e in eng.seen) == 2
    assert eng.state is GameState.RESULT
    eng.on_answer(AnswerEvent(correct=False))  # a late answer changes nothing
    assert eng.stress.level == 0


def test_level_sets_how_many_questions_and_new_game_closes_an_open_one(tmp_path):
    bus, eng = make_engine(tmp_path, quiz={"count": 1, "topics": []})
    assert eng.level.quiz_count == 1
    eng.tick(2.5)
    eng.on_command(CommandEvent(word="new game"))
    assert eng.quiz.pending is None
    assert kinds(bus, eng)[-2:] == ["QuestionClosed", "round_started"]
    eng.tick(2.5)
    eng.on_answer(AnswerEvent(correct=True))
    eng.tick(30.0)
    assert eng.quiz.pending is None  # one question only


def test_engine_without_questions_never_asks(tmp_path):
    bus = EventBus()
    eng = GameEngine(bus, GameConfig(), OpenCatalog(tmp_path), 200, 120)
    eng.start()
    eng.start_round()
    eng.tick(30.0)
    assert eng.snapshot().question_text == ""


# --- spoken lines -----------------------------------------------------------------


def test_quiz_events_and_results_map_to_clips():
    assert PhraseBuilder.for_event("question", "q1", 0) == ["q_q1"]
    assert PhraseBuilder.for_event("quiz_correct", "q1", 0) == ["quiz_correct"]
    assert PhraseBuilder.for_event("quiz_wrong", "q1", 0) == ["quiz_wrong", "qa_q1"]
    assert PhraseBuilder.for_event("quiz_timeout", "q1", 0) == ["quiz_timeout", "qa_q1"]

    def result(correct, wrong):
        return RoundResult(level_name="L", won=True, time_s=30, contacts=0, steadiness=80, calls_correct=0, calls_wrong=0, steady_uses=0, questions_correct=correct, questions_wrong=wrong)

    assert not any(i.startswith("quiz") for i in PhraseBuilder.result(result(0, 0)))
    assert PhraseBuilder.result(result(2, 0))[-1] == "quiz_all"
    assert PhraseBuilder.result(result(1, 1))[-1] == "quiz_some"
    assert PhraseBuilder.result(result(0, 2))[-1] == "quiz_none"


def test_every_question_and_explanation_gets_a_clip():
    lines = all_lines(make_bank(2))
    assert lines["q_q0"] == "Question 0?" and lines["qa_q1"] == "Clamp."
    assert "q_q0" not in all_lines()
    for needed in ("quiz_correct", "quiz_wrong", "quiz_timeout", "quiz_all", "quiz_some", "quiz_none"):
        assert needed in lines


def test_metrics_log_holds_the_verdict_and_latency_of_an_answer(tmp_path):
    import time

    from trainer.core.config import SystemConfig
    from trainer.system.metrics_logger import MetricsLogger

    bus = EventBus()
    logger = MetricsLogger(bus, SystemConfig(metrics_log=str(tmp_path / "m.csv")))
    logger.start()
    bus.publish(AnswerEvent(question_id="q0", correct=True, speech_end_t=time.monotonic() - 0.2))
    bus.publish(AnswerEvent(question_id="q0", unclear=True))
    bus.dispatch()
    logger.stop()
    rows = [line.split(",")[1:3] for line in (tmp_path / "m.csv").read_text().splitlines()[1:]]
    assert rows[0][0] == "answer_latency_ms" and 150 <= float(rows[0][1]) <= 1000
    assert rows[1:] == [["answer", "correct"], ["answer", "unclear"]]
