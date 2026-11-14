"""The console along the bottom edge: the vitals monitor on the left, the
nurse's last line as a subtitle on the right.

Each tile shows its value, the trend, and its dose card: what 10 units of
its drug do ("10 mg: −6"), the rule the player doses by. After the SpO2
tile a small tile shows the oxygen setting (FiO2).

The subtitle is there for the room as much as for the player: headset audio
reaches only the wearer (open point D4). An open quiz question uses the same
place on the right; the game never has both open at once.
"""
from __future__ import annotations

import pygame

from ..core.events import GameSnapshot, VitalView
from . import theme
from .fonts import Fonts

HEIGHT = 54
SUBTITLE_S = 7.0  # a line stays this long


class VitalsConsole:
    TILE_W, SETTING_W, TILE_H, GAP = 172, 84, 44, 8

    def __init__(self, width: int, fonts: Fonts) -> None:
        self.width = width
        self.fonts = fonts
        self._line = ""
        self._line_t = -1e9

    def show(self, text: str, now: float) -> None:
        self._line, self._line_t = text, now

    def subtitle(self, now: float) -> str:
        return self._line if now - self._line_t < SUBTITLE_S else ""

    def wanted(self, snap: GameSnapshot, now: float) -> bool:
        return bool(snap.vitals) or bool(self.subtitle(now))

    def draw(self, surface: pygame.Surface, snap: GameSnapshot, now: float, wrap) -> None:
        top = surface.get_height() - HEIGHT
        pygame.draw.rect(surface, theme.PANEL, (0, top, self.width, HEIGHT))
        pygame.draw.rect(surface, theme.PANEL_LIGHT, (0, top, self.width, 3))
        x = self.GAP
        for vital in snap.vitals:
            self._tile(surface, vital, pygame.Rect(x, top + 6, self.TILE_W, self.TILE_H), now)
            x += self.TILE_W + self.GAP
            if vital.setting:
                self._setting(surface, vital.setting, pygame.Rect(x, top + 6, self.SETTING_W, self.TILE_H))
                x += self.SETTING_W + self.GAP
        right = pygame.Rect(x + 4, top + 6, self.width - x - 4 - self.GAP, self.TILE_H)
        if snap.question_text:
            self._question(surface, snap, right, wrap)
        else:
            self._subtitle(surface, right, now, wrap)

    def _tile(self, surface: pygame.Surface, v: VitalView, rect: pygame.Rect, now: float) -> None:
        colour = {"normal": theme.GOOD, "alarm": theme.WARN, "critical": theme.BAD}.get(v.status, theme.TEXT)
        blink = v.status != "normal" and int(now * (4 if v.status == "critical" else 2)) % 2 == 0
        fill = colour if blink and v.status == "critical" else theme.PANEL_LIGHT
        pygame.draw.rect(surface, fill, rect, border_radius=9)
        pygame.draw.rect(surface, colour, rect, 3 if v.status != "normal" else 2, border_radius=9)
        text = theme.PANEL if fill is colour else colour
        plain = theme.TEXT if fill is not colour else theme.PANEL
        self.fonts.draw(surface, "small", f"{v.label} {v.unit}".strip(), plain, (rect.x + 9, rect.y + 3))
        if v.dose_card:
            self.fonts.draw(surface, "small", v.dose_card, theme.MUTED if fill is not colour else theme.PANEL, (rect.x + 9, rect.bottom - 21))
        self.fonts.draw(surface, "head", str(v.value), text, (rect.right - 30, rect.centery + 2), anchor="midright")
        self._arrow(surface, v.trend, (rect.right - 15, rect.centery + 2), text if v.trend else theme.MUTED)

    def _setting(self, surface: pygame.Surface, setting: str, rect: pygame.Rect) -> None:
        """The oxygen setting, like the display on an anaesthesia machine."""
        name, _, value = setting.partition(" ")
        pygame.draw.rect(surface, theme.PANEL_LIGHT, rect, border_radius=9)
        pygame.draw.rect(surface, theme.ACCENT, rect, 2, border_radius=9)
        self.fonts.draw(surface, "small", name, theme.TEXT, (rect.x + 9, rect.y + 3))
        self.fonts.draw(surface, "label", value, theme.ACCENT, (rect.right - 9, rect.bottom - 4), anchor="bottomright")

    @staticmethod
    def _arrow(surface: pygame.Surface, trend: int, centre: tuple[int, int], colour) -> None:
        cx, cy = centre
        if trend == 0:
            pygame.draw.line(surface, colour, (cx - 6, cy), (cx + 6, cy), 3)
        elif trend > 0:  # rising
            pygame.draw.polygon(surface, colour, [(cx - 7, cy + 4), (cx + 7, cy + 4), (cx, cy - 6)])
        else:
            pygame.draw.polygon(surface, colour, [(cx - 7, cy - 4), (cx + 7, cy - 4), (cx, cy + 6)])

    def _subtitle(self, surface: pygame.Surface, box: pygame.Rect, now: float, wrap) -> None:
        line = self.subtitle(now)
        if not line:
            return
        badge = self.fonts.draw(surface, "label", "Nurse", theme.ACCENT, (box.x, box.centery), anchor="midleft")
        font = "body" if len(wrap("body", line, box.right - badge.right - 14)) == 1 else "small"
        lines = wrap(font, line, box.right - badge.right - 14)[:2]
        step = 22 if font == "body" else 18
        y = box.centery - step * len(lines) // 2
        for i, text in enumerate(lines):
            self.fonts.draw(surface, font, text, theme.TEXT, (badge.right + 12, y + i * step))

    def _question(self, surface: pygame.Surface, snap: GameSnapshot, box: pygame.Rect, wrap) -> None:
        pygame.draw.circle(surface, theme.ACCENT, (box.x + 15, box.centery - 3), 14)
        self.fonts.draw(surface, "head", "?", theme.PANEL, (box.x + 15, box.centery - 3), anchor="center")
        lines = wrap("small", snap.question_text, box.w - 44)[:2]
        for i, text in enumerate(lines):
            self.fonts.draw(surface, "small", text, theme.TEXT, (box.x + 38, box.y + 2 + 18 * i))
        left = max(0.0, min(1.0, snap.question_left))
        colour = theme.GOOD if left > 0.5 else theme.WARN if left > 0.25 else theme.BAD
        track = pygame.Rect(box.x + 38, box.bottom - 6, box.w - 44, 5)
        pygame.draw.rect(surface, theme.PANEL_LINE, track, border_radius=3)
        pygame.draw.rect(surface, colour, (track.x, track.y, int(track.w * left), track.h), border_radius=3)
