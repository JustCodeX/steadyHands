from trainer.core.config import DEFAULT_COMMANDS, DEFAULT_TREATMENTS, TOOL_WORDS
from trainer.game.actions import MODEL_ACTIONS, ActionCatalog


def test_every_command_word_is_reachable_through_a_tool_call():
    catalog = ActionCatalog()
    reachable = set()
    for schema in catalog.schemas():
        params = schema["parameters"]["properties"]
        if not params:
            reachable.add(catalog.command_word(schema["name"]))
        for name, spec in params.items():
            for value in spec["enum"]:
                reachable.add(catalog.command_word(schema["name"], {name: value}))
    assert reachable == set(DEFAULT_COMMANDS) | set(DEFAULT_TREATMENTS)


def test_tool_call_becomes_a_command_word():
    catalog = ActionCatalog()
    assert catalog.command_word("select_instrument", {"instrument": "Clamp"}) == "clamp"
    assert catalog.command_word("resume") == "continue"
    assert catalog.command_word("new_game", {}) == "new game"


def test_invalid_tool_calls_give_nothing():
    catalog = ActionCatalog()
    assert catalog.command_word("select_instrument", {"instrument": "hammer"}) is None
    assert catalog.command_word("select_instrument") is None
    assert catalog.command_word("launch_rocket") is None


def test_schemas_shrink_to_what_is_allowed_now():
    catalog = ActionCatalog()
    assert len(catalog.schemas()) == 12
    assert catalog.schemas()[0]["parameters"]["properties"]["instrument"]["enum"] == list(TOOL_WORDS)
    now = catalog.schemas(allowed=["clamp", "forceps", "steady", "cancel", "pause"])
    assert [s["name"] for s in now] == ["select_instrument", "steady", "cancel", "pause"]
    assert now[0]["parameters"]["properties"]["instrument"]["enum"] == ["forceps", "clamp"]
    assert now[0]["parameters"]["required"] == ["instrument"]


def test_needle_gets_the_treatments_only_each_with_triggers():
    schemas = ActionCatalog(MODEL_ACTIONS).schemas()
    assert {s["name"] for s in schemas} == {"give_oxygen", "deepen_anaesthesia", "give_adrenaline"}
    assert {w for a in MODEL_ACTIONS for w in a.command_words()} == set(DEFAULT_TREATMENTS)
    assert not set(DEFAULT_TREATMENTS) & set(DEFAULT_COMMANDS)  # the two paths share no word
    assert all(s["triggers"] for s in schemas)


def test_triggers_are_valid_regular_expressions_that_hear_the_symptom():
    import re

    catalog = ActionCatalog(MODEL_ACTIONS)
    heard = {
        "give_oxygen": "he can't breathe",
        "deepen_anaesthesia": "the patient is waking up",
        "give_adrenaline": "his pressure is dropping",
    }
    for name, said in heard.items():
        assert any(re.search(t, said) for t in catalog.get(name).triggers), name
