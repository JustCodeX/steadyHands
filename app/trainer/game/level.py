"""A level: PNG mask plus level.json. See levels/README.md for the format."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .collision_map import CollisionMap


@dataclass
class Target:
    id: str
    x: int
    y: int
    needs: str  # instrument word: forceps, swab, clamp, scalpel
    timer_s: float | None = None  # bleeding: seconds until it gets worse
    done: bool = False
    timer_left: float | None = None

    def reset(self) -> None:
        self.done = False
        self.timer_left = self.timer_s


@dataclass
class Level:
    name: str
    directory: Path
    time_limit_s: float
    start: tuple[int, int]
    targets: list[Target]
    mask: CollisionMap
    dark_zones: list[tuple[int, int, int, int]] = field(default_factory=list)
    quiz_count: int | None = None  # questions asked in this level; None = the config's default
    quiz_topics: list[str] = field(default_factory=list)  # empty = any topic
    vitals_episodes: int = 0  # how many times a vital sign goes wrong in this level
    vitals_kinds: list[str] = field(default_factory=list)  # which ones ("spo2", "bis", "bp"); empty = any

    @classmethod
    def load(cls, directory: str | Path, mask: CollisionMap | None = None) -> "Level":
        directory = Path(directory)
        with open(directory / "level.json", encoding="utf-8") as f:
            data = json.load(f)
        targets = [
            Target(
                id=t["id"],
                x=int(t["position"][0]),
                y=int(t["position"][1]),
                needs=t["needs"],
                timer_s=float(t["timer_s"]) if t.get("timer_s") is not None else None,
            )
            for t in data["targets"]
        ]
        if mask is None:
            mask = CollisionMap.from_png(directory / "mask.png")
        quiz = data.get("quiz", {})
        vitals = data.get("vitals", {})
        level = cls(
            name=data.get("name", directory.name),
            directory=directory,
            time_limit_s=float(data.get("time_limit_s", 60)),
            start=(int(data["start"][0]), int(data["start"][1])),
            targets=targets,
            mask=mask,
            dark_zones=[tuple(int(v) for v in z) for z in data.get("dark", [])],
            quiz_count=int(quiz["count"]) if "count" in quiz else None,
            quiz_topics=list(quiz.get("topics", [])),
            vitals_episodes=int(vitals.get("episodes", 0)),
            vitals_kinds=list(vitals.get("kinds", [])),
        )
        level.reset()
        return level

    def reset(self) -> None:
        for t in self.targets:
            t.reset()

    def remaining(self) -> list[Target]:
        return [t for t in self.targets if not t.done]

    def complete(self) -> bool:
        return all(t.done for t in self.targets)


class LevelCatalog:
    """All level folders under levels/, sorted by name."""

    def __init__(self, levels_dir: str | Path) -> None:
        self.levels_dir = Path(levels_dir)

    def directories(self) -> list[Path]:
        if not self.levels_dir.is_dir():
            return []
        return sorted(p for p in self.levels_dir.iterdir() if (p / "level.json").is_file())

    def names(self) -> list[str]:
        out = []
        for d in self.directories():
            try:
                with open(d / "level.json", encoding="utf-8") as f:
                    out.append(json.load(f).get("name", d.name))
            except (OSError, json.JSONDecodeError):
                out.append(d.name)
        return out

    def load(self, index: int) -> Level:
        dirs = self.directories()
        if not dirs:
            raise FileNotFoundError(f"no levels in {self.levels_dir}")
        return Level.load(dirs[index % len(dirs)])
