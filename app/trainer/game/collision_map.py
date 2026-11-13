"""Wall lookup in the level mask. Black is wall, white is corridor."""
from __future__ import annotations

import math
from pathlib import Path


class CollisionMap:
    def __init__(self, width: int, height: int, walls: bytearray | bytes) -> None:
        if len(walls) != width * height:
            raise ValueError("walls must have width*height entries")
        self.width = width
        self.height = height
        self._walls = bytes(walls)  # 1 = wall

    @classmethod
    def from_png(cls, path: str | Path) -> "CollisionMap":
        import pygame

        surface = pygame.image.load(str(path))
        w, h = surface.get_size()
        rgb = pygame.image.tobytes(surface, "RGB")
        walls = bytearray(w * h)
        for i in range(w * h):
            # dark pixel = wall; coloured markers count as corridor
            r, g, b = rgb[3 * i], rgb[3 * i + 1], rgb[3 * i + 2]
            if r < 100 and g < 100 and b < 100:
                walls[i] = 1
        return cls(w, h, walls)

    @classmethod
    def all_open(cls, width: int, height: int) -> "CollisionMap":
        return cls(width, height, bytearray(width * height))

    def is_wall(self, x: float, y: float) -> bool:
        xi, yi = int(x), int(y)
        if xi < 0 or yi < 0 or xi >= self.width or yi >= self.height:
            return True  # outside the map counts as wall
        return self._walls[yi * self.width + xi] == 1

    def circle_hits_wall(self, x: float, y: float, radius: float, samples: int = 12) -> bool:
        if self.is_wall(x, y):
            return True
        for k in range(samples):
            a = 2 * math.pi * k / samples
            if self.is_wall(x + radius * math.cos(a), y + radius * math.sin(a)):
                return True
        return False

    def wall_fraction(self) -> float:
        return sum(self._walls) / max(1, len(self._walls))
