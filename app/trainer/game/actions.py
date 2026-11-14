"""Everything a player can ask the game to do, described as tool schemas.

The game itself still runs on command words (`CommandEvent.word`). This
catalogue is the bridge for a tool-calling model: it hands the model the
schemas and turns the model's call back into a command word, so
`GameEngine.on_command` needs no change. See docs/needle-integration.md.

`triggers` are regular expressions the Cactus runtime matches against the
request (a documented field of its tool schema). Measured on 14 Nov 2026,
they decide whether Needle picks the right one of several tools: without
them every rung tested picked the same tool for almost every sentence. The
nurse's tools trigger on the drug's names, and their amount is an integer
parameter: the runtime flags an amount that is not in the sentence
("ungrounded"), so talk without a number gives no order.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from ..core.config import TOOL_WORDS

INSTRUMENT_HELP = (
    "forceps: picks up and removes foreign objects (splinter, glass, needle). "
    "swab: wipes away blood that hides the wound. "
    "clamp: stops a bleeding vessel. "
    "scalpel: cuts open a sealed passage."
)


@dataclass(frozen=True)
class Amount:
    """An integer parameter: how much of a drug, or a setting."""

    name: str  # the parameter's name, e.g. "milligrams"
    minimum: int
    maximum: int
    help: str  # tells the model what the number is


@dataclass(frozen=True)
class GameAction:
    name: str
    description: str
    command: str = ""  # the command word; "" when a parameter supplies it
    parameters: Mapping[str, tuple[str, ...]] = field(default_factory=dict)  # name -> allowed values
    triggers: tuple[str, ...] = ()  # request regexes for the runtime (ECMAScript syntax)
    amount: Amount | None = None

    def command_words(self) -> tuple[str, ...]:
        if self.command:
            return (self.command,)
        return tuple(v for values in self.parameters.values() for v in values)

    def schema(self, allowed: Sequence[str] | None = None) -> dict:
        properties: dict[str, dict] = {}
        for name, values in self.parameters.items():
            usable = [v for v in values if allowed is None or v in allowed]
            properties[name] = {"type": "string", "enum": usable}
        if self.amount is not None:
            a = self.amount
            properties[a.name] = {"type": "integer", "minimum": a.minimum, "maximum": a.maximum, "description": a.help}
        schema = {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": properties, "required": list(properties)},
        }
        if self.triggers:
            schema["triggers"] = list(self.triggers)
        return schema


# The nurse's orders on the vitals monitor: the drug is named, the amount said.
TREATMENT_ACTIONS: tuple[GameAction, ...] = (
    GameAction(
        "set_oxygen",
        "Set the oxygen fraction the patient breathes, in percent.",
        command="oxygen",
        triggers=(r"\b(oxygen|o2|fio2)\b",),
        amount=Amount("percent", 21, 100, "oxygen in percent, 21 to 100"),
    ),
    GameAction(
        "give_propofol",
        "Give propofol to deepen the anaesthesia.",
        command="propofol",
        triggers=(r"\b(propofol|propophol)\b",),
        amount=Amount("milligrams", 5, 200, "dose in milligrams"),
    ),
    GameAction(
        "give_adrenaline",
        "Give adrenaline to raise the blood pressure.",
        command="adrenaline",
        triggers=(r"\b(adrenalin\w*|epinephrin\w*)\b",),
        amount=Amount("micrograms", 5, 100, "dose in micrograms"),
    ),
)

# Words Whistle is biased towards when it hears an order (its `keywords`):
# the drugs and their units.
ORDER_WORDS: tuple[str, ...] = (
    "oxygen", "FiO2", "percent", "propofol", "milligrams", "adrenaline", "epinephrine", "micrograms",
)

SELECT_INSTRUMENT = GameAction(
    "select_instrument",
    "Hand the surgeon an instrument. " + INSTRUMENT_HELP,
    parameters={"instrument": TOOL_WORDS},
    triggers=(r"\b(hand|pass|give me|need|instrument|tool|pick|grab|pull|remove|wipe|soak|mop|dab|bleed\w*|vessel|squeeze|pinch|cut|blade|incision|slice|splinter|glass|shard)\b",),
)

DEFAULT_ACTIONS: tuple[GameAction, ...] = (
    SELECT_INSTRUMENT,
    *TREATMENT_ACTIONS,
    GameAction("steady", "Precision mode for a few seconds: slower, finer movement.", command="steady"),
    GameAction("light", "Switch on the light to see the dark part of the wound.", command="light"),
    GameAction("cancel", "Undo the last instrument change.", command="cancel"),
    GameAction("repeat", "Say the last spoken line again.", command="repeat"),
    GameAction("help", "List the commands that work right now.", command="help"),
    GameAction("pause", "Pause the round.", command="pause"),
    GameAction("resume", "Continue a paused round.", command="continue"),
    GameAction("new_game", "Start a new round.", command="new game"),
)

# What Needle gets: the nurse's orders only. Whistle and Needle serve the
# vitals monitor; every older command stays on the Vosk grammar, and neither
# path fires the other's commands. (Measured 14 Nov 2026: with the instrument
# tool added, Needle picked the wrong instrument for 16 of 16 clamp and
# scalpel sentences. The runtime's docs advise five tools or fewer.)
MODEL_ACTIONS: tuple[GameAction, ...] = TREATMENT_ACTIONS


class ActionCatalog:
    def __init__(self, actions: Sequence[GameAction] = DEFAULT_ACTIONS) -> None:
        self._actions = {a.name: a for a in actions}

    def actions(self) -> list[GameAction]:
        return list(self._actions.values())

    def get(self, name: str) -> GameAction | None:
        return self._actions.get(name)

    def schemas(self, allowed: Sequence[str] | None = None) -> list[dict]:
        """Tool schemas for the model. `allowed` (command words, e.g. from
        `GameEngine.available_commands()`) drops every action and every
        parameter value that makes no sense right now."""
        out = []
        for action in self._actions.values():
            if allowed is not None and not any(w in allowed for w in action.command_words()):
                continue
            out.append(action.schema(allowed))
        return out

    def amount(self, name: str, arguments: Mapping[str, object] | None = None) -> float | None:
        """The amount in a tool call, clamped to the tool's range; None if it has none."""
        action = self._actions.get(name)
        if action is None or action.amount is None:
            return None
        value = (arguments or {}).get(action.amount.name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return float(min(action.amount.maximum, max(action.amount.minimum, value)))

    def command_word(self, name: str, arguments: Mapping[str, object] | None = None) -> str | None:
        """The command word for a tool call, or None if the call is not valid."""
        action = self._actions.get(name)
        if action is None:
            return None
        if action.command:
            return action.command
        arguments = arguments or {}
        for param, values in action.parameters.items():
            value = arguments.get(param)
            if isinstance(value, str) and value.lower() in values:
                return value.lower()
        return None
