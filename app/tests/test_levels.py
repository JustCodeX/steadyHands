"""The levels that ship in levels/ must be playable."""
from collections import deque
from pathlib import Path

import pytest

from trainer.core.config import GameConfig, QuizConfig
from trainer.game.level import Level, LevelCatalog
from trainer.quiz import QuestionBank

LEVELS_DIR = Path(__file__).resolve().parents[2] / "levels"
DIRS = LevelCatalog(LEVELS_DIR).directories()
CFG = GameConfig()
QUESTION_BANNER_TOP = 540  # an open quiz question covers the screen below this line
STEP = 6


def reachable(level: Level) -> set[tuple[int, int]]:
    """Grid points the instrument can get to from the start without touching a wall."""
    start = (level.start[0] // STEP, level.start[1] // STEP)
    seen = {start}
    todo = deque([start])
    while todo:
        gx, gy = todo.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (gx + dx, gy + dy)
            if nxt in seen or level.mask.circle_hits_wall(nxt[0] * STEP, nxt[1] * STEP, CFG.tool_radius):
                continue
            seen.add(nxt)
            todo.append(nxt)
    return seen


def test_six_levels_ship():
    assert [d.name[:2] for d in DIRS] == ["01", "02", "03", "04", "05", "06"]


@pytest.mark.parametrize("directory", DIRS, ids=lambda d: d.name)
def test_level_is_playable(directory):
    level = Level.load(directory)
    assert (level.mask.width, level.mask.height) == (1024, 600)
    assert not level.mask.circle_hits_wall(*level.start, CFG.tool_radius)
    assert level.targets and len({t.id for t in level.targets}) == len(level.targets)
    free = reachable(level)
    for target in level.targets:
        assert target.needs in ("forceps", "swab", "clamp"), "scalpel targets are not built yet"
        near = [
            (gx, gy)
            for gx, gy in free
            if (gx * STEP - target.x) ** 2 + (gy * STEP - target.y) ** 2 <= (CFG.target_radius - STEP) ** 2
        ]
        assert near, f"{target.id} cannot be reached from the start"
        assert target.y < QUESTION_BANNER_TOP
    for x, y, w, h in level.dark_zones:
        assert 0 <= x and x + w <= 1024 and 56 <= y and y + h <= 600


def test_levels_get_harder_and_their_quiz_topics_exist():
    levels = [Level.load(d) for d in DIRS]
    bank = QuestionBank.load(QuizConfig().questions_file)
    assert levels[0].quiz_count == 0  # the first level teaches steering only
    counts = [lv.quiz_count for lv in levels]
    assert counts == sorted(counts)
    for lv in levels:
        if lv.quiz_count:
            assert len(bank.for_topics(lv.quiz_topics)) >= lv.quiz_count
    assert levels[-1].time_limit_s < levels[0].time_limit_s
