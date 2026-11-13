"""Small pictures of the controls, used in hints: buttons A/B/C and the knob."""
from __future__ import annotations

import pygame

from .. import theme
from ..fonts import Fonts
from .canvas import Pen, render


class Glyphs:
    def __init__(self, fonts: Fonts) -> None:
        self.fonts = fonts
        self._cache: dict[tuple, pygame.Surface] = {}

    def button(self, letter: str, size: int = 30) -> pygame.Surface:
        """A round button cap with its letter."""
        key = ("button", letter, size)
        if key not in self._cache:
            surface = render((size, size), 30, self._cap)
            text = self.fonts.text("label", letter, theme.INK)
            surface.blit(text, text.get_rect(center=(size // 2, size // 2 - 1)))
            self._cache[key] = surface
        return self._cache[key]

    def knob(self, size: int = 30, press: bool = False) -> pygame.Surface:
        """The knob: with arrows around it (turn) or with a dot in the middle (press)."""
        key = ("knob", press, size)
        if key not in self._cache:
            self._cache[key] = render((size, size), 30, self._knob_press if press else self._knob_turn)
        return self._cache[key]

    @staticmethod
    def _cap(pen: Pen) -> None:
        pen.circle(theme.OUTLINE, (15, 16), 13.5)
        pen.circle((176, 186, 200), (15, 16), 12)
        pen.circle((250, 250, 252), (15, 14.5), 12)

    @staticmethod
    def _knob_base(pen: Pen) -> None:
        pen.circle(theme.OUTLINE, (15, 15), 10.5)
        pen.circle((120, 134, 156), (15, 15), 9)
        pen.circle((176, 188, 206), (15, 14), 7)

    @classmethod
    def _knob_turn(cls, pen: Pen) -> None:
        cls._knob_base(pen)
        pen.line(theme.OUTLINE, (15, 14), (15, 8.5), 2.2)
        # an arrow on each side: turn it either way
        for x, sign in ((2.6, -1), (27.4, 1)):
            pen.line(theme.TEXT, (x, 11), (x, 19), 1.8)
            tip_y = 15 + sign * 6.5
            pen.poly(theme.TEXT, [(x - 3.2, tip_y - sign * 3.5), (x + 3.2, tip_y - sign * 3.5), (x, tip_y + sign * 1.5)])

    @classmethod
    def _knob_press(cls, pen: Pen) -> None:
        cls._knob_base(pen)
        pen.circle(theme.WARN, (15, 14), 3.6)
        pen.circle(theme.TEXT, (15, 15), 13.6, 1.6)
