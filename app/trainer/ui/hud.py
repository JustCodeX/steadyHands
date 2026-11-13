"""Heads-up display drawn over the map while playing.

Left to right: the patient's face and lives, the clock, the instrument tray
(the knob picks from it), the list of things still to treat, and the mic.
Along the bottom edge: the vitals console (VitalsConsole) with the nurse's
subtitle, or, in a level without the monitor, an open quiz question.
"""
from __future__ import annotations

import math

import pygame

from ..core.events import GameSnapshot, VoiceState
from . import theme
from .art.glyphs import Glyphs
from .art.instrument_art import InstrumentArt
from .art.patient_art import PatientArt
from .art.target_art import TargetArt
from .fonts import Fonts
from .vitals_console import VitalsConsole

LIFE = (244, 92, 110)


class Hud:
    SLOT_W, SLOT_H, SLOT_GAP = 46, 44, 5
    TRAY_X = 300
    TASKS_X = 618
    MAX_TASKS = 7

    def __init__(self, width: int, fonts: Fonts, instruments: InstrumentArt, targets: TargetArt, patient: PatientArt, glyphs: Glyphs) -> None:
        self.width = width
        self.fonts = fonts
        self.instruments = instruments
        self.targets = targets
        self.patient = patient
        self.glyphs = glyphs
        self._dim: dict[str, pygame.Surface] = {}
        self._task_icons: dict[tuple[str, str], pygame.Surface] = {}
        self._panel = self._make_panel()
        self.console = VitalsConsole(width, fonts)

    def _make_panel(self) -> pygame.Surface:
        h = theme.HUD_HEIGHT
        panel = pygame.Surface((self.width, h))
        panel.fill(theme.PANEL)
        pygame.draw.rect(panel, theme.PANEL_LIGHT, (0, h - 3, self.width, 3))
        pygame.draw.rect(panel, theme.PANEL_LIGHT, (156, 8, 94, 40), border_radius=12)  # behind the clock
        return panel

    def draw(self, surface: pygame.Surface, snap: GameSnapshot, voice: VoiceState, t: float, shaken: bool = False) -> None:
        surface.blit(self._panel, (0, 0))
        self._patient(surface, snap, t, shaken)
        self._clock(surface, snap, t)
        self._tray(surface, snap, t)
        self._tasks(surface, snap)
        self._status(surface, snap, voice, t)
        if self.console.wanted(snap, t):
            self.console.draw(surface, snap, t, self._wrap)
        else:
            self._question(surface, snap)

    # --- parts -----------------------------------------------------------------

    def _patient(self, surface: pygame.Surface, snap: GameSnapshot, t: float, shaken: bool) -> None:
        lost = snap.contacts + snap.crises  # a crisis on the monitor costs a life like a wall contact
        mood = self.patient.mood_for(lost, snap.max_contacts)
        dx = int(3 * math.sin(t * 60)) if shaken else 0
        surface.blit(self.patient.face(mood, 50), (5 + dx, 3))
        for i in range(snap.max_contacts):
            alive = i >= lost
            self._heart(surface, 74 + i * 25, 18, 10, LIFE if alive else theme.PANEL_LINE)
        rate = snap.heart_rate
        colour = theme.GOOD if rate < 100 else theme.WARN if rate < 130 else theme.BAD
        bpm = self.fonts.draw(surface, "small", f"{rate} bpm", colour, (63, 31))
        for i in range(snap.stress):  # one arrow per stress level
            x = bpm.right + 5 + i * 9
            pygame.draw.polygon(surface, theme.BAD, [(x, 46), (x + 4, 36), (x + 8, 46)])

    def _clock(self, surface: pygame.Surface, snap: GameSnapshot, t: float) -> None:
        secs = int(math.ceil(snap.time_left))
        urgent = secs <= 10
        colour = theme.BAD if urgent and int(t * 3) % 2 == 0 else theme.WARN if urgent else theme.TEXT
        self.fonts.draw(surface, "head", f"{secs // 60}:{secs % 60:02d}", colour, (203, 28), anchor="center")

    def _tray(self, surface: pygame.Surface, snap: GameSnapshot, t: float) -> None:
        surface.blit(self.glyphs.knob(30), (262, 13))
        wanted = ""
        for target in snap.targets:
            if target.id == snap.hover_target and target.needs != snap.tool:
                wanted = target.needs
        for i, word in enumerate(snap.tools):
            rect = pygame.Rect(self.TRAY_X + i * (self.SLOT_W + self.SLOT_GAP), 6, self.SLOT_W, self.SLOT_H)
            active = word == snap.tool
            colour = theme.TARGET_COLOURS.get(word, theme.TEXT)
            if active:
                pygame.draw.rect(surface, theme.PAPER, rect, border_radius=10)
                pygame.draw.rect(surface, colour, rect, 3, border_radius=10)
                surface.blit(self.instruments.icon(word, 40), (rect.x + 3, rect.y + 2))
            else:
                pygame.draw.rect(surface, theme.PANEL_LIGHT, rect, border_radius=10)
                if word == wanted and int(t * 4) % 2 == 0:  # the tool the target under the instrument needs
                    pygame.draw.rect(surface, theme.WARN, rect, 3, border_radius=10)
                surface.blit(self._dimmed(word), (rect.x + 3, rect.y + 2))
            if word == snap.nurse_selection:  # co-op: what the assistant has ready to hand over
                called = word == snap.pending_call
                mark = theme.GOOD if called else theme.ACCENT
                pygame.draw.rect(surface, mark, rect.inflate(6, 6), 3, border_radius=12)
                pygame.draw.polygon(surface, mark, [(rect.centerx - 7, rect.bottom + 5), (rect.centerx + 7, rect.bottom + 5), (rect.centerx, rect.bottom - 2)])
            elif word == snap.pending_call and int(t * 4) % 2 == 0:  # co-op: the surgeon called this one
                pygame.draw.rect(surface, theme.WARN, rect, 3, border_radius=10)
        name_x = self.TRAY_X + len(snap.tools) * (self.SLOT_W + self.SLOT_GAP) + 4
        self.fonts.draw(surface, "label", snap.tool.capitalize(), theme.TARGET_COLOURS.get(snap.tool, theme.TEXT), (name_x, 28), anchor="midleft")

    def _question(self, surface: pygame.Surface, snap: GameSnapshot) -> None:
        """The open quiz question and the time left to answer it."""
        if not snap.question_text:
            return
        lines = self._wrap("body", snap.question_text, self.width - 130)
        texts = [self.fonts.text("body", line, theme.TEXT) for line in lines]
        box = pygame.Rect(0, 0, max(t.get_width() for t in texts) + 86, 26 * len(texts) + 26)
        box.midbottom = (self.width // 2, surface.get_height() - 6)
        pygame.draw.rect(surface, theme.PANEL, box, border_radius=16)
        pygame.draw.rect(surface, theme.ACCENT, box, 3, border_radius=16)
        pygame.draw.circle(surface, theme.ACCENT, (box.x + 30, box.centery - 3), 15)
        self.fonts.draw(surface, "head", "?", theme.PANEL, (box.x + 30, box.centery - 3), anchor="center")
        for i, text in enumerate(texts):
            surface.blit(text, (box.x + 58, box.y + 8 + 26 * i))
        left = max(0.0, min(1.0, snap.question_left))
        colour = theme.GOOD if left > 0.5 else theme.WARN if left > 0.25 else theme.BAD
        track = pygame.Rect(box.x + 58, box.bottom - 13, box.w - 76, 5)
        pygame.draw.rect(surface, theme.PANEL_LINE, track, border_radius=3)
        pygame.draw.rect(surface, colour, (track.x, track.y, int(track.w * left), track.h), border_radius=3)

    def _wrap(self, font: str, text: str, width: int) -> list[str]:
        lines, line = [], ""
        for word in text.split():
            longer = f"{line} {word}".strip()
            if line and self.fonts.width(font, longer) > width:
                lines.append(line)
                line = word
            else:
                line = longer
        return lines + [line]

    def _dimmed(self, word: str) -> pygame.Surface:
        if word not in self._dim:
            icon = self.instruments.icon(word, 40).copy()
            icon.set_alpha(150)
            self._dim[word] = icon
        return self._dim[word]

    def _tasks(self, surface: pygame.Surface, snap: GameSnapshot) -> None:
        """One chip per target: what it is, ticked off when treated."""
        shown = snap.targets[: self.MAX_TASKS]
        for i, target in enumerate(shown):
            rect = pygame.Rect(self.TASKS_X + i * 39, 10, 36, 36)
            pygame.draw.rect(surface, theme.PANEL_LIGHT, rect, border_radius=9)
            icon = self._task_icon(target.id, target.needs)
            if target.done:
                pygame.draw.rect(surface, theme.GOOD, rect, 2, border_radius=9)
                self._tick(surface, rect.center)
            else:
                surface.blit(icon, icon.get_rect(center=rect.center))
        if len(snap.targets) > len(shown):
            self.fonts.draw(surface, "small", f"+{len(snap.targets) - len(shown)}", theme.MUTED, (self.TASKS_X + len(shown) * 39, 28), anchor="midleft")

    def _task_icon(self, target_id: str, needs: str) -> pygame.Surface:
        key = (self.targets.kind(target_id, needs), needs)
        if key not in self._task_icons:
            self._task_icons[key] = pygame.transform.smoothscale(self.targets.sprite(target_id, needs), (30, 30))
        return self._task_icons[key]

    @staticmethod
    def _tick(surface: pygame.Surface, centre: tuple[int, int]) -> None:
        cx, cy = centre
        pygame.draw.lines(surface, theme.GOOD, False, [(cx - 9, cy), (cx - 3, cy + 7), (cx + 10, cy - 8)], 5)

    def _status(self, surface: pygame.Surface, snap: GameSnapshot, voice: VoiceState, t: float) -> None:
        """Right edge: microphone and what it heard, or the mode when the voice is off."""
        right = self.width - 12
        if voice is not VoiceState.OFF:
            self.mic_icon(surface, self.width - 28, 28, voice, t)
            right = self.width - 54
            heard = f"called: {snap.pending_call}" if snap.pending_call else snap.last_command
            if heard:
                self.fonts.draw(surface, "small", heard, theme.WARN if heard == "?" else theme.ACCENT, (right, 18), anchor="midright")
            notes = [snap.mode] if snap.mode != "solo" else []
            y = 38
        else:
            notes = [snap.mode]
            y = 20
        if not snap.mcu_connected:
            notes.append("keyboard")
        for note in notes:
            self.fonts.draw(surface, "small", note, theme.MUTED, (right, y), anchor="midright")
            y += 17

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
    def _heart(surface: pygame.Surface, cx: int, cy: int, r: int, colour) -> None:
        pygame.draw.circle(surface, colour, (cx - r // 2, cy - r // 3), r // 2 + 1)
        pygame.draw.circle(surface, colour, (cx + r // 2, cy - r // 3), r // 2 + 1)
        pygame.draw.polygon(surface, colour, [(cx - r, cy - r // 3 + 1), (cx + r, cy - r // 3 + 1), (cx, cy + r)])
