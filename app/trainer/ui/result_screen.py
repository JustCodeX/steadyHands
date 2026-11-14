"""Training feedback after a round, as the patient's chart on a clipboard."""
from __future__ import annotations

import math

import pygame

from ..core.events import RoundResult
from . import theme
from .art.backdrop import Backdrop
from .art.glyphs import Glyphs
from .art.patient_art import PatientArt
from .fonts import Fonts

WON_INK = (30, 148, 92)
LOST_INK = (214, 58, 64)
STAR = (250, 190, 40)


class ResultScreen:
    W, H = 780, 400

    def __init__(self, size: tuple[int, int], fonts: Fonts, backdrop: Backdrop, patient: PatientArt, glyphs: Glyphs) -> None:
        self.width, self.height = size
        self.fonts = fonts
        self.backdrop = backdrop
        self.patient = patient
        self.glyphs = glyphs

    @staticmethod
    def stars(result: RoundResult) -> int:
        """One star for finishing, one for no wall contact, one for steady hands."""
        if not result.won:
            return 0
        return 1 + (result.contacts == 0) + (result.steadiness >= 70)

    def draw(self, surface: pygame.Surface, result: RoundResult) -> None:
        surface.blit(self.backdrop.room(), (0, 0))
        card = pygame.Rect((self.width - self.W) // 2, 112, self.W, self.H)
        pygame.draw.rect(surface, (10, 32, 38), card.move(0, 8), border_radius=26)
        pygame.draw.rect(surface, theme.PAPER, card, border_radius=26)
        pygame.draw.rect(surface, theme.PAPER_LINE, card, 3, border_radius=26)
        # the clip of the clipboard
        clip = pygame.Rect(0, 0, 190, 44)
        clip.center = (card.centerx, card.top)
        pygame.draw.rect(surface, theme.OUTLINE, clip.inflate(6, 6), border_radius=16)
        pygame.draw.rect(surface, theme.STEEL, clip, border_radius=14)
        pygame.draw.circle(surface, theme.OUTLINE, clip.center, 8)

        ink = WON_INK if result.won else LOST_INK
        title = "Patient stable" if result.won else "Patient woke up"
        self.fonts.draw(surface, "big", title, ink, (card.centerx, card.top + 30), anchor="midtop")

        # left: the patient
        face = self.patient.face("happy" if result.won else "awake", 176)
        surface.blit(face, (card.x + 40, card.y + 92))
        self.fonts.draw(surface, "head", result.level_name, theme.INK, (card.x + 128, card.y + 274), anchor="midtop")
        for i in range(3):
            self._star(surface, (card.x + 76 + i * 52, card.y + 342), 22, STAR if i < self.stars(result) else theme.PAPER_LINE)

        # right: the numbers
        rows = [
            ("Time", f"{result.time_s:.1f} s"),
            ("Wall contacts", str(result.contacts)),
            ("Wrong instrument", str(result.calls_wrong)),
            ("Steadiness", f"{result.steadiness:.0f} / 100"),
        ]
        if result.calls_correct:
            rows.insert(3, ("Instruments called by voice", str(result.calls_correct)))
        if result.steady_uses:
            rows.append(("Precision help (steady)", str(result.steady_uses)))
        given = result.treatments_correct + result.treatments_wrong
        if given or result.crises:
            rows.insert(2, ("Orders right", f"{result.treatments_correct} / {given}"))
            rows.insert(3, ("Overdoses · crises", f"{result.overdoses} · {result.crises}"))
        asked = result.questions_correct + result.questions_wrong
        if asked:
            rows.insert(2, ("Questions answered right", f"{result.questions_correct} / {asked}"))
        left, right, y = card.x + 268, card.right - 44, card.y + 112
        step = min(46, 252 // len(rows))  # more rows move closer together to stay on the card
        for label, value in rows:
            self.fonts.draw(surface, "body", label, theme.INK, (left, y))
            self.fonts.draw(surface, "head", value, theme.INK, (right, y - 4), anchor="topright")
            pygame.draw.line(surface, theme.PAPER_LINE, (left, y + step - 12), (right, y + step - 12), 2)
            y += step
        bar = pygame.Rect(left, y + 2, right - left, 18)
        pygame.draw.rect(surface, theme.PAPER_LINE, bar, border_radius=9)
        fill = int(bar.w * max(0.0, min(100.0, result.steadiness)) / 100.0)
        colour = theme.GOOD if result.steadiness >= 70 else theme.WARN if result.steadiness >= 40 else theme.BAD
        if fill > 0:
            pygame.draw.rect(surface, colour, (bar.x, bar.y, max(18, fill), bar.h), border_radius=9)

        hint = "Continue: the next level is selected" if result.won else "Continue: try this level again"
        a = self.glyphs.button("A", 34)
        text = self.fonts.text("body", hint, theme.TEXT)
        x = (self.width - a.get_width() - 10 - text.get_width()) // 2
        surface.blit(a, (x, self.height - 42))
        surface.blit(text, (x + a.get_width() + 10, self.height - 42 + 17 - text.get_height() // 2))

    @staticmethod
    def _star(surface: pygame.Surface, centre: tuple[int, int], radius: int, colour) -> None:
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            r = radius if i % 2 == 0 else radius * 0.46
            pts.append((centre[0] + r * math.cos(a), centre[1] + r * math.sin(a)))
        pygame.draw.polygon(surface, theme.OUTLINE, [(centre[0] + (x - centre[0]) * 1.2, centre[1] + (y - centre[1]) * 1.2) for x, y in pts])
        pygame.draw.polygon(surface, colour, pts)
