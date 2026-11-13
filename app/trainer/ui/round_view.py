"""The playfield of a running round: wound, targets, dark zones, the instrument.

It also notices changes between two snapshots (a target treated, a wall
contact) and shows a short effect for them.
"""
from __future__ import annotations

import math

import pygame

from ..core.events import GameSnapshot, TargetView
from . import theme
from .art.canvas import radial, ring, soft_glow
from .art.glyphs import Glyphs
from .art.instrument_art import InstrumentArt
from .art.target_art import TargetArt
from .fonts import Fonts
from .map_painter import MapPainter

DONE_WORDS = {"forceps": "Out!", "swab": "Clean!", "clamp": "Clamped!", "scalpel": "Open!"}


class RoundView:
    FLASH_S = 0.45
    POP_S = 0.9

    def __init__(self, size: tuple[int, int], fonts: Fonts, painter: MapPainter, instruments: InstrumentArt, targets: TargetArt, glyphs: Glyphs) -> None:
        self.size = size
        self.fonts = fonts
        self.painter = painter
        self.instruments = instruments
        self.targets = targets
        self.glyphs = glyphs
        self._badges: dict[tuple[str, bool], pygame.Surface] = {}
        self._dark: dict[tuple[int, int], pygame.Surface] = {}
        self._flash = self._make_flash()
        self._shadow = soft_glow((46, 24), (20, 0, 10), 150)
        # what the last snapshot looked like, to spot changes
        self._level = ""
        self._done: set[str] = set()
        self._contacts = 0
        self._hit_t = -1e9
        self._pops: list[tuple[float, int, int, str]] = []  # start time, x, y, text

    def hit_recently(self, now: float) -> bool:
        return now - self._hit_t < self.FLASH_S

    def draw(self, surface: pygame.Surface, snap: GameSnapshot, now: float) -> None:
        self._track(snap, now)
        surface.blit(self.painter.background(snap.level_dir), (0, 0))
        for target in snap.targets:
            if not target.done:
                self._target(surface, target, snap, now)
        self._dark_zones(surface, snap)
        self._wrong_tool_hint(surface, snap)
        self._instrument(surface, snap)
        self._effects(surface, now)

    # --- changes between snapshots ---------------------------------------------

    def _track(self, snap: GameSnapshot, now: float) -> None:
        done = {t.id for t in snap.targets if t.done}
        if snap.level_dir != self._level or snap.contacts < self._contacts or not done >= self._done:
            # another level, or the round started again
            self._level, self._done, self._contacts = snap.level_dir, done, snap.contacts
            self._pops.clear()
            self._hit_t = -1e9
            return
        for target in snap.targets:
            if target.done and target.id not in self._done:
                self._pops.append((now, target.x, target.y, DONE_WORDS.get(target.needs, "Done!")))
        if snap.contacts > self._contacts:
            self._hit_t = now
        self._done, self._contacts = done, snap.contacts

    # --- targets ---------------------------------------------------------------

    def _target(self, surface: pygame.Surface, target: TargetView, snap: GameSnapshot, now: float) -> None:
        centre = (target.x, target.y)
        match = target.needs == snap.tool
        colour = theme.TARGET_COLOURS.get(target.needs, theme.TEXT)
        pulse = 2.0 * math.sin(now * 4.0)
        ring(surface, colour, centre, 33 + pulse, 3)
        if target.timer_left is not None and target.timer_s:
            # countdown until the bleeding costs the patient
            left = target.timer_left / target.timer_s
            urgent = target.timer_left < 5 and int(now * 4) % 2 == 0
            ring(surface, theme.CAVITY_DARK, centre, 43, 7)
            ring(surface, theme.WARN if urgent else theme.BAD, centre, 43, 7, left)
        sprite = self.targets.sprite(target.id, target.needs)
        surface.blit(sprite, sprite.get_rect(center=centre))
        if target.id == snap.hover_target and match and snap.dwell > 0:
            ring(surface, theme.GOOD, centre, 37, 7, snap.dwell)  # hold still: the grab fills up
        badge = self._badge(target.needs, match)
        surface.blit(badge, badge.get_rect(center=(target.x + 30, target.y - 30)))

    def _badge(self, needs: str, match: bool) -> pygame.Surface:
        """The instrument a target needs; green when it is the one in hand."""
        key = (needs, match)
        if key not in self._badges:
            badge = pygame.Surface((44, 44), pygame.SRCALPHA)
            pygame.draw.circle(badge, theme.OUTLINE, (22, 22), 22)
            pygame.draw.circle(badge, theme.GOOD if match else theme.TARGET_COLOURS.get(needs, theme.TEXT), (22, 22), 20)
            pygame.draw.circle(badge, theme.PAPER, (22, 22), 16)
            badge.blit(self.instruments.icon(needs, 30), (7, 7))
            self._badges[key] = badge
        return self._badges[key]

    def _wrong_tool_hint(self, surface: pygame.Surface, snap: GameSnapshot) -> None:
        target = next((t for t in snap.targets if t.id == snap.hover_target and not t.done), None)
        if target is None or target.needs == snap.tool:
            return
        text = self.fonts.text("body", f"Needs the {target.needs}", theme.TEXT)
        knob = self.glyphs.knob(30)
        w = text.get_width() + knob.get_width() + 34
        box = pygame.Rect(0, 0, w, 42)
        box.midbottom = (target.x, target.y - 52)
        box.clamp_ip(pygame.Rect(8, theme.HUD_HEIGHT + 8, self.size[0] - 16, self.size[1] - theme.HUD_HEIGHT - 16))
        pygame.draw.rect(surface, theme.PANEL, box, border_radius=14)
        pygame.draw.rect(surface, theme.WARN, box, 3, border_radius=14)
        surface.blit(knob, (box.x + 10, box.y + 6))
        surface.blit(text, (box.x + 18 + knob.get_width(), box.centery - text.get_height() // 2))

    # --- dark zones ------------------------------------------------------------

    def _dark_zones(self, surface: pygame.Surface, snap: GameSnapshot) -> None:
        """Dark zones hide the targets in them until the light is on. The instrument stays visible."""
        for (x, y, w, h) in snap.dark_zones:
            if snap.lit:
                pygame.draw.rect(surface, theme.WARN, (x, y, w, h), 3, border_radius=18)
                self.fonts.draw(surface, "small", f"light {math.ceil(snap.light_left)} s", theme.WARN, (x + 12, y + 8))
            else:
                surface.blit(self._dark_zone(w, h), (x, y))

    def _dark_zone(self, w: int, h: int) -> pygame.Surface:
        if (w, h) not in self._dark:
            zone = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.rect(zone, (*theme.DARK, 255), (0, 0, w, h), border_radius=18)
            pygame.draw.rect(zone, (*theme.PANEL_LINE, 255), (0, 0, w, h), 3, border_radius=18)
            knob = self.glyphs.knob(34, press=True)
            text = self.fonts.text("body", "Press the knob for light", theme.WARN)
            total = knob.get_width() + 10 + text.get_width()
            if total + 16 <= w and h >= 48:
                left = (w - total) // 2
                zone.blit(knob, (left, h // 2 - knob.get_height() // 2))
                zone.blit(text, (left + knob.get_width() + 10, h // 2 - text.get_height() // 2))
            self._dark[(w, h)] = zone
        return self._dark[(w, h)]

    # --- instrument and effects --------------------------------------------------

    def _instrument(self, surface: pygame.Surface, snap: GameSnapshot) -> None:
        x, y = int(snap.x), int(snap.y)
        surface.blit(self._shadow, (x - 12, y - 2))
        picture, (hx, hy) = self.instruments.cursor(snap.tool)
        surface.blit(picture, (x - hx, y - hy))
        # the part that must not touch the edge
        pygame.draw.circle(surface, theme.TOOL_STEADY if snap.steady else theme.TEXT, (x, y), snap.tool_radius, 2)
        if snap.steady:
            self.fonts.draw(surface, "small", "STEADY", theme.TOOL_STEADY, (x, y + snap.tool_radius + 4), anchor="midtop")

    def _effects(self, surface: pygame.Surface, now: float) -> None:
        self._pops = [p for p in self._pops if now - p[0] < self.POP_S]
        for start, x, y, text in self._pops:
            age = (now - start) / self.POP_S
            ring(surface, theme.GOOD, (x, y), 24 + 46 * age, max(1.0, 7 * (1 - age)))
            label = self.fonts.text("head", text, theme.TEXT)
            shade = self.fonts.text("head", text, theme.OUTLINE)
            pos = label.get_rect(center=(x, y - 30 - int(34 * age)))
            surface.blit(shade, pos.move(2, 2))
            surface.blit(label, pos)
        age = now - self._hit_t
        if age < self.FLASH_S:
            self._flash.set_alpha(int(255 * (1 - age / self.FLASH_S)))
            surface.blit(self._flash, (0, 0))

    def _make_flash(self) -> pygame.Surface:
        """A red frame around the screen, shown when the instrument touches the edge."""
        return radial(self.size, (240, 30, 40, 0), (240, 30, 40, 230), inner=0.8, outer=1.36)
