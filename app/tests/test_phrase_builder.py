from trainer.audio.lines import all_lines, number_id
from trainer.audio.phrase_builder import PhraseBuilder
from trainer.core.events import RoundResult


def test_result_phrase_uses_existing_line_ids():
    lines = all_lines()
    r = RoundResult(level_name="L", won=True, time_s=48.3, contacts=2, steadiness=85.0, calls_correct=3, calls_wrong=0, steady_uses=1)
    ids = PhraseBuilder.result(r)
    assert ids[:3] == ["win", number_id(48), "seconds"]
    assert all(i in lines for i in ids)


def test_event_phrases_exist():
    lines = all_lines()
    for kind in ("hit", "item_out", "clamped", "pardon", "wrong_tool", "bleed_timeout", "win", "lose"):
        for i in PhraseBuilder.for_event(kind, "", 0):
            assert i in lines
    assert PhraseBuilder.for_event("tool_changed", "clamp", 0) == ["clamp"]
    assert PhraseBuilder.for_event("help", "forceps,steady", 0) == ["you_can_say", "forceps", "steady"]
