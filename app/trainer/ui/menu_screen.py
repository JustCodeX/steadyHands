"""The menu: the patient on the table, one marker and one card per level."""
from __future__ import annotations

import math

import pygame

from ..core.events import GameSnapshot
from . import theme
from .art.backdrop import Backdrop
from .art.glyphs import Glyphs
from .art.patient_art import PatientArt
from .fonts import Fonts


class MenuScreen:
    BODY_W = 780
    BODY_Y = 124
    CARD_W, CARD_H, CARD_GAP = 214, 84, 16
    CARDS_Y = 392
    MAX_CARDS = 4

    def __init__(self, size: tuple[int, int], fonts: Fonts, backdrop: Backdrop, patient: PatientArt, glyphs: Glyphs) -> None:
        self.width, self.height = size
        self.fonts = fonts
        self.backdrop = backdrop
        self.patient = patient
        self.glyphs = glyphs
        self._static: pygame.Surface | None = None

    def draw(self, surface: pygame.Surface, snap: GameSnapshot, now: float) -> None:
        surface.blit(self._background(), (0, 0))
        names = snap.menu_levels
        if not names:
            self.fonts.draw(surface, "head", "No levels found in levels/", theme.BAD, (self.width // 2, self.CARDS_Y + 30), anchor="center")
        else:
            self._cards(surface, names, snap.menu_index)
            self._markers(surface, names, snap.menu_index, now)
        self._hints(surface, snap)
        if snap.message:
            self.fonts.draw(surface, "head", snap.message, theme.WARN, (self.width // 2, 108), anchor="center")

    # --- parts -----------------------------------------------------------------

    def _background(self) -> pygame.Surface:
        """Everything that never changes: room, title, patient."""
        if self._static is None:
            s = self.backdrop.room().copy()
            centre = self.width // 2
            self.fonts.draw(s, "title", "Steady Hands", theme.OUTLINE, (centre + 3, 14 + 4), anchor="midtop")
            self.fonts.draw(s, "title", "Steady Hands", theme.TEXT, (centre, 14), anchor="midtop")
            self.fonts.draw(s, "body", "Surgeon trainer: a steady hand and the right instrument", (176, 214, 216), (centre, 92), anchor="midtop")
            s.blit(self.patient.body(self.BODY_W), (self._body_x(), self.BODY_Y))
            self._static = s
        return self._static

    def _body_x(self) -> int:
        return (self.width - self.BODY_W) // 2

    def _cards(self, surface: pygame.Surface, names: list[str], selected: int) -> None:
        """Draw the level cards (a window around the selected one)."""
        count = min(len(names), self.MAX_CARDS)
        first = max(0, min(selected - count // 2, len(names) - count))
        total = count * self.CARD_W + (count - 1) * self.CARD_GAP
        x0 = (self.width - total) // 2
        for slot in range(count):
            index = first + slot
            is_sel = index == selected
            rect = pygame.Rect(x0 + slot * (self.CARD_W + self.CARD_GAP), self.CARDS_Y - (8 if is_sel else 0), self.CARD_W, self.CARD_H)
            pygame.draw.rect(surface, (10, 32, 38), rect.move(0, 6), border_radius=18)  # shadow
            pygame.draw.rect(surface, theme.PAPER if is_sel else theme.PANEL, rect, border_radius=18)
            pygame.draw.rect(surface, theme.ACCENT if is_sel else theme.PANEL_LINE, rect, 4 if is_sel else 2, border_radius=18)
            self._number(surface, (rect.x + 36, rect.centery), index + 1, is_sel, 20)
            self.fonts.draw(surface, "small", f"Level {index + 1}", theme.INK if is_sel else theme.MUTED, (rect.x + 66, rect.y + 16))
            self.fonts.draw(surface, "head", names[index], theme.INK if is_sel else theme.TEXT, (rect.x + 66, rect.y + 34))
        if first > 0:
            self.fonts.draw(surface, "head", "<", theme.MUTED, (x0 - 14, self.CARDS_Y + self.CARD_H // 2), anchor="midright")
        if first + count < len(names):
            self.fonts.draw(surface, "head", ">", theme.MUTED, (x0 + total + 14, self.CARDS_Y + self.CARD_H // 2), anchor="midleft")

    def _markers(self, surface: pygame.Surface, names: list[str], selected: int, now: float) -> None:
        """A numbered pin on the body for each level; the selected one pulses."""
        spots = {}
        for index in range(len(names)):
            bx, by = self.patient.body_spot(index, self.BODY_W)
            spots[index] = (self._body_x() + bx, self.BODY_Y + by)
        for index, spot in spots.items():
            if index != selected:
                self._number(surface, spot, index + 1, False, 15)
        if selected in spots:
            pulse = 0.5 + 0.5 * math.sin(now * 5)
            pygame.draw.circle(surface, theme.ACCENT, spots[selected], int(26 + 6 * pulse), 3)
            self._number(surface, spots[selected], selected + 1, True, 19)

    def _number(self, surface: pygame.Surface, centre: tuple[int, int], number: int, selected: bool, radius: int) -> None:
        pygame.draw.circle(surface, theme.OUTLINE, centre, radius + 3)
        pygame.draw.circle(surface, theme.ACCENT if selected else theme.PAPER, centre, radius)
        self.fonts.draw(surface, "label" if radius < 18 else "head", str(number), theme.INK, (centre[0], centre[1] - 1), anchor="center")

    def _hints(self, surface: pygame.Surface, snap: GameSnapshot) -> None:
        items = [
            (self.glyphs.knob(34), "Choose level"),
            (self.glyphs.button("A", 34), "Start"),
            (self.glyphs.button("C", 34), f"Mode: {snap.mode}"),
        ]
        widths = [glyph.get_width() + 10 + self.fonts.text("body", text, theme.TEXT).get_width() for glyph, text in items]
        gap = 44
        x = (self.width - sum(widths) - gap * (len(items) - 1)) // 2
        y = 524
        for (glyph, text), width in zip(items, widths):
            surface.blit(glyph, (x, y - glyph.get_height() // 2))
            self.fonts.draw(surface, "body", text, theme.TEXT, (x + glyph.get_width() + 10, y), anchor="midleft")
            x += width + gap
        if not snap.mcu_connected:
            keys = "No board connected. Keyboard: arrows move, Space = A, M = B, C = C, +/- = knob, Enter = knob press"
            self.fonts.draw(surface, "small", keys, theme.WARN, (self.width // 2, 568), anchor="center")
