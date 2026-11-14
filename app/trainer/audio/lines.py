"""Every spoken line, by id. Rendered to WAV once at setup by TtsRenderer.

No speech synthesis runs during play; the game only plays these files.
"""
from __future__ import annotations

from ..quiz.question import QuestionBank

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
    "oxygen": "Oxygen.",  # for "you can say ..."
    "anaesthesia": "Anaesthesia.",
    "adrenaline": "Adrenaline.",
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
    # quiz
    "quiz_correct": "Correct.",
    "quiz_wrong": "Wrong.",
    "quiz_timeout": "Too slow.",
    "quiz_all": "Every question answered correctly.",
    "quiz_some": "Some answers were wrong.",
    "quiz_none": "No question answered correctly.",
}

# The nurse at the vitals monitor. Alarm lines stay under 2 s: they interrupt.
NURSE_LINES: dict[str, str] = {
    "alarm_spo2": "Doctor, sats are dropping.",
    "alarm_bis": "Doctor, he is waking up.",
    "alarm_bp": "Doctor, pressure is falling.",
    "remind_spo2": "Saturation is at",
    "remind_bis": "BIS is at",
    "remind_bp": "Pressure is at",
    "unit_spo2": "percent.",
    "unit_bis": "and rising.",
    "unit_bp": "systolic.",
    # read-back of an instruction, as in the operating room
    "give_oxygen": "More oxygen.",
    "give_anaesthesia": "Deepening the anaesthesia.",
    "give_adrenaline": "Adrenaline is in.",
    "not_helped": "That did not help, doctor.",
    "unneeded": "That was not needed, doctor.",
    "already": "Already on it.",
    "stable": "He is stable again.",
    "crisis": "He is critical! The team steps in.",
    "pardon_doctor": "Pardon, doctor?",
    "you_can_order": "You can say oxygen, anaesthesia or adrenaline.",
    # result sentence parts
    "treat_good": "Every instruction to the nurse was right.",
    "treat_wrong": "Some instructions to the nurse were wrong.",
    "crises_one": "One crisis.",
    "crises": "crises.",
}

MAX_NUMBER = 180


def number_id(n: int) -> str:
    n = max(0, min(MAX_NUMBER, int(round(n))))
    return f"n_{n}"


def nurse_number_id(n: int) -> str:
    """A number in the nurse's voice (the patient's are number_id)."""
    n = max(0, min(MAX_NUMBER, int(round(n))))
    return f"nn_{n}"


def nurse_ids() -> set[str]:
    """Every clip the nurse speaks: rendered with audio.nurse_voice."""
    return set(NURSE_LINES) | {nurse_number_id(n) for n in range(MAX_NUMBER + 1)}


def line_text(ids: list[str]) -> str:
    """What a sequence of nurse clips says, for the subtitle."""
    out = []
    for i in ids:
        if i in NURSE_LINES:
            out.append(NURSE_LINES[i])
        elif i.startswith(("n_", "nn_")):
            out.append(i.split("_", 1)[1])
    return " ".join(out)


def question_id(question: str) -> str:
    """Clip id of a quiz question, from the question's id."""
    return f"q_{question}"


def explain_id(question: str) -> str:
    """Clip id of the sentence that gives a question's right answer."""
    return f"qa_{question}"


def all_lines(questions: QuestionBank | None = None) -> dict[str, str]:
    lines = dict(PATIENT_LINES)
    lines.update(NURSE_LINES)
    for n in range(MAX_NUMBER + 1):
        lines[number_id(n)] = str(n)
        lines[nurse_number_id(n)] = str(n)
    for q in questions.questions if questions else []:
        lines[question_id(q.id)] = q.text
        if q.explain:
            lines[explain_id(q.id)] = q.explain
    return lines
