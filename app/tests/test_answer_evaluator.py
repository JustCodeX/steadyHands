from pathlib import Path

import pytest

from trainer.core.config import DEFAULT_COMMANDS, QuizConfig
from trainer.quiz import KeywordEvaluator, Question, QuestionBank
from trainer.voice.command_matcher import CommandMatcher
from trainer.voice.voice_service import ANSWER_CONTROLS

BANK = QuestionBank.load(QuizConfig().questions_file)


def question(question_id):
    return BANK.get(question_id)


def test_a_whole_sentence_names_the_option():
    ev = KeywordEvaluator()
    q = question("bleeding_vessel")
    assert ev.evaluate(q, "i would take a clamp to stop it").choice == "clamp"
    assert ev.evaluate(q, "Clamp!").choice == "clamp"
    assert ev.evaluate(q, "give me the tweezers please").choice == "forceps"
    assert ev.evaluate(q, "the forcep").choice == "forceps"  # close enough


def test_no_option_or_several_options_is_unclear():
    ev = KeywordEvaluator()
    q = question("bleeding_vessel")
    assert ev.evaluate(q, "").choice is None
    assert ev.evaluate(q, "let me think about that").choice is None
    assert ev.evaluate(q, "the forceps no wait the clamp").choice is None


def test_an_exact_phrase_beats_a_near_miss_of_another_option():
    ev = KeywordEvaluator()
    q = Question(id="x", text="?", options={"light": ("light", "lamp"), "clamp": ("clamp",)}, correct="light")
    assert ev.evaluate(q, "a lamp please").choice == "light"  # not a misheard "clamp"
    assert ev.evaluate(q, "the clam").choice == "clamp"


def test_short_words_must_match_exactly():
    ev = KeywordEvaluator()
    q = question("fast_pulse")
    assert ev.evaluate(q, "no that is far too fast").choice == "no"
    assert ev.evaluate(q, "yes").choice == "yes"
    assert ev.evaluate(q, "now i know").choice is None  # "now" and "know" are not "no"


def test_phrases_of_several_words():
    ev = KeywordEvaluator()
    q = question("body_temperature")
    assert ev.evaluate(q, "it is thirty seven degrees").choice == "thirty_seven"
    assert ev.evaluate(q, "seven").choice is None


def test_question_must_name_a_correct_option_that_exists():
    with pytest.raises(ValueError):
        Question(id="x", text="?", options={"a": ("a",)}, correct="b")


def test_the_shipped_questions_are_consistent():
    assert len(BANK) >= 10
    assert len({q.id for q in BANK.questions}) == len(BANK)
    controls = CommandMatcher({w: DEFAULT_COMMANDS[w] for w in ANSWER_CONTROLS}).phrases()
    ev = KeywordEvaluator()
    for q in BANK.questions:
        assert q.text.endswith("?") and q.explain
        assert len(q.options) >= 2
        for option, phrases in q.options.items():
            for phrase in phrases:
                # every phrase means its own option and no other one
                assert ev.evaluate(q, phrase).choice == option, (q.id, phrase)
                # an answer must not be taken for "repeat", "pause" or "help"
                assert phrase not in controls, (q.id, phrase)


def test_bank_filters_by_topic_and_lists_keywords(tmp_path):
    assert {q.topic for q in BANK.for_topics(["instruments"])} == {"instruments"}
    assert len(BANK.for_topics([])) == len(BANK)
    assert "clamp" in BANK.keywords() and "thirty seven" in BANK.keywords()
    assert Path(QuizConfig().questions_file).is_file()
