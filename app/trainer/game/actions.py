"""Everything a player can ask the game to do, described as tool schemas.

The game itself still runs on command words (`CommandEvent.word`). This
catalogue is the bridge for a tool-calling model: it hands the model the
schemas and turns the model's call back into a command word, so
`GameEngine.on_command` needs no change. See docs/needle-integration.md.
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
class GameAction:
    name: str
    description: str
    command: str = ""  # the command word; "" when a parameter supplies it
    parameters: Mapping[str, tuple[str, ...]] = field(default_factory=dict)  # name -> allowed values

    def command_words(self) -> tuple[str, ...]:
        if self.command:
            return (self.command,)
        return tuple(v for values in self.parameters.values() for v in values)

    def schema(self, allowed: Sequence[str] | None = None) -> dict:
        properties = {}
        for name, values in self.parameters.items():
            usable = [v for v in values if allowed is None or v in allowed]
            properties[name] = {"type": "string", "enum": usable}
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"type": "object", "properties": properties, "required": list(properties)},
        }


DEFAULT_ACTIONS: tuple[GameAction, ...] = (
    GameAction(
        "select_instrument",
        "Hand the surgeon an instrument. " + INSTRUMENT_HELP,
        parameters={"instrument": TOOL_WORDS},
    ),
    GameAction("steady", "Precision mode for a few seconds: slower, finer movement.", command="steady"),
    GameAction("light", "Switch on the light to see the dark part of the wound.", command="light"),
    GameAction("cancel", "Undo the last instrument change.", command="cancel"),
    GameAction("repeat", "Say the last spoken line again.", command="repeat"),
    GameAction("help", "List the commands that work right now.", command="help"),
    GameAction("pause", "Pause the round.", command="pause"),
    GameAction("resume", "Continue a paused round.", command="continue"),
    GameAction("new_game", "Start a new round.", command="new game"),
)


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
