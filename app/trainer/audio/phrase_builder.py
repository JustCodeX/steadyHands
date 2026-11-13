"""Puts spoken sentences together from clip ids."""
from __future__ import annotations

from ..core.events import RoundResult
from .lines import explain_id, number_id, question_id


class PhraseBuilder:
    @staticmethod
    def result(r: RoundResult) -> list[str]:
        ids = ["win" if r.won else "lose", number_id(r.time_s), "seconds"]
        if r.contacts == 0:
            ids.append("contact_0")
        elif r.contacts == 1:
            ids.append("contact_1")
        else:
            ids += [number_id(r.contacts), "contacts"]
        if r.steadiness >= 70:
            ids.append("steady_hands")
        elif r.steadiness >= 40:
            ids.append("fair_hands")
        else:
            ids.append("shaky_hands")
        if r.calls_correct + r.calls_wrong == 0:
            ids.append("calls_none")
        elif r.calls_wrong == 0:
            ids.append("calls_good")
        else:
            ids.append("calls_wrong")
        if r.questions_correct + r.questions_wrong > 0:
            if r.questions_wrong == 0:
                ids.append("quiz_all")
            elif r.questions_correct == 0:
                ids.append("quiz_none")
            else:
                ids.append("quiz_some")
        return ids

    @staticmethod
    def help(words: list[str]) -> list[str]:
        return ["you_can_say"] + [w for w in words if w]

    @staticmethod
    def for_event(kind: str, detail: str, variant: int) -> list[str]:
        if kind == "hit":
            return [f"ouch_{variant % 3 + 1}"]
        if kind == "tool_changed":
            return [detail] if detail else []
        if kind == "help":
            return PhraseBuilder.help(detail.split(",")) if detail else ["you_can_say", "help"]
        if kind == "question":
            return [question_id(detail)] if detail else []
        if kind == "quiz_correct":
            return [kind]
        if kind in ("quiz_wrong", "quiz_timeout"):
            return [kind, explain_id(detail)] if detail else [kind]
        if kind in ("round_started", "menu", "paused", "resumed", "awaiting_callback"):
            return [kind] if kind != "awaiting_callback" else []
        if kind in ("item_out", "swabbed", "clamped", "opened", "bleed_timeout", "wrong_tool", "pardon", "steady", "light", "win", "lose"):
            return [kind]
        return []
