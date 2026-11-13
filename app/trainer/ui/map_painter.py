"""Paints a level's background from its mask: skin, with the corridor as an open wound.

The mask only says wall or corridor (see levels/README.md). This class turns
it into a picture once per level; the renderer then reuses that picture every
frame. Everything is done with pygame surfaces, so it needs no extra library.
"""
from __future__ import annotations

import logging
import random
import zlib
from pathlib import Path

import pygame

from . import theme
from .art.canvas import Pen, blur, curve, radial, render

log = logging.getLogger(__name__)

_MULT = pygame.BLEND_RGBA_MULT
_CLEAR = (0, 0, 0, 0)


class MapPainter:
    def __init__(self, size: tuple[int, int]) -> None:
        self.size = size
        self._cache: tuple[str, pygame.Surface] | None = None

    def background(self, level_dir: str) -> pygame.Surface:
        """The finished background for the level in `level_dir` (cached)."""
        if self._cache and self._cache[0] == level_dir:
            return self._cache[1]
        mask_path = Path(level_dir) / "mask.png" if level_dir else None
        if mask_path and mask_path.is_file():
            surface = self._paint(mask_path)
        else:
            log.warning("no mask.png in %r: drawing an open map", level_dir)
            surface = self._skin()
        self._cache = (level_dir, surface)
        return surface

    # --- painting --------------------------------------------------------------

    def _paint(self, mask_path: Path) -> pygame.Surface:
        raw = pygame.image.load(str(mask_path)).convert()
        if raw.get_size() != self.size:
            raw = pygame.transform.scale(raw, self.size)
        # Same rule as CollisionMap: a dark pixel is wall.
        wall = pygame.mask.from_threshold(raw, (0, 0, 0, 255), (100, 100, 100, 255))
        wound = wall.copy()
        wound.invert()
        white = (255, 255, 255)
        wound_alpha = wound.to_surface(setcolor=(*white, 255), unsetcolor=(*white, 0))
        wall_alpha = wall.to_surface(setcolor=(*white, 255), unsetcolor=(*white, 0))

        surface = self._skin()
        self._decorate(surface, wound, mask_path.parent.name)

        # Reddened skin around the wound.
        halo = blur(wound_alpha, 8)
        halo.fill((*theme.WOUND_HALO, 190), special_flags=_MULT)
        surface.blit(halo, (0, 0))
        # The far rim catches the light; then a dark line all around the wound.
        surface.blit(wound.to_surface(setcolor=(*theme.SKIN_LIGHT, 255), unsetcolor=_CLEAR), (4, 4))
        edge = wound.to_surface(setcolor=(*theme.WOUND_EDGE, 255), unsetcolor=_CLEAR)
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, -2), (-2, 2), (2, 2)):
            surface.blit(edge, (dx, dy))

        # Inside: lighter along the middle, and the near rim casts a shadow.
        inside = pygame.Surface(self.size, pygame.SRCALPHA)
        inside.fill((*theme.CAVITY, 255))
        middle = blur(wound_alpha, 14)
        middle.fill((*theme.CAVITY_LIGHT, 150), special_flags=_MULT)
        inside.blit(middle, (0, 0))
        self._fibres(inside, mask_path.parent.name)
        shadow = blur(wall_alpha, 5)
        shadow.fill((*theme.CAVITY_DARK, 215), special_flags=_MULT)
        inside.blit(shadow, (7, 9))
        rim = blur(wall_alpha, 3)
        rim.fill((*theme.CAVITY_DARK, 120), special_flags=_MULT)
        inside.blit(rim, (0, 0))
        inside.blit(wound_alpha, (0, 0), special_flags=_MULT)  # keep only the wound
        surface.blit(inside, (0, 0))

        surface.blit(self._vignette(), (0, 0))
        return surface

    def _skin(self) -> pygame.Surface:
        """Skin with soft lighting: brighter in the middle."""
        return radial(self.size, (*theme.SKIN_LIGHT, 255), (*theme.SKIN_SHADE, 255), inner=0.15, outer=1.3).convert()

    def _vignette(self) -> pygame.Surface:
        return radial(self.size, (70, 20, 30, 0), (70, 20, 30, 80), inner=0.8)

    def _fibres(self, inside: pygame.Surface, seed: str) -> None:
        """Faint streaks, so the tissue is not a flat colour."""
        rng = random.Random(zlib.crc32(seed.encode()))
        w, h = self.size
        streaks = pygame.Surface(self.size, pygame.SRCALPHA)
        for _ in range(260):
            x, y = rng.randrange(w), rng.randrange(theme.HUD_HEIGHT, h)
            length, bend = rng.randrange(14, 40), rng.randrange(-8, 9)
            colour = (*theme.CAVITY_LIGHT, 46) if rng.random() < 0.5 else (*theme.CAVITY_DARK, 50)
            pts = curve((x, y), (x + length / 2, y + bend), (x + length, y + rng.randrange(-5, 6)), 6)
            pygame.draw.lines(streaks, colour, False, pts, 2)
        inside.blit(streaks, (0, 0))

    # --- decoration on the skin ------------------------------------------------

    def _decorate(self, surface: pygame.Surface, wound: pygame.mask.Mask, seed: str) -> None:
        """A plaster, a belly button and a few moles, placed where the wound is not."""
        rng = random.Random(zlib.crc32(seed.encode()) + 7)
        w, h = self.size
        taken: list[pygame.Rect] = []
        pieces = [
            pygame.transform.rotozoom(render((92, 40), 92, self._plaster), rng.choice((-28, -14, 12, 24)), 1.0),
            render((40, 40), 40, self._belly_button),
        ] + [render((16, 16), 16, self._mole) for _ in range(4)]
        for piece in pieces:
            pw, ph = piece.get_size()
            for _ in range(60):
                rect = pygame.Rect(rng.randrange(16, w - pw - 16), rng.randrange(theme.HUD_HEIGHT + 12, h - ph - 12), pw, ph)
                space = rect.inflate(44, 44).clip(pygame.Rect(0, 0, w, h))
                if wound.overlap(pygame.mask.Mask(space.size, fill=True), space.topleft) is None and space.collidelist(taken) < 0:
                    surface.blit(piece, rect)
                    taken.append(space)
                    break

    @staticmethod
    def _plaster(pen: Pen) -> None:
        pen.rect(theme.SKIN_LINE, (2, 8, 88, 24), radius=12)
        pen.rect((240, 196, 150), (4, 10, 84, 20), radius=10)
        pen.rect((252, 228, 196), (32, 10, 28, 20))
        for x in (12, 20, 72, 80):
            for y in (16, 24):
                pen.circle((206, 160, 116), (x, y), 1.3)

    @staticmethod
    def _belly_button(pen: Pen) -> None:
        pen.ellipse(theme.SKIN_SHADE, (10, 8, 20, 24))
        pen.path(theme.SKIN_LINE, curve((15, 13), (27, 20), (15, 28), 8), 2.6)

    @staticmethod
    def _mole(pen: Pen) -> None:
        pen.circle(theme.SKIN_LINE, (8, 8), 3.4)
        pen.circle((176, 118, 96), (7.2, 7.2), 1.6)
