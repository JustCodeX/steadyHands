from trainer.core.config import DEFAULT_COMMANDS
from trainer.voice.command_matcher import CommandMatcher


def test_exact_and_phrase_match():
    m = CommandMatcher(DEFAULT_COMMANDS)
    assert m.match("forceps").word == "forceps"
    assert m.match("please the clamp now").word == "clamp"
    assert m.match("new game").word == "new game"
    assert m.match("tweezers").word == "forceps"


def test_fuzzy_match_and_rejection():
    m = CommandMatcher(DEFAULT_COMMANDS)
    assert m.match("forcep").word == "forceps"
    assert m.match("banana milkshake") is None
    assert m.match("") is None


def test_phrases_list_has_every_word():
    m = CommandMatcher(DEFAULT_COMMANDS)
    for word in DEFAULT_COMMANDS:
        assert word in m.phrases()


def test_allowed_limits_the_commands_considered():
    m = CommandMatcher(DEFAULT_COMMANDS)
    assert m.interpret("clamp").word == "clamp"
    assert m.interpret("clamp", allowed=["forceps", "pause"]) is None
    assert m.interpret("please pause", allowed=["forceps", "pause"]).word == "pause"
