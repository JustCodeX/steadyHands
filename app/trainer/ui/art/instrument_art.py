"""Pictures of the instruments: icons for the tray and the cursor in the wound."""
from __future__ import annotations

import pygame

from .. import theme
from .canvas import Pen, curve, render

# Every instrument is drawn in a 100 x 100 box with its tip at the lower left
# and its handle towards the upper right.
BOX = 100.0
TIP = (12.0, 88.0)
_U = (0.7071, -0.7071)  # along the instrument, away from the tip
_N = (0.7071, 0.7071)  # across the instrument


def _at(along: float, across: float = 0.0) -> tuple[float, float]:
    return (TIP[0] + along * _U[0] + across * _N[0], TIP[1] + along * _U[1] + across * _N[1])


class InstrumentArt:
    """Draws each instrument once per size and hands out the cached pictures."""

    CURSOR_SIZE = 92

    def __init__(self) -> None:
        self._cache: dict[tuple[str, int], pygame.Surface] = {}
        self._painters = {
            "forceps": self._forceps,
            "swab": self._swab,
            "clamp": self._clamp,
            "scalpel": self._scalpel,
        }

    def icon(self, word: str, size: int) -> pygame.Surface:
        key = (word, size)
        if key not in self._cache:
            painter = self._painters.get(word, self._unknown)
            self._cache[key] = render((size, size), BOX, lambda pen: painter(pen, theme.TARGET_COLOURS.get(word, theme.STEEL)))
        return self._cache[key]

    def cursor(self, word: str) -> tuple[pygame.Surface, tuple[int, int]]:
        """The picture and the pixel in it that sits on the instrument's position."""
        size = self.CURSOR_SIZE
        return self.icon(word, size), (round(TIP[0] / BOX * size), round(TIP[1] / BOX * size))

    # --- one painter per instrument --------------------------------------------

    @staticmethod
    def _forceps(pen: Pen, accent) -> None:
        arms = [curve(_at(102), _at(60, side * 15), _at(0, side * 3.5)) for side in (-1, 1)]
        for arm in arms:
            pen.path(theme.OUTLINE, arm, 10)
        for arm in arms:
            pen.path(theme.STEEL, arm, 6)
            pen.path(theme.STEEL_LIGHT, arm[4:-2], 1.6)
        pen.circle(theme.OUTLINE, _at(102), 8)
        pen.circle(accent, _at(102), 5.5)

    @staticmethod
    def _swab(pen: Pen, accent) -> None:
        pen.outlined_path((228, 198, 150), theme.OUTLINE, [_at(12), _at(106)], 6)
        pen.path(accent, [_at(92), _at(106)], 6)
        pen.circle(theme.OUTLINE, _at(6), 14)
        pen.circle((250, 250, 252), _at(6), 11.5)
        pen.circle((226, 232, 242), _at(3, 3), 6)
        pen.circle((255, 255, 255), _at(10, -3), 4)

    @staticmethod
    def _clamp(pen: Pen, accent) -> None:
        pivot = 44
        jaws = [[_at(pivot, side * 2.5), _at(1, side * 2.0)] for side in (-1, 1)]
        handles = [[_at(pivot, -side * 2.5), _at(84, side * 12)] for side in (-1, 1)]
        rings = [_at(95, side * 14.5) for side in (-1, 1)]
        for part in jaws + handles:
            pen.path(theme.OUTLINE, part, 9.5)
        for centre in rings:
            pen.circle(theme.OUTLINE, centre, 13.5, 9)
        for part in jaws + handles:
            pen.path(theme.STEEL, part, 5.5)
        for centre in rings:
            pen.circle(accent, centre, 11.5, 5)
        pen.circle(theme.OUTLINE, _at(pivot), 4.5)
        pen.circle(theme.STEEL_LIGHT, _at(pivot), 2.2)

    @staticmethod
    def _scalpel(pen: Pen, accent) -> None:
        pen.outlined_path(accent, theme.OUTLINE, [_at(48), _at(104)], 10)
        for along in (62, 70, 78):
            pen.line(theme.OUTLINE, _at(along, -3.5), _at(along, 3.5), 1.6)
        blade = [_at(48, -5.5), _at(48, 5.5), _at(16, 7.5), _at(0, 0), _at(18, -5)]
        pen.path(theme.OUTLINE, blade, 4.5, closed=True)
        pen.poly(theme.STEEL_LIGHT, blade)
        pen.line(theme.STEEL_DARK, _at(44, 2), _at(10, 3.5), 1.6)

    @staticmethod
    def _unknown(pen: Pen, accent) -> None:
        pen.outlined_path(theme.STEEL, theme.OUTLINE, [_at(4), _at(104)], 6)
