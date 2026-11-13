"""Training feedback after a round."""
from __future__ import annotations

import pygame

from ..core.events import RoundResult
from . import theme


class ResultScreen:
    def __init__(self, width: int, height: int, big: pygame.font.Font, font: pygame.font.Font, small: pygame.font.Font) -> None:
        self.width = width
        self.height = height
        self.big = big
        self.font = font
        self.small = small

    def draw(self, surface: pygame.Surface, result: RoundResult) -> None:
        surface.fill(theme.BG)
        title = "Patient stable" if result.won else "Patient woke up"
        colour = theme.GOOD if result.won else theme.BAD
        t = self.big.render(title, True, colour)
        surface.blit(t, ((self.width - t.get_width()) // 2, 60))
        sub = self.small.render(f"Level: {result.level_name}", True, theme.MUTED)
        surface.blit(sub, ((self.width - sub.get_width()) // 2, 130))

        rows = [
            ("Time", f"{result.time_s:.1f} s"),
            ("Wall contacts", str(result.contacts)),
            ("Steadiness", f"{result.steadiness:.0f} / 100"),
            ("Instrument calls", f"{result.calls_correct} correct, {result.calls_wrong} wrong"),
            ("Precision help (steady)", str(result.steady_uses)),
        ]
        y = 190
        for label, value in rows:
            surface.blit(self.font.render(label, True, theme.MUTED), (self.width // 2 - 300, y))
            v = self.font.render(value, True, theme.TEXT)
            surface.blit(v, (self.width // 2 + 300 - v.get_width(), y))
            y += 52
        # steadiness bar
        bar_w = 600
        pygame.draw.rect(surface, theme.HUD_BG, (self.width // 2 - 300, y + 10, bar_w, 18), border_radius=9)
        fill = int(bar_w * result.steadiness / 100.0)
        bar_colour = theme.GOOD if result.steadiness >= 70 else theme.WARN if result.steadiness >= 40 else theme.BAD
        if fill > 0:
            pygame.draw.rect(surface, bar_colour, (self.width // 2 - 300, y + 10, fill, 18), border_radius=9)
        hint = self.small.render('Say "new game" or press A to play again', True, theme.MUTED)
        surface.blit(hint, ((self.width - hint.get_width()) // 2, self.height - 60))
