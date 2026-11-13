"""Every spoken line, by id. Rendered to WAV once at setup by TtsRenderer.

No speech synthesis runs during play; the game only plays these files.
"""
from __future__ import annotations

PATIENT_LINES: dict[str, str] = {
    # reactions
    "ouch_1": "Ouch!",
    "ouch_2": "Hey, careful!",
    "ouch_3": "That hurts!",
    "item_out": "Got it. Thank you, doctor.",
    "swabbed": "Ah, I can see again.",
    "clamped": "The bleeding has stopped.",
    "opened": "Passage open.",
    "bleed_timeout": "Doctor, I am bleeding!",
    "wrong_tool": "That is the wrong instrument.",
    "win": "Operation complete. The patient is stable.",
    "lose": "The patient woke up. Round over.",
    "round_started": "Scalpel... no wait, forceps. Let us begin.",
    "paused": "Taking a break.",
    "resumed": "Continuing.",
    "menu": "Ready for the next patient.",
    "awaiting_callback": "Waiting for the call-back.",
    # voice interaction
    "pardon": "Pardon?",
    "you_can_say": "You can say",
    "steady": "Steady hands, doctor.",
    "light": "Light on.",
    # instruments handed over
    "forceps": "Forceps.",
    "swab": "Swab.",
    "clamp": "Clamp.",
    "scalpel": "Scalpel.",
    "cancel": "Cancelled.",
    "pause": "Pause.",
    "continue": "Continue.",
    "new game": "New game.",
    # result sentence parts
    "seconds": "seconds.",
    "contact_0": "No wall contacts.",
    "contact_1": "One wall contact.",
    "contacts": "wall contacts.",
    "steady_hands": "Steady hands.",
    "fair_hands": "Fairly steady.",
    "shaky_hands": "Shaky hands. Try the steady command.",
    "calls_none": "No instrument calls.",
    "calls_good": "All instrument calls were correct.",
    "calls_wrong": "Some calls were for the wrong instrument.",
}

MAX_NUMBER = 180


def number_id(n: int) -> str:
    n = max(0, min(MAX_NUMBER, int(round(n))))
    return f"n_{n}"


def all_lines() -> dict[str, str]:
    lines = dict(PATIENT_LINES)
    for n in range(MAX_NUMBER + 1):
        lines[number_id(n)] = str(n)
    return lines
