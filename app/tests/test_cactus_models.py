"""Needle and Whistle against a stand-in for the Cactus runtime.

The stand-in follows cactus-compute 4.2.0 as read from its source: tools are
JSON schemas, `complete()` returns the proposed calls without executing them,
a call below confidence 0.1 lands in "suppressed_calls", a number argument
that is not in the text is listed in validation.ungrounded, `reset()` must
come before every independent text, and `close()` ends the worker process. The
real runtime is covered by tests/test_cactus_real.py.
"""
import json
import os
import sys
import types

import numpy as np
import pytest

from trainer.cactus_models import needle_agent, whistle_recognizer
from trainer.cactus_models.needle_agent import NeedleAgent, tool_schema
from trainer.cactus_models.needle_evaluator import NeedleEvaluator
from trainer.cactus_models.needle_orders import NeedleOrders
from trainer.cactus_models.runtime import load_cactus
from trainer.cactus_models.whistle_recognizer import WhistleRecognizer
from trainer.core.config import DEFAULT_COMMANDS, DEFAULT_TREATMENTS, QuizConfig, VoiceConfig
from trainer.game.actions import MODEL_ACTIONS, ActionCatalog
from trainer.quiz import KeywordEvaluator, QuestionBank
from trainer.voice.command_matcher import CommandMatcher
from trainer.voice.named_orders import NamedOrders
from trainer.voice.recognizer import EnsembleRecognizer, NullRecognizer
from trainer.voice.voice_service import (
    build_answer_recognizer,
    build_evaluator,
    build_sentence_recognizer,
    build_treatment_interpreter,
)

BANK = QuestionBank.load(QuizConfig().questions_file)


class FakeAgent:
    def __init__(self, tools, system, weights, script, auto_date=True):
        assert isinstance(tools, str), "tools go to the runtime as JSON"
        self.tools = {t["name"]: t for t in json.loads(tools)}
        self.system, self.weights, self.script, self.auto_date = system, weights, script, auto_date
        self.fresh = False
        self.closed = False
        self.heard = []

    def reset(self):
        self.fresh = True

    def close(self):
        self.closed = True

    def complete(self, text):
        assert not self.closed
        assert self.fresh, "reset() must be called before every independent text"
        self.fresh = False
        self.heard.append(text)
        planned = self.script.get(text, [])
        if isinstance(planned, Exception):
            raise planned
        calls, confidence, ungrounded = [], 0.7, []
        for name, arguments, conf in planned:
            tool = self.tools[name]
            properties = tool["parameters"]["properties"]
            assert set(arguments) == set(properties)
            for key, value in arguments.items():
                if properties[key]["type"] == "integer":
                    assert properties[key]["minimum"] <= value <= properties[key]["maximum"]
                    if str(value) not in text:  # the runtime's grounding check
                        ungrounded.append(f"{name}.{key}")
                else:
                    assert value in properties[key]["enum"], f"{value!r} is not allowed for {name}.{key}"
            calls.append({"name": name, "arguments": arguments})
            confidence = conf
        gated = confidence is not None and confidence < 0.1  # the runtime's own gate: reported, not proposed
        return {
            "type": "call",
            "function_calls": [] if gated else calls,
            "suppressed_calls": calls if gated else [],
            "confidence": confidence,
            "validation": {"ungrounded": ungrounded, "negation": False},
        }


class FakeCactus:
    def __init__(self, script=None, heard_text="clamp"):
        self.script = script or {}
        self.agents = []
        self.transcriptions = []
        self.heard_text = heard_text

    def Cactus(self, tools, system, weights, auto_date=True):  # noqa: N802
        self.agents.append(FakeAgent(tools, system, weights, self.script, auto_date))
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
    tool = tool_schema("answer", "Record the answer.", {"choice": (["clamp", "swab"], "the option meant")})
    assert tool == {
        "name": "answer",
        "description": "Record the answer.",
        "parameters": {
            "type": "object",
            "properties": {"choice": {"type": "string", "enum": ["clamp", "swab"], "description": "the option meant"}},
            "required": ["choice"],
        },
    }
    assert tool_schema("steady", "Precision mode.")["parameters"] == {"type": "object", "properties": {}, "required": []}


def make_agent(monkeypatch, weights, script):
    fake = use(monkeypatch, FakeCactus(script))
    tools = [tool_schema("steady", "Precision mode."), tool_schema("pick", "Pick one.", {"choice": (["a", "b"], "which")})]
    return fake, NeedleAgent(weights, "system text", tools)


def test_agent_returns_the_call_the_model_made(monkeypatch, weights):
    fake, agent = make_agent(monkeypatch, weights, {"the first": [("pick", {"choice": "a"}, 0.7)], "slow down": [("steady", {}, 0.9)]})
    call = agent.call("the first")
    assert (call.name, call.arguments, call.confidence) == ("pick", {"choice": "a"}, 0.7)
    assert agent.call("slow down").name == "steady"  # the fake fails if reset() was skipped in between
    assert len(fake.agents) == 1
    made = fake.agents[0]
    assert made.system == "system text" and made.weights == str(weights) and made.auto_date is False
    agent.unload()
    assert made.closed  # the worker process ends with the agent


def test_agent_gives_nothing_when_the_model_is_unsure_or_wants_two_things(monkeypatch, weights):
    fake, agent = make_agent(
        monkeypatch,
        weights,
        {
            "held back": [("pick", {"choice": "a"}, 0.05)],
            "both": [("pick", {"choice": "a"}, 0.8), ("pick", {"choice": "b"}, 0.8)],
            "twice": [("pick", {"choice": "a"}, 0.8), ("pick", {"choice": "a"}, 0.8)],
            "no head": [("pick", {"choice": "b"}, None)],
        },
    )
    assert agent.call("what a nice day") is None  # no tool fits
    assert agent.call("held back") is None  # below the runtime's gate
    assert agent.call("both") is None
    assert agent.call("twice").arguments == {"choice": "a"}
    assert agent.call("no head").confidence == 1.0  # weights without a confidence head: no gate
    agent.min_confidence = 0.03
    assert agent.call("held back").arguments == {"choice": "a"}  # a looser gate than the runtime's takes suppressed calls
    agent.min_confidence = 0.9
    assert agent.call("twice") is None  # our own, stricter gate


def test_calls_keep_grounded_orders_and_the_last_correction(monkeypatch, weights):
    fake = use(monkeypatch, FakeCactus({
        "propofol 20 and oxygen 60": [("give_propofol", {"milligrams": 20}, 0.8), ("set_oxygen", {"percent": 60}, 0.8)],
        "propofol 20 no wait 30": [("give_propofol", {"milligrams": 20}, 0.6), ("give_propofol", {"milligrams": 30}, 0.6)],
        "propofol": [("give_propofol", {"milligrams": 50}, 0.4)],  # an invented amount
        "held back": [("give_propofol", {"milligrams": 5}, 0.05)],
    }))
    agent = NeedleAgent(weights, "s", ActionCatalog(MODEL_ACTIONS).schemas())
    assert [(c.name, c.arguments) for c in agent.calls("propofol 20 and oxygen 60")] == [
        ("give_propofol", {"milligrams": 20}), ("set_oxygen", {"percent": 60})]
    assert [c.arguments for c in agent.calls("propofol 20 no wait 30")] == [{"milligrams": 30}]
    assert agent.calls("propofol") == []  # ungrounded: not in the text
    assert agent.calls("held back") == [] and agent.calls("nice day") == []
    assert len(fake.agents) == 1


def test_agent_needs_its_weights(monkeypatch, tmp_path):
    use(monkeypatch, FakeCactus())
    with pytest.raises(FileNotFoundError):
        NeedleAgent(tmp_path / "missing.cact", "s", lambda record: []).load()


# --- NeedleOrders -------------------------------------------------------------------


def test_orders_need_a_drug_named_and_read_its_amount(monkeypatch, weights):
    script = {
        "give him 30 milligrams of propofol.": [("give_propofol", {"milligrams": 30}, 0.8)],
        "propofol 40 and oxygen to 70.": [("give_propofol", {"milligrams": 40}, 0.8), ("set_oxygen", {"percent": 70}, 0.8)],
        "more propofol.": [("give_propofol", {"milligrams": 50}, 0.3)],  # the model invents an amount
        "adrenaline 300.": [("give_adrenaline", {"micrograms": 100}, 0.7)],  # clamped by the schema; not in the text
        "epinephrine 10 now.": RuntimeError("engine fell over"),
    }
    fake = use(monkeypatch, FakeCactus(script))
    orders = NeedleOrders(DEFAULT_TREATMENTS, weights)
    agent = fake.agents[0]
    assert sorted(agent.tools) == sorted(a.name for a in MODEL_ACTIONS)  # the three drugs, nothing else
    assert agent.tools["give_propofol"]["parameters"]["properties"]["milligrams"]["type"] == "integer"

    def said(text):
        return [(m.word, m.amount) for m in orders.orders(text)]

    assert said("give him 30 milligrams of propofol") == [("propofol", 30.0)]
    assert said("propofol 40 and oxygen to 70") == [("propofol", 40.0), ("oxygen", 70.0)]
    assert said("more propofol") == [("propofol", None)]  # named, no usable amount: standard dose
    assert said("adrenaline 300") == [("adrenaline", None)]
    assert said("epinephrine 10 now") == [("adrenaline", None)]  # a failing model: standard dose
    heard = len(agent.heard)
    assert said("his sats look good now") == [] and said("give me the clamp") == [] and said("") == []
    assert len(agent.heard) == heard  # no drug named: the model does not run
    assert orders.phrases() == ["oxygen", "propofol", "adrenaline", "epinephrine"]
    assert NeedleOrders.sentence("push 10 micrograms of adrenaline") == "push 10 micrograms of adrenaline."
    assert NeedleOrders.sentence("Oxygen 60!") == "Oxygen 60!"


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
    choice = agent.tools["answer"]["parameters"]["properties"]["choice"]
    assert choice["enum"] == list(question.options)
    assert "clamp (clamp, clamps" in choice["description"]

    assert evaluator.evaluate(question, "i would take a clamp").choice == "clamp"
    assert evaluator.evaluate(question, "the forceps no wait the clamp").choice is None  # two options: ask again
    assert agent.heard == []

    verdict = evaluator.evaluate(question, "the thing you squeeze the vessel shut with")
    assert (verdict.choice, verdict.score) == ("clamp", 0.6)
    assert evaluator.evaluate(question, "the sharp one").choice == "scalpel"  # a wrong answer, understood
    assert evaluator.evaluate(question, "no idea to be honest").choice is None

    other = BANK.get("fast_pulse")
    evaluator.prepare(other)
    assert len(fake.agents) == 2 and fake.agents[1].tools["answer"]["parameters"]["properties"]["choice"]["enum"] == ["yes", "no"]
    assert agent.closed  # the previous question's worker process is gone


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


def test_config_selects_needle_for_treatments_and_falls_back_without_it(monkeypatch, weights, tmp_path, caplog):
    use(monkeypatch, FakeCactus())
    with_needle = VoiceConfig(treatment_interpreter="needle", evaluator="needle", needle_weights=str(weights))
    treatments = build_treatment_interpreter(with_needle, DEFAULT_TREATMENTS)
    assert isinstance(treatments, NeedleOrders) and treatments.require_trigger
    assert isinstance(build_evaluator(with_needle), NeedleEvaluator)
    missing = VoiceConfig(treatment_interpreter="needle", evaluator="needle", needle_weights=str(tmp_path / "missing.cact"))
    with caplog.at_level("ERROR"):
        fallback = build_treatment_interpreter(missing, DEFAULT_TREATMENTS)
        assert type(build_evaluator(missing)) is KeywordEvaluator
    assert isinstance(fallback, NamedOrders) and [(m.word, m.amount) for m in fallback.orders("give him oxygen")] == [("oxygen", None)]
    assert caplog.text.count("Needle unavailable") == 2


def test_config_selects_whistle_for_answers_and_for_sentences(monkeypatch, weights, tmp_path):
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
    # sentences for the treatments
    whistle = build_sentence_recognizer(VoiceConfig(sentence_recognizer="whistle", whistle_weights=str(weights)), DEFAULT_TREATMENTS)
    assert isinstance(whistle, WhistleRecognizer) and "adrenaline" in whistle._keywords
    assert build_sentence_recognizer(VoiceConfig(sentence_recognizer="whistle", whistle_weights=str(tmp_path / "x.cact")), DEFAULT_TREATMENTS) is None
    assert build_sentence_recognizer(VoiceConfig(), DEFAULT_TREATMENTS) is None  # the default needs no model
    assert isinstance(build_sentence_recognizer(VoiceConfig(sentence_recognizer="vosk"), DEFAULT_TREATMENTS), FakeVosk)
    with pytest.raises(ValueError):
        build_answer_recognizer(VoiceConfig(answer_engine="magic"), BANK)
    with pytest.raises(ValueError):
        build_sentence_recognizer(VoiceConfig(sentence_recognizer="magic"), DEFAULT_TREATMENTS)


# --- the board check --------------------------------------------------------------


def test_eval_cases_fit_the_game_and_never_contain_a_command_phrase(monkeypatch, weights, capsys):
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "tools"))
    import needle_eval

    cases = needle_eval.load_cases()
    keywords = KeywordEvaluator()
    named = NamedOrders(DEFAULT_TREATMENTS)
    tool_of = {a.command: a for a in MODEL_ACTIONS}
    script = {}
    for case in cases["orders"]:
        said, expected, kind = case["said"], case["expected"], case["kind"]
        assert kind in ("order", "named", "talk", "named_talk")
        assert all(word in DEFAULT_TREATMENTS for word, _ in expected)
        if kind in ("talk",):
            assert not expected and not named.orders(said)
        if kind == "named":
            assert all(amount is None for _, amount in expected)
        if kind == "order":
            assert all(amount is not None for _, amount in expected)
            planned = []
            for word, amount in expected:
                action = tool_of[word]
                planned.append((action.name, {action.amount.name: int(amount)}, 0.8))
            # numbers said in words ("fifty") are not grounded by the stand-in's digit check: leave them out
            if all(str(int(amount)) in said for _, amount in expected):
                script[said] = planned
    assert sum(c["kind"] == "talk" for c in cases["orders"]) >= 10  # enough talk to count false orders
    for case in cases["answers"]:
        question = BANK.get(case["question"])
        assert question is not None and (case["expected"] is None or case["expected"] in question.options)
        assert not keywords.evaluate(question, case["said"]).named, f"{case['said']!r} never reaches the model"
        if case["expected"] is not None:
            script[case["said"]] = [("answer", {"choice": case["expected"]}, 0.8)]
    use(monkeypatch, FakeCactus(script))
    needle_eval.main([str(weights), "--quiz", "--json"])
    import json as _json

    result = _json.loads(capsys.readouterr().out)[0]
    assert result["false_orders"] == 0 and result["named"] == "6/6"
    assert result["answers"] == f"{len(cases['answers'])}/{len(cases['answers'])}"
    assert result["orders"] == f"{len(script) - sum(c['expected'] is not None for c in cases['answers'])}/{sum(c['kind'] == 'order' for c in cases['orders'])}"
    use(monkeypatch, FakeCactus({}))
    assert needle_eval.main([str(weights), "--json"]) == 1  # one that never calls a tool does not pass
