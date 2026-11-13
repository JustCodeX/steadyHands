"""Needle and Whistle against a stand-in for the Cactus runtime.

The stand-in behaves the way the runtime is documented to: tools are plain
functions the agent executes, `reset()` must come before every independent
text, and a call below the confidence gate is reported but not executed.
The real runtime is only on the board; these tests cover our side of it.
"""
import inspect
import os
import sys
import types
import typing

import numpy as np
import pytest

from trainer.cactus_models import needle_agent, whistle_recognizer
from trainer.cactus_models.needle_agent import NeedleAgent, choice_tool, plain_tool
from trainer.cactus_models.needle_evaluator import NeedleEvaluator
from trainer.cactus_models.needle_interpreter import NeedleInterpreter
from trainer.cactus_models.runtime import load_cactus
from trainer.cactus_models.whistle_recognizer import WhistleRecognizer
from trainer.core.config import DEFAULT_COMMANDS, QuizConfig, VoiceConfig
from trainer.game.actions import ActionCatalog
from trainer.quiz import KeywordEvaluator, QuestionBank
from trainer.voice.command_matcher import CommandMatcher
from trainer.voice.recognizer import EnsembleRecognizer, NullRecognizer
from trainer.voice.voice_service import build_answer_recognizer, build_evaluator, build_interpreter, build_recognizer

BANK = QuestionBank.load(QuizConfig().questions_file)


class FakeAgent:
    def __init__(self, tools, system, weights, script):
        self.tools = {t.__name__: t for t in tools}
        self.system, self.weights, self.script = system, weights, script
        self.fresh = False
        self.heard = []

    def reset(self):
        self.fresh = True

    def run(self, text):
        assert self.fresh, "reset() must be called before every independent text"
        self.fresh = False
        self.heard.append(text)
        planned = self.script.get(text, [])
        if isinstance(planned, Exception):
            raise planned
        suppressed, confidence = [], 0.0
        for name, arguments, conf in planned:
            tool = self.tools[name]
            hints = typing.get_type_hints(tool)
            assert set(arguments) == set(inspect.signature(tool).parameters)
            for key, value in arguments.items():
                assert value in typing.get_args(hints[key]), f"{value!r} is not allowed for {name}.{key}"
            confidence = conf
            if conf < 0.1:  # the runtime's own gate: reported, not executed
                suppressed.append({"name": name, "arguments": arguments})
            else:
                tool(**arguments)
        return {"confidence": confidence, "suppressed_calls": suppressed}


class FakeCactus:
    def __init__(self, script=None, heard_text="clamp"):
        self.script = script or {}
        self.agents = []
        self.transcriptions = []
        self.heard_text = heard_text

    def tool(self, fn):
        assert fn.__doc__ and fn.__name__.isidentifier()
        return fn

    def Cactus(self, tools, system, weights):  # noqa: N802
        self.agents.append(FakeAgent(tools, system, weights, self.script))
        return self.agents[-1]

    def transcribe(self, audio, language=None, keywords=None, word_timestamps=False, weights=None):
        self.transcriptions.append({"audio": audio, "language": language, "keywords": keywords, "weights": weights})
        words = [{"word": w, "probability": 0.8} for w in self.heard_text.split()] if word_timestamps else None
        return {"text": self.heard_text, "language": language, "words": words}


@pytest.fixture
def weights(tmp_path):
    path = tmp_path / "needle3-9L.cact"
    path.write_bytes(b"weights")
    return path


def use(monkeypatch, fake):
    monkeypatch.setattr(needle_agent, "load_cactus", lambda: fake)
    monkeypatch.setattr(whistle_recognizer, "load_cactus", lambda: fake)
    return fake


# --- runtime ----------------------------------------------------------------------


def test_the_runtime_is_imported_with_telemetry_and_hub_access_off(monkeypatch):
    monkeypatch.setenv("CACTUS_TELEMETRY", "1")
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    stub = types.ModuleType("cactus")
    monkeypatch.setitem(sys.modules, "cactus", stub)
    assert load_cactus() is stub
    assert os.environ["CACTUS_TELEMETRY"] == "0" and os.environ["HF_HUB_OFFLINE"] == "1"


def test_nothing_outside_the_package_imports_the_runtime():
    from pathlib import Path

    root = Path(needle_agent.__file__).resolve().parents[1]
    for path in root.rglob("*.py"):
        if path.name == "runtime.py":
            continue
        assert "import cactus" not in path.read_text(), path


# --- NeedleAgent -------------------------------------------------------------------


def test_tools_tell_the_model_their_name_purpose_and_allowed_values():
    seen = []
    tool = choice_tool("answer", "Record the answer.", "the option meant", ["clamp", "swab"], lambda n, a: seen.append((n, a)))
    assert tool.__name__ == "answer"
    assert typing.get_args(typing.get_type_hints(tool)["choice"]) == ("clamp", "swab")
    assert "Record the answer." in tool.__doc__ and "choice: the option meant" in tool.__doc__
    tool(choice="swab")
    plain = plain_tool("steady", "Precision mode.", lambda n, a: seen.append((n, a)))
    assert not inspect.signature(plain).parameters
    plain()
    assert seen == [("answer", {"choice": "swab"}), ("steady", {})]


def make_agent(monkeypatch, weights, script):
    fake = use(monkeypatch, FakeCactus(script))
    agent = NeedleAgent(
        weights,
        "system text",
        lambda record: [plain_tool("steady", "Precision mode.", record), choice_tool("pick", "Pick one.", "which", ["a", "b"], record)],
    )
    return fake, agent


def test_agent_returns_the_call_the_model_made(monkeypatch, weights):
    fake, agent = make_agent(monkeypatch, weights, {"the first": [("pick", {"choice": "a"}, 0.7)], "slow down": [("steady", {}, 0.9)]})
    call = agent.call("the first")
    assert (call.name, call.arguments, call.confidence) == ("pick", {"choice": "a"}, 0.7)
    assert agent.call("slow down").name == "steady"  # the fake fails if reset() was skipped in between
    assert len(fake.agents) == 1 and fake.agents[0].system == "system text" and fake.agents[0].weights == str(weights)


def test_agent_gives_nothing_when_the_model_is_unsure_or_wants_two_things(monkeypatch, weights):
    fake, agent = make_agent(
        monkeypatch,
        weights,
        {
            "held back": [("pick", {"choice": "a"}, 0.05)],
            "both": [("pick", {"choice": "a"}, 0.8), ("pick", {"choice": "b"}, 0.8)],
            "twice": [("pick", {"choice": "a"}, 0.8), ("pick", {"choice": "a"}, 0.8)],
        },
    )
    assert agent.call("what a nice day") is None  # no tool fits
    assert agent.call("held back") is None  # below the runtime's gate: not executed
    assert agent.call("both") is None
    assert agent.call("twice").arguments == {"choice": "a"}
    agent.min_confidence = 0.9
    assert agent.call("twice") is None  # our own, stricter gate


def test_agent_needs_its_weights(monkeypatch, tmp_path):
    use(monkeypatch, FakeCactus())
    with pytest.raises(FileNotFoundError):
        NeedleAgent(tmp_path / "missing.cact", "s", lambda record: []).load()


# --- NeedleInterpreter -------------------------------------------------------------


def test_interpreter_asks_the_model_only_when_no_command_phrase_was_said(monkeypatch, weights):
    script = {
        "something to stop the bleeding": [("select_instrument", {"choice": "clamp"}, 0.8)],
        "lets carry on": [("resume", {}, 0.6)],
        "i need more light in here": [("light", {}, 0.7)],
        "hand me the forcep": RuntimeError("engine fell over"),
    }
    fake = use(monkeypatch, FakeCactus(script))
    interpreter = NeedleInterpreter(DEFAULT_COMMANDS, weights)
    agent = fake.agents[0]
    assert sorted(agent.tools) == sorted(["select_instrument", "steady", "light", "cancel", "repeat", "help", "pause", "resume", "new_game"])
    assert typing.get_args(typing.get_type_hints(agent.tools["select_instrument"])["choice"]) == ("forceps", "swab", "clamp", "scalpel")

    assert interpreter.interpret("clamp").word == "clamp"
    assert interpreter.interpret("i need more light in here").score == 1.0  # "light" is in the sentence
    assert agent.heard == []  # neither needed the model

    hit = interpreter.interpret("something to stop the bleeding")
    assert (hit.word, hit.score) == ("clamp", 0.8)
    assert interpreter.interpret("lets carry on").word == "continue"
    # talk is not a command, even where the fuzzy matcher alone would hear "light" in "night"
    assert CommandMatcher(DEFAULT_COMMANDS).interpret("did you see the game last night").word == "light"
    assert interpreter.interpret("did you see the game last night") is None
    assert interpreter.interpret("something to stop the bleeding", allowed=["forceps", "pause"]) is None
    # a failing model must not stop the game: the matcher's guess is the fallback
    assert interpreter.interpret("hand me the forcep").word == "forceps"
    assert interpreter.interpret("") is None
    assert interpreter.phrases() == CommandMatcher(DEFAULT_COMMANDS).phrases()


# --- NeedleEvaluator ---------------------------------------------------------------


def test_evaluator_asks_the_model_only_when_no_option_was_named(monkeypatch, weights):
    script = {
        "the thing you squeeze the vessel shut with": [("answer", {"choice": "clamp"}, 0.6)],
        "the sharp one": [("answer", {"choice": "scalpel"}, 0.7)],
    }
    fake = use(monkeypatch, FakeCactus(script))
    evaluator = NeedleEvaluator(weights)
    question = BANK.get("bleeding_vessel")
    evaluator.prepare(question)
    evaluator.prepare(question)  # asked again ("repeat"): no second model
    assert len(fake.agents) == 1
    agent = fake.agents[0]
    assert question.text in agent.system
    assert typing.get_args(typing.get_type_hints(agent.tools["answer"])["choice"]) == tuple(question.options)
    assert "clamp (clamp, clamps" in agent.tools["answer"].__doc__

    assert evaluator.evaluate(question, "i would take a clamp").choice == "clamp"
    assert evaluator.evaluate(question, "the forceps no wait the clamp").choice is None  # two options: ask again
    assert agent.heard == []

    verdict = evaluator.evaluate(question, "the thing you squeeze the vessel shut with")
    assert (verdict.choice, verdict.score) == ("clamp", 0.6)
    assert evaluator.evaluate(question, "the sharp one").choice == "scalpel"  # a wrong answer, understood
    assert evaluator.evaluate(question, "no idea to be honest").choice is None

    other = BANK.get("fast_pulse")
    evaluator.prepare(other)
    assert len(fake.agents) == 2 and typing.get_args(typing.get_type_hints(fake.agents[1].tools["answer"])["choice"]) == ("yes", "no")


def test_evaluator_without_a_working_model_is_the_keyword_evaluator(monkeypatch, weights, tmp_path):
    with pytest.raises(FileNotFoundError):
        NeedleEvaluator(tmp_path / "missing.cact")

    def broken(*_):
        raise ImportError("no module named cactus")

    monkeypatch.setattr(needle_agent, "load_cactus", broken)
    with pytest.raises(ImportError):
        NeedleEvaluator(weights)  # the package is missing: say so at start-up
    assert type(build_evaluator(VoiceConfig(evaluator="needle", needle_weights=str(weights)))) is KeywordEvaluator
    evaluator = NeedleEvaluator(weights, agent_factory=broken)  # the model breaks later, for one question
    question = BANK.get("bleeding_vessel")
    assert evaluator.evaluate(question, "the clamp").choice == "clamp"
    assert evaluator.evaluate(question, "the thing you squeeze with").choice is None


# --- WhistleRecognizer ---------------------------------------------------------------


def test_whistle_transcribes_the_whole_segment_offline_settings_included(monkeypatch, weights):
    fake = use(monkeypatch, FakeCactus(heard_text="I'd take the clamp."))
    rec = WhistleRecognizer(weights, language="en", keywords=["swab", "clamp"])
    assert len(fake.transcriptions) == 1  # the warm-up that loads the engine
    rec.set_vocabulary(["clamp", "forceps"])
    half = (np.ones(160, dtype=np.int16) * 16384).tobytes()
    rec.accept(half)
    rec.accept(half)
    heard = rec.finish()
    call = fake.transcriptions[-1]
    assert len(call["audio"]) == 320 and call["audio"][0] == pytest.approx(0.5)
    assert (call["language"], call["keywords"], call["weights"]) == ("en", ["clamp", "forceps"], str(weights))
    assert heard.text == "I'd take the clamp." and heard.confidence == pytest.approx(0.8)
    assert KeywordEvaluator().evaluate(BANK.get("bleeding_vessel"), heard.text).choice == "clamp"
    assert rec.finish().text == "" and len(fake.transcriptions) == 2  # nothing fed, nothing transcribed
    rec.accept(half)
    rec.reset()
    assert rec.finish().text == ""


def test_numbers_written_as_digits_still_name_the_option():
    evaluator = KeywordEvaluator()
    assert evaluator.evaluate(BANK.get("body_temperature"), "It's 37 degrees.").choice == "thirty_seven"
    assert evaluator.evaluate(BANK.get("heart_chambers"), "4").choice == "four"
    assert all(k.replace(" ", "").isalpha() for k in BANK.keywords())  # digits never reach a Vosk grammar


def test_whistle_needs_its_weights_and_16_khz(monkeypatch, weights, tmp_path):
    use(monkeypatch, FakeCactus())
    with pytest.raises(FileNotFoundError):
        WhistleRecognizer(tmp_path / "missing.cact")
    with pytest.raises(ValueError):
        WhistleRecognizer(weights, sample_rate=48000)


# --- selection by config ---------------------------------------------------------------


def test_config_selects_needle_and_falls_back_without_it(monkeypatch, weights, tmp_path, caplog):
    use(monkeypatch, FakeCactus())
    with_needle = VoiceConfig(interpreter="needle", evaluator="needle", command_vocabulary="open", needle_weights=str(weights))
    assert isinstance(build_interpreter(with_needle, DEFAULT_COMMANDS), NeedleInterpreter)
    assert isinstance(build_evaluator(with_needle), NeedleEvaluator)
    missing = VoiceConfig(interpreter="needle", evaluator="needle", needle_weights=str(tmp_path / "missing.cact"))
    with caplog.at_level("ERROR"):
        assert isinstance(build_interpreter(missing, DEFAULT_COMMANDS), CommandMatcher)
        assert type(build_evaluator(missing)) is KeywordEvaluator
    assert caplog.text.count("Needle unavailable") == 2


def test_config_selects_whistle_for_answers_and_for_commands(monkeypatch, weights, tmp_path):
    import trainer.voice.vosk_recognizer as vosk_module

    class FakeVosk(NullRecognizer):
        def __init__(self, model_dir, phrases, sample_rate):
            self.phrases = phrases

    monkeypatch.setattr(vosk_module, "VoskRecognizer", FakeVosk)
    use(monkeypatch, FakeCactus())
    cfg = VoiceConfig(answer_engine="whistle", whistle_weights=str(weights))
    both = build_answer_recognizer(cfg, BANK)
    assert isinstance(both, EnsembleRecognizer)
    assert isinstance(both.members[0], WhistleRecognizer) and isinstance(both.members[1], FakeVosk)
    assert both.members[1].phrases == BANK.keywords()
    # Whistle missing: the phrase recogniser still works alone
    alone = build_answer_recognizer(VoiceConfig(answer_engine="whistle", whistle_weights=str(tmp_path / "x.cact")), BANK)
    assert isinstance(alone, FakeVosk)
    assert isinstance(build_recognizer(VoiceConfig(recognizer="whistle", whistle_weights=str(weights)), ["clamp"]), WhistleRecognizer)
    assert isinstance(build_recognizer(VoiceConfig(recognizer="whistle", whistle_weights=str(tmp_path / "x.cact")), ["clamp"]), NullRecognizer)
    with pytest.raises(ValueError):
        build_answer_recognizer(VoiceConfig(answer_engine="magic"), BANK)


# --- the board check --------------------------------------------------------------


def test_eval_cases_fit_the_game_and_never_contain_a_phrase_the_keywords_catch(monkeypatch, weights, capsys):
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "tools"))
    import needle_eval

    matcher, keywords = CommandMatcher(DEFAULT_COMMANDS), KeywordEvaluator()
    script = {}
    for said, expected in needle_eval.COMMAND_CASES:
        assert expected is None or expected in DEFAULT_COMMANDS
        hit = matcher.interpret(said)
        assert hit is None or hit.score < 1.0, f"{said!r} never reaches the model"
        if expected is not None:
            name = next(a.name for a in ActionCatalog().actions() if expected in a.command_words())
            script[said] = [(name, {"choice": expected} if name == "select_instrument" else {}, 0.8)]
    for question_id, said, expected in needle_eval.ANSWER_CASES:
        question = BANK.get(question_id)
        assert question is not None and (expected is None or expected in question.options)
        assert not keywords.evaluate(question, said).named, f"{said!r} never reaches the model"
        if expected is not None:
            script[said] = [("answer", {"choice": expected}, 0.8)]
    use(monkeypatch, FakeCactus(script))
    assert needle_eval.main([str(weights)]) == 0  # a model that answers as hoped passes
    assert f"{len(needle_eval.COMMAND_CASES) + len(needle_eval.ANSWER_CASES)}/" in capsys.readouterr().out
    use(monkeypatch, FakeCactus({}))
    assert needle_eval.main([str(weights), "--json"]) == 1  # one that never calls a tool does not
