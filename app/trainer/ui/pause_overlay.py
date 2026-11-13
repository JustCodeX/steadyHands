"""Shown over the round while paused: the controls and the steering speed."""
from __future__ import annotations

import pygame

from ..core.events import GameSnapshot
from . import theme
from .art.glyphs import Glyphs
from .fonts import Fonts


class PauseOverlay:
    W, H = 720, 432

    def __init__(self, size: tuple[int, int], fonts: Fonts, glyphs: Glyphs) -> None:
        self.size = size
        self.fonts = fonts
        self.glyphs = glyphs
        self._shade = pygame.Surface(size, pygame.SRCALPHA)
        self._shade.fill((6, 14, 20, 170))
        self._card: pygame.Surface | None = None

    def draw(self, surface: pygame.Surface, snap: GameSnapshot) -> None:
        surface.blit(self._shade, (0, 0))
        card = self._controls_card()
        x, y = (self.size[0] - self.W) // 2, (self.size[1] - self.H) // 2 + 16
        surface.blit(card, (x, y))
        self._speed(surface, snap, x + 40, y + 318)

    def _controls_card(self) -> pygame.Surface:
        if self._card is None:
            card = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            pygame.draw.rect(card, theme.PANEL, (0, 0, self.W, self.H), border_radius=26)
            pygame.draw.rect(card, theme.PANEL_LINE, (0, 0, self.W, self.H), 3, border_radius=26)
            self.fonts.draw(card, "big", "Paused", theme.TEXT, (self.W // 2, 14), anchor="midtop")
            rows = [
                (None, "Tilt the instrument", "move"),
                (self.glyphs.knob(34), "Turn the knob", "choose the instrument"),
                (self.glyphs.knob(34, press=True), "Press the knob", "light in dark areas"),
                (self.glyphs.button("A", 34), "Button A", "use it, or just hold still for 1 s"),
                (self.glyphs.button("C", 34), "Button C", "next instrument"),
            ]
            y = 84
            for glyph, what, effect in rows:
                if glyph is not None:
                    card.blit(glyph, (40, y))
                self.fonts.draw(card, "body", what, theme.TEXT, (88, y + 17), anchor="midleft")
                self.fonts.draw(card, "body", effect, theme.MUTED, (318, y + 17), anchor="midleft")
                y += 44
            pygame.draw.line(card, theme.PANEL_LINE, (40, 306), (self.W - 40, 306), 2)
            hint = self.fonts.text("body", "to continue", theme.TEXT)
            b = self.glyphs.button("B", 34)
            left = (self.W - b.get_width() - 10 - hint.get_width()) // 2
            card.blit(b, (left, self.H - 50))
            card.blit(hint, (left + b.get_width() + 10, self.H - 50 + 17 - hint.get_height() // 2))
            self._card = card
        return self._card

    def _speed(self, surface: pygame.Surface, snap: GameSnapshot, x: int, y: int) -> None:
        """The knob sets the steering speed while paused."""
        surface.blit(self.glyphs.knob(34), (x, y))
        self.fonts.draw(surface, "body", "Steering speed", theme.TEXT, (x + 48, y + 17), anchor="midleft")
        low, high = snap.sensitivity_range
        frac = (snap.sensitivity - low) / max(1e-6, high - low)
        bar = pygame.Rect(x + 278, y + 9, 270, 16)
        pygame.draw.rect(surface, theme.PANEL_LIGHT, bar, border_radius=8)
        pygame.draw.rect(surface, theme.ACCENT, (bar.x, bar.y, max(16, int(bar.w * frac)), bar.h), border_radius=8)
        pygame.draw.circle(surface, theme.TEXT, (bar.x + int(bar.w * frac), bar.centery), 12)
        self.fonts.draw(surface, "body", f"{snap.sensitivity * 100:.0f} %", theme.ACCENT, (bar.right + 22, y + 17), anchor="midleft")
