from trainer.core.config import DEFAULT_COMMANDS, DEFAULT_TREATMENTS, TOOL_WORDS
from trainer.game.actions import MODEL_ACTIONS, ActionCatalog


def test_every_command_word_is_reachable_through_a_tool_call():
    catalog = ActionCatalog()
    reachable = set()
    for schema in catalog.schemas():
        params = schema["parameters"]["properties"]
        enums = {name: spec for name, spec in params.items() if "enum" in spec}
        if not enums:
            reachable.add(catalog.command_word(schema["name"]))
        for name, spec in enums.items():
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


def test_needle_gets_the_orders_only_each_with_a_drug_trigger_and_an_amount():
    catalog = ActionCatalog(MODEL_ACTIONS)
    schemas = catalog.schemas()
    assert {s["name"] for s in schemas} == {"set_oxygen", "give_propofol", "give_adrenaline"}
    assert {w for a in MODEL_ACTIONS for w in a.command_words()} == set(DEFAULT_TREATMENTS)
    assert not set(DEFAULT_TREATMENTS) & set(DEFAULT_COMMANDS)  # the two paths share no word
    assert all(s["triggers"] for s in schemas)
    propofol = catalog.get("give_propofol").schema()["parameters"]
    assert propofol["properties"]["milligrams"] == {"type": "integer", "minimum": 5, "maximum": 200, "description": "dose in milligrams"}
    assert propofol["required"] == ["milligrams"]


def test_a_call_gives_its_amount_clamped_to_the_tool_range():
    catalog = ActionCatalog(MODEL_ACTIONS)
    assert catalog.amount("give_propofol", {"milligrams": 30}) == 30.0
    assert catalog.amount("set_oxygen", {"percent": 150}) == 100.0
    assert catalog.amount("give_adrenaline", {"micrograms": "ten"}) is None
    assert catalog.amount("give_adrenaline", {}) is None and catalog.amount("nope", {"x": 1}) is None
    assert catalog.command_word("give_propofol", {"milligrams": 30}) == "propofol"


def test_triggers_are_valid_regular_expressions_that_hear_the_drug():
    import re

    catalog = ActionCatalog(MODEL_ACTIONS)
    heard = {"set_oxygen": "oxygen to 60 please", "give_propofol": "propofol 30", "give_adrenaline": "give 10 of epinephrine"}
    for name, said in heard.items():
        assert any(re.search(t, said) for t in catalog.get(name).triggers), name
    assert not any(re.search(t, "his sats look good now") for a in MODEL_ACTIONS for t in a.triggers)
