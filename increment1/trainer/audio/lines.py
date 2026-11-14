"""The patient's lines.

Scripted on purpose: no LLM runs at play time (PLAN.md, T3). That keeps the
response immediate, costs no energy, and makes the trainer predictable.
"""

LINES = {
    # Reactions to a wall contact
    "hit_1": "Ouch! Careful, please.",
    "hit_2": "That hurt. Watch the edge.",
    "hit_3": "I can feel that. Steady now.",
    # Instruments
    "took_forceps": "Forceps.",
    "took_swab": "Swab.",
    "took_clamp": "Clamp.",
    "took_scalpel": "Scalpel.",
    # Flow
    "round_start": "I am ready. Let us begin.",
    "item_out": "Got it. One down.",
    "win": "All done. Thank you, doctor.",
    "lose": "I am waking up. We have to stop.",
    # Misheard speech
    "pardon": "Pardon?",
    "help": "You can ask for forceps, swab, clamp or scalpel.",
}
