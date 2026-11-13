"""Questions with a closed set of answer options. See assets/questions.json."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Question:
    id: str
    text: str  # spoken by the patient and shown on screen
    options: dict[str, tuple[str, ...]]  # option id -> phrases that mean it
    correct: str  # an option id
    explain: str = ""  # spoken after a wrong answer
    topic: str = ""

    def __post_init__(self) -> None:
        if self.correct not in self.options:
            raise ValueError(f"question {self.id}: correct option {self.correct!r} is not among the options")

    def keywords(self) -> list[str]:
        return [phrase for phrases in self.options.values() for phrase in phrases]


@dataclass
class QuestionBank:
    questions: list[Question] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "QuestionBank":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(
            [
                Question(
                    id=q["id"],
                    text=q["text"],
                    options={option: tuple(p.lower() for p in phrases) for option, phrases in q["options"].items()},
                    correct=q["correct"],
                    explain=q.get("explain", ""),
                    topic=q.get("topic", ""),
                )
                for q in data
            ]
        )

    def __len__(self) -> int:
        return len(self.questions)

    def get(self, question_id: str) -> Question | None:
        return next((q for q in self.questions if q.id == question_id), None)

    def for_topics(self, topics: list[str] | None = None) -> list[Question]:
        if not topics:
            return list(self.questions)
        return [q for q in self.questions if q.topic in topics]

    def keywords(self) -> list[str]:
        """Every answer phrase: the vocabulary of a restricted answer recogniser."""
        return sorted({k for q in self.questions for k in q.keywords()})
