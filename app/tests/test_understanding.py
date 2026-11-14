"""The two speech paths: older commands on the Vosk grammar, treatments through
Whistle and Needle, and neither firing the other's words."""
import json
import random

from trainer.core.config import DEFAULT_COMMANDS, DEFAULT_TREATMENTS, GameConfig, VitalsConfig, VoiceConfig
from trainer.core.event_bus import EventBus
from trainer.core.events import CommandEvent, GameEvent, InstructionWindow, MisheardEvent
from trainer.game.collision_map import CollisionMap
from trainer.game.engine import GameEngine
from trainer.game.level import Level, LevelCatalog
from trainer.voice.command_matcher import CommandMatcher
from trainer.voice.interpreter import CommandInterpreter, Match
from trainer.voice.recognizer import SpeechRecognizer, Transcript
from trainer.voice.understanding import CommandUnderstanding
from trainer.voice.vad import Segmenter
from trainer.voice.voice_service import VoiceService, command_phrases


class Scripted(SpeechRecognizer):
    def __init__(self, text="", conf=0.9):
        self.text, self.conf = text, conf
        self.finished = 0
        self.fed = 0

    def accept(self, pcm):
        self.fed += 1

    def finish(self):
        self.finished += 1
        return Transcript(self.text, self.conf)


class FakeNeedle(CommandInterpreter):
    """Phrases first, then a scripted 'model'."""

    def __init__(self, script):
        self.script = script
        self.asked = []
        self.phrases_matcher = CommandMatcher(DEFAULT_TREATMENTS)

    def interpret(self, text, allowed=None):
        hit = self.phrases_matcher.interpret(text)
        if hit is not None and hit.score == 1.0:
            return hit
        self.asked.append(text)
        word = self.script.get(text)
        return Match(word=word, score=0.7) if word else None

    def phrases(self):
        return self.phrases_matcher.phrases()


def understanding(grammar_text, grammar_conf=0.9, sentence_text="", sentence_conf=0.95, script=None, sentence=True):
    vosk = Scripted(grammar_text, grammar_conf)
    whistle = Scripted(sentence_text, sentence_conf) if sentence else None
    needle = FakeNeedle(script or {})
    u = CommandUnderstanding(vosk, CommandMatcher(DEFAULT_COMMANDS), 0.6, DEFAULT_TREATMENTS, whistle, needle if sentence else None)
    return u, vosk, whistle, needle


def test_a_short_call_takes_the_fast_path_and_whistle_never_runs():
    u, vosk, whistle, needle = understanding("clamp", sentence_text="clamp")
    got = u.finish(0.6, expecting=True)
    assert (got.kind, got.word) == ("command", "clamp") and not got.sentence_ran
    assert whistle.finished == 0 and needle.asked == []


def test_during_an_alarm_a_sentence_becomes_a_treatment_even_if_the_grammar_forced_a_word():
    u, vosk, whistle, needle = understanding("steady", sentence_text="he can't breathe", script={"he can't breathe": "oxygen"})
    got = u.finish(1.8, expecting=True)
    assert (got.kind, got.word) == ("treatment", "oxygen") and got.sentence_ran
    assert needle.asked == ["he can't breathe"]


def test_outside_an_alarm_needle_is_not_asked_and_the_grammar_stands():
    u, vosk, whistle, needle = understanding("steady", sentence_text="he can't breathe", script={"he can't breathe": "oxygen"})
    got = u.finish(1.8, expecting=False)
    assert (got.kind, got.word) == ("command", "steady") and needle.asked == []
    u, *_ = understanding("", sentence_text="his sats look good now", script={"his sats look good now": "oxygen"})
    assert u.finish(1.5, expecting=False).kind == "ignored"  # status talk outside an alarm: nothing


def test_a_treatment_said_by_name_counts_at_any_time():
    u, vosk, whistle, needle = understanding("", sentence_text="give him some adrenaline now")
    got = u.finish(1.6, expecting=False)
    assert (got.kind, got.word, got.confidence) == ("treatment", "adrenaline", 1.0) and needle.asked == []


def test_a_sentence_without_a_treatment_is_unclear_only_while_the_nurse_waits():
    u, *_ = understanding("", sentence_text="what a lovely day")
    got = u.finish(1.5, expecting=True)
    assert (got.kind, got.reason) == ("unclear", "no_instruction")
    u, *_ = understanding("", sentence_text="what a lovely day")
    assert u.finish(1.5, expecting=False).kind == "ignored"


def test_whistle_unsure_means_no_treatment():
    u, vosk, whistle, needle = understanding("", sentence_text="give him oxygen", sentence_conf=0.3)
    assert u.finish(1.5, expecting=False).kind == "ignored"


def test_an_older_command_in_a_sentence_still_works():
    u, vosk, whistle, needle = understanding("clamp", sentence_text="give me the clamp please")
    got = u.finish(1.6, expecting=True)
    assert (got.kind, got.word) == ("command", "clamp") and got.sentence_ran  # the grammar's word stands


def test_without_a_sentence_path_the_treatments_join_the_grammar():
    phrases = command_phrases(DEFAULT_COMMANDS, DEFAULT_TREATMENTS, sentence_path=False)
    assert "oxygen" in phrases and "clamp" in phrases
    assert "oxygen" not in command_phrases(DEFAULT_COMMANDS, DEFAULT_TREATMENTS, sentence_path=True)
    vosk = Scripted("oxygen", 0.9)
    u = CommandUnderstanding(vosk, CommandMatcher(phrases), 0.6, DEFAULT_TREATMENTS)
    assert (u.finish(0.7, expecting=True).kind, u.finish(0.7, expecting=True).word) == ("command", "oxygen")
    low = CommandUnderstanding(Scripted("clamp", 0.3), CommandMatcher(phrases), 0.6, DEFAULT_TREATMENTS)
    assert low.finish(0.5, expecting=False).reason == "low_confidence"


def test_both_recognisers_hear_the_segment():
    u, vosk, whistle, _ = understanding("clamp")
    u.accept(b"\0\0" * 320)
    assert vosk.fed == 1 and whistle.fed == 1


# --- the voice service with an instruction window ------------------------------------


class Silent:
    running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def read(self, timeout=0.1):
        return None


def test_voice_service_publishes_treatments_and_pardon_while_the_window_is_open():
    bus = EventBus()
    whistle = Scripted("he can't breathe")
    svc = VoiceService(
        bus,
        VoiceConfig(),
        DEFAULT_COMMANDS,
        recognizer=Scripted(""),
        audio=Silent(),
        treatments=DEFAULT_TREATMENTS,
        sentence_recognizer=whistle,
        treatment_interpreter=FakeNeedle({"he can't breathe": "oxygen"}),
    )
    seen = []
    bus.subscribe(CommandEvent, seen.append)
    bus.subscribe(MisheardEvent, seen.append)
    svc.handle_segment(1.0, 1.6)
    bus.dispatch()
    assert seen == []  # no alarm: the model is not asked, the sentence is ignored
    bus.publish(InstructionWindow(open=True))
    bus.dispatch()
    svc.handle_segment(2.0, 1.6)
    whistle.text = "hmm what was that"
    svc.handle_segment(3.0, 1.6)
    bus.dispatch()
    assert [type(e).__name__ for e in seen] == ["CommandEvent", "MisheardEvent"]
    assert seen[0].word == "oxygen" and seen[1].reason == "no_instruction"


# --- adaptive end of a segment ------------------------------------------------------------


def test_a_short_call_ends_quickly_and_a_sentence_survives_a_pause():
    seg = Segmenter(start_blocks=1, hangover_blocks=20, max_blocks=150, long_after_blocks=60, long_hangover_blocks=35, long_max_blocks=300)
    phases = [seg.update(True) for _ in range(30)] + [seg.update(False) for _ in range(20)]
    assert phases[-1] == "end" and seg.last_length == 30  # 0.6 s call, 400 ms of silence
    phases = [seg.update(True) for _ in range(80)] + [seg.update(False) for _ in range(25)]
    assert "end" not in phases  # a 500 ms pause in a sentence does not cut it
    phases = [seg.update(True) for _ in range(20)] + [seg.update(False) for _ in range(35)]
    assert phases[-1] == "end" and seg.last_length == 125
    phases = [seg.update(True) for _ in range(299)]
    assert "end" not in phases[:200]  # sentences may run longer than a call (6 s, not 3 s)


# --- the nurse asks again only while she waits ------------------------------------------------


class Catalog(LevelCatalog):
    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        self.dir = tmp_path / "01-test"
        self.dir.mkdir()
        data = {"name": "T", "time_limit_s": 120, "start": [20, 60], "targets": [{"id": "s", "position": [160, 60], "needs": "forceps"}],
                "vitals": {"episodes": 1, "kinds": ["spo2"]}}
        (self.dir / "level.json").write_text(json.dumps(data))

    def load(self, index):
        return Level.load(self.dir, mask=CollisionMap(200, 120, bytearray(200 * 120)))


def test_engine_opens_the_window_and_the_nurse_asks_again_then_names_the_options(tmp_path):
    bus = EventBus()
    vcfg = VitalsConfig(first_after_s=1.0, drift_to_critical_s=30.0, reminder_s=30.0)
    eng = GameEngine(bus, GameConfig(), Catalog(tmp_path), 200, 120, None, None, vcfg, random.Random(2))
    seen = []
    bus.subscribe(GameEvent, seen.append)
    bus.subscribe(InstructionWindow, seen.append)
    eng.start()
    eng.start_round()
    bus.publish(MisheardEvent(reason="no_instruction"))
    bus.dispatch()
    assert not [e for e in seen if isinstance(e, GameEvent) and e.kind == "pardon_doctor"]  # no alarm yet
    for _ in range(20):
        eng.tick(0.1)
    bus.dispatch()
    assert eng.vitals.alarm_open() and not [e for e in seen if isinstance(e, InstructionWindow)]  # drifting, not announced
    bus.publish(MisheardEvent(reason="no_instruction"))
    bus.dispatch()
    assert not [e for e in seen if isinstance(e, GameEvent) and e.kind == "pardon_doctor"]
    for _ in range(140):
        eng.tick(0.1)
    bus.dispatch()
    assert any(isinstance(e, GameEvent) and e.kind == "vital_alarm" for e in seen)
    assert [e.open for e in seen if isinstance(e, InstructionWindow)] == [True]
    for _ in range(2):
        bus.publish(MisheardEvent(reason="no_instruction"))
        bus.dispatch()
    nurse = [e.kind for e in seen if isinstance(e, GameEvent) and e.kind in ("pardon_doctor", "you_can_order")]
    assert nurse == ["pardon_doctor", "you_can_order"]
    bus.publish(CommandEvent(word="oxygen", confidence=0.8))
    bus.dispatch()
    eng.tick(0.1)
    bus.dispatch()
    assert [e.open for e in seen if isinstance(e, InstructionWindow)] == [True, False]
