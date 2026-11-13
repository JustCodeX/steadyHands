"""The operating room behind the menu and the result: tiled floor under a lamp."""
from __future__ import annotations

import pygame

from .. import theme
from .canvas import soft_glow


class Backdrop:
    TILE = 64

    def __init__(self, size: tuple[int, int]) -> None:
        self.size = size
        self._room: pygame.Surface | None = None

    def room(self) -> pygame.Surface:
        if self._room is None:
            w, h = self.size
            room = pygame.Surface(self.size)
            room.fill(theme.ROOM)
            for x in range(0, w, self.TILE):
                pygame.draw.line(room, theme.ROOM_LINE, (x, 0), (x, h), 2)
            for y in range(0, h, self.TILE):
                pygame.draw.line(room, theme.ROOM_LINE, (0, y), (w, y), 2)
            room.blit(soft_glow((int(w * 1.15), int(h * 1.1)), theme.ROOM_LIGHT, 190), (-int(w * 0.075), -int(h * 0.12)))
            self._room = room.convert() if pygame.display.get_surface() else room
        return self._room
