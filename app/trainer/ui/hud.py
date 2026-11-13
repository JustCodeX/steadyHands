"""Heads-up display drawn over the map while playing."""
from __future__ import annotations

import math

import pygame

from ..core.events import GameSnapshot, VoiceState
from . import theme


class Hud:
    def __init__(self, width: int, font: pygame.font.Font, small: pygame.font.Font) -> None:
        self.width = width
        self.font = font
        self.small = small

    def draw(self, surface: pygame.Surface, snap: GameSnapshot, voice: VoiceState, t: float) -> None:
        pygame.draw.rect(surface, theme.HUD_BG, (0, 0, self.width, theme.HUD_HEIGHT))
        x = 16
        # time
        secs = int(math.ceil(snap.time_left))
        colour = theme.TEXT if secs > 10 else theme.BAD
        surface.blit(self.font.render(f"{secs // 60}:{secs % 60:02d}", True, colour), (x, 10))
        x += 110
        # contacts as hearts
        for i in range(snap.max_contacts):
            filled = i >= snap.contacts
            self._heart(surface, x + i * 34, 28, 13, theme.GOOD if filled else theme.MUTED, filled)
        x += snap.max_contacts * 34 + 20
        # heart rate
        pulse = 1.0 + 0.08 * math.sin(t * snap.heart_rate / 60.0 * 2 * math.pi)
        hr_colour = theme.GOOD if snap.heart_rate < 100 else theme.WARN if snap.heart_rate < 130 else theme.BAD
        self._heart(surface, x, 28, int(11 * pulse), hr_colour, True)
        surface.blit(self.small.render(f"{snap.heart_rate} bpm", True, hr_colour), (x + 20, 18))
        x += 130
        # active tool
        tool_colour = theme.TARGET_COLOURS.get(snap.tool, theme.TEXT)
        pygame.draw.circle(surface, tool_colour, (x + 14, 28), 14)
        surface.blit(self.small.render(theme.TOOL_LETTERS.get(snap.tool, "?"), True, theme.HUD_BG), (x + 8, 18))
        surface.blit(self.font.render(snap.tool.capitalize(), True, theme.TEXT), (x + 36, 10))
        x += 190
        if snap.steady:
            surface.blit(self.small.render("STEADY", True, theme.TOOL_STEADY), (x, 20))
        x += 90
        # mode and mcu
        mode_text = snap.mode + ("" if snap.mcu_connected else "  (no MCU)")
        surface.blit(self.small.render(mode_text, True, theme.MUTED), (x, 20))
        # mic icon and last command, right side
        self.mic_icon(surface, self.width - 40, 28, voice, t)
        heard = snap.last_command or ""
        if snap.pending_call:
            heard = f"call-back: {snap.pending_call}?"
        label = self.small.render(heard, True, theme.WARN if heard == "?" else theme.ACCENT)
        surface.blit(label, (self.width - 60 - label.get_width(), 20))

    def mic_icon(self, surface: pygame.Surface, cx: int, cy: int, voice: VoiceState, t: float) -> None:
        colour = theme.MIC_COLOURS[voice.name]
        if voice is VoiceState.LISTENING:
            glow = 0.5 + 0.5 * math.sin(t * 4)
            pygame.draw.circle(surface, colour, (cx, cy), int(16 + 6 * glow), 2)
        pygame.draw.rect(surface, colour, (cx - 6, cy - 14, 12, 18), border_radius=6)
        pygame.draw.arc(surface, colour, (cx - 10, cy - 10, 20, 20), math.pi, 2 * math.pi, 2)
        pygame.draw.line(surface, colour, (cx, cy + 10), (cx, cy + 16), 2)
        if voice is VoiceState.OFF:
            pygame.draw.line(surface, theme.BAD, (cx - 12, cy - 14), (cx + 12, cy + 16), 3)

    @staticmethod
    def _heart(surface: pygame.Surface, cx: int, cy: int, r: int, colour, filled: bool) -> None:
        width = 0 if filled else 2
        pygame.draw.circle(surface, colour, (cx - r // 2, cy - r // 3), r // 2 + 1, width)
        pygame.draw.circle(surface, colour, (cx + r // 2, cy - r // 3), r // 2 + 1, width)
        pts = [(cx - r, cy - r // 3), (cx + r, cy - r // 3), (cx, cy + r)]
        pygame.draw.polygon(surface, colour, pts, width)
