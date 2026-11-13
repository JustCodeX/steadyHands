"""Pictures of what the surgeon has to deal with: objects, blood, bleeding."""
from __future__ import annotations

import pygame

from .. import theme
from .canvas import Pen, render

BOX = 64.0


class TargetArt:
    """One picture per kind of target, chosen from the target's id and the instrument it needs."""

    SIZE = 60

    # Objects for the forceps, picked by a word in the target id.
    OBJECT_WORDS = (
        ("splinter", "splinter"),
        ("shard", "glass"),
        ("glass", "glass"),
        ("needle", "needle"),
        ("button", "button"),
    )

    def __init__(self) -> None:
        self._cache: dict[str, pygame.Surface] = {}
        self._painters = {
            "splinter": self._splinter,
            "glass": self._glass,
            "needle": self._needle,
            "button": self._button,
            "object": self._pebble,
            "blood": self._blood,
            "bleeding": self._bleeding,
            "sealed": self._sealed,
        }

    def kind(self, target_id: str, needs: str) -> str:
        if needs == "swab":
            return "blood"
        if needs == "clamp":
            return "bleeding"
        if needs == "scalpel":
            return "sealed"
        for word, kind in self.OBJECT_WORDS:
            if word in target_id.lower():
                return kind
        return "object"

    def sprite(self, target_id: str, needs: str) -> pygame.Surface:
        kind = self.kind(target_id, needs)
        if kind not in self._cache:
            self._cache[kind] = render((self.SIZE, self.SIZE), BOX, self._painters[kind])
        return self._cache[kind]

    # --- painters --------------------------------------------------------------

    @staticmethod
    def _splinter(pen: Pen) -> None:
        shape = [(8, 50), (24, 32), (50, 12), (56, 17), (36, 38), (15, 54)]
        pen.path((70, 42, 22), shape, 4, closed=True)
        pen.poly((176, 118, 62), shape)
        pen.line((214, 160, 100), (18, 46), (46, 20), 2)
        pen.line((120, 76, 38), (24, 46), (44, 28), 1.5)

    @staticmethod
    def _glass(pen: Pen) -> None:
        shape = [(20, 12), (47, 20), (54, 44), (30, 54), (11, 36)]
        pen.path((60, 112, 146), shape, 4, closed=True)
        pen.poly((176, 226, 244), shape)
        pen.poly((226, 246, 252), [(20, 12), (47, 20), (30, 30)])
        pen.line((255, 255, 255), (20, 34), (30, 46), 2)

    @staticmethod
    def _needle(pen: Pen) -> None:
        pen.outlined_path(theme.STEEL_LIGHT, theme.OUTLINE, [(12, 52), (46, 18)], 3.5, border=1.8)
        pen.circle(theme.OUTLINE, (49, 15), 7)
        pen.circle(theme.STEEL_LIGHT, (49, 15), 5)
        pen.circle(theme.OUTLINE, (49, 15), 2.2)

    @staticmethod
    def _button(pen: Pen) -> None:
        pen.circle((134, 88, 14), (32, 32), 19)
        pen.circle((252, 200, 70), (32, 32), 16.5)
        pen.circle((226, 166, 40), (32, 32), 11.5, 2)
        for dx, dy in ((-4, -4), (4, -4), (-4, 4), (4, 4)):
            pen.circle((134, 88, 14), (32 + dx, 32 + dy), 2.2)

    @staticmethod
    def _pebble(pen: Pen) -> None:
        shape = [(16, 26), (30, 14), (46, 20), (52, 36), (40, 50), (22, 46)]
        pen.path(theme.OUTLINE, shape, 4, closed=True)
        pen.poly((176, 184, 196), shape)
        pen.poly((214, 220, 230), [(30, 14), (46, 20), (36, 28), (22, 26)])

    @staticmethod
    def _blood(pen: Pen) -> None:
        blobs = [((30, 34), 15), ((43, 29), 10), ((38, 44), 10), ((20, 26), 7), ((50, 40), 5)]
        for centre, r in blobs:
            pen.circle((98, 6, 20), centre, r + 2.5)
        for centre, r in blobs:
            pen.circle((206, 28, 44), centre, r)
        pen.ellipse((248, 120, 128), (22, 24, 11, 6))
        pen.circle((248, 120, 128), (41, 25), 2)

    @staticmethod
    def _bleeding(pen: Pen) -> None:
        pen.circle((98, 6, 20), (32, 34), 16)
        pen.circle((226, 36, 48), (32, 34), 13)
        pen.circle((120, 8, 22), (32, 34), 6.5)
        # drops flying off
        for (x, y), r in (((12, 16), 4.5), ((32, 8), 5), ((52, 16), 4.5)):
            pen.circle((98, 6, 20), (x, y), r + 2)
            pen.circle((236, 48, 58), (x, y), r)
            pen.circle((255, 170, 170), (x - 1.2, y - 1.5), 1.4)

    @staticmethod
    def _sealed(pen: Pen) -> None:
        pen.ellipse(theme.SKIN_LINE, (6, 16, 52, 32))
        pen.ellipse(theme.SKIN, (8.5, 18.5, 47, 27))
        pen.line(theme.SKIN_LINE, (16, 32), (48, 32), 2.4)
        for x in (22, 29, 36, 43):
            pen.line(theme.OUTLINE, (x - 2, 27), (x + 2, 37), 1.8)
