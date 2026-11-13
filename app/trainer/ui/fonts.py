"""The fonts of the UI and a cache of rendered text."""
from __future__ import annotations

from pathlib import Path

import pygame

from . import theme


class Fonts:
    """Named font sizes. `text()` renders once and reuses the surface."""

    SIZES = {
        # name: (font file, size)
        "title": (theme.FONT_DISPLAY, 68),
        "big": (theme.FONT_DISPLAY, 46),
        "head": (theme.FONT_DISPLAY, 28),
        "label": (theme.FONT_DISPLAY, 21),
        "body": (theme.FONT_BODY, 21),
        "small": (theme.FONT_BODY, 16),
    }
    MAX_CACHED = 300

    def __init__(self) -> None:
        self._fonts = {name: self._load(path, size) for name, (path, size) in self.SIZES.items()}
        self._cache: dict[tuple, pygame.Surface] = {}

    @staticmethod
    def _load(path: Path, size: int) -> pygame.font.Font:
        if path.is_file():
            return pygame.font.Font(str(path), size)
        return pygame.font.Font(None, int(size * 1.25))  # the default font runs small

    def text(self, name: str, text: str, colour) -> pygame.Surface:
        key = (name, text, tuple(colour))
        surface = self._cache.get(key)
        if surface is None:
            if len(self._cache) >= self.MAX_CACHED:
                self._cache.clear()
            surface = self._fonts[name].render(text, True, colour)
            self._cache[key] = surface
        return surface

    def draw(self, target: pygame.Surface, name: str, text: str, colour, pos, anchor: str = "topleft") -> pygame.Rect:
        """Blit text with `anchor` (a pygame.Rect attribute name) at `pos`."""
        surface = self.text(name, text, colour)
        rect = surface.get_rect(**{anchor: pos})
        target.blit(surface, rect)
        return rect
