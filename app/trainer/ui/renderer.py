"""Draws the game on the display and turns pygame input into events.

The level map is rendered once per level into a surface; each frame only
redraws the moving parts over a copy, capped at `fps`.
"""
from __future__ import annotations

import logging
import math
import os
import time
from collections import deque
from pathlib import Path

import pygame

from ..core.config import DisplayConfig
from ..core.events import (
    AsrDebugEvent,
    GameSnapshot,
    GameState,
    IdleChanged,
    KeyEvent,
    QuitRequest,
    VoiceState,
    VoiceStateChanged,
)
from ..core.service import Service
from . import theme
from .hud import Hud
from .result_screen import ResultScreen

log = logging.getLogger(__name__)


class Renderer(Service):
    name = "renderer"

    def __init__(self, bus, cfg: DisplayConfig) -> None:
        super().__init__(bus)
        self.cfg = cfg
        self.screen: pygame.Surface | None = None
        self.snapshot: GameSnapshot | None = None
        self.voice = VoiceState.OFF
        self.idle = False
        self._map_cache: tuple[str, pygame.Surface] | None = None
        self._last_draw = 0.0
        self._frames = 0
        self.font = self.small = self.big = None
        self.hud: Hud | None = None
        self.result_screen: ResultScreen | None = None
        self.asr_partial = ""
        self.asr_log: deque[AsrDebugEvent] = deque(maxlen=8)
        self._asr_panel_on = False
        bus.subscribe(GameSnapshot, self._on_snapshot)
        bus.subscribe(VoiceStateChanged, self._on_voice)
        bus.subscribe(IdleChanged, self._on_idle)
        bus.subscribe(AsrDebugEvent, self._on_asr_debug)

    # --- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        if self.cfg.driver:
            os.environ["SDL_VIDEODRIVER"] = self.cfg.driver
        pygame.display.init()
        pygame.font.init()
        flags = pygame.FULLSCREEN if self.cfg.fullscreen else 0
        self.screen = pygame.display.set_mode((self.cfg.width, self.cfg.height), flags)
        pygame.display.set_caption("Steady Hands")
        pygame.mouse.set_visible(False)
        self.font = pygame.font.Font(theme.FONT, 30)
        self.small = pygame.font.Font(theme.FONT, 20)
        self.big = pygame.font.Font(theme.FONT, 54)
        self.hud = Hud(self.cfg.width, self.font, self.small)
        self.result_screen = ResultScreen(self.cfg.width, self.cfg.height, self.big, self.font, self.small)
        log.info("display %dx%d fullscreen=%s driver=%s", self.cfg.width, self.cfg.height, self.cfg.fullscreen, pygame.display.get_driver())

    def stop(self) -> None:
        pygame.display.quit()

    def tick(self, dt: float) -> None:
        self._pump_events()
        now = time.monotonic()
        if now - self._last_draw < 1.0 / self.cfg.fps:
            return
        self._last_draw = now
        self.draw(now)
        pygame.display.flip()
        self._frames += 1

    # --- events --------------------------------------------------------------

    def _pump_events(self) -> None:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.bus.publish(QuitRequest())
            elif ev.type in (pygame.KEYDOWN, pygame.KEYUP):
                name = pygame.key.name(ev.key)
                if ev.type == pygame.KEYDOWN and name in ("escape", "q") and (ev.mod & pygame.KMOD_CTRL or name == "escape"):
                    self.bus.publish(QuitRequest())
                    continue
                self.bus.publish(KeyEvent(key=name, down=ev.type == pygame.KEYDOWN))

    def _on_snapshot(self, snap: GameSnapshot) -> None:
        self.snapshot = snap

    def _on_voice(self, ev: VoiceStateChanged) -> None:
        self.voice = ev.state

    def _on_idle(self, ev: IdleChanged) -> None:
        self.idle = ev.idle

    def _on_asr_debug(self, ev: AsrDebugEvent) -> None:
        self._asr_panel_on = True
        if ev.outcome == "partial":
            self.asr_partial = ev.text
        else:
            self.asr_partial = ""
            self.asr_log.appendleft(ev)

    # --- drawing -------------------------------------------------------------

    def draw(self, now: float) -> None:
        assert self.screen is not None
        snap = self.snapshot
        if snap is None or snap.state is GameState.IDLE or self.idle:
            self.screen.fill(theme.DARK)
            return
        if snap.state is GameState.MENU:
            self._draw_menu(snap)
        elif snap.state is GameState.RESULT and snap.result is not None:
            self.result_screen.draw(self.screen, snap.result)
        else:
            self._draw_round(snap, now)
            if snap.state is GameState.PAUSED:
                self._overlay("Paused", 'Press B or say "continue"')
        if self._asr_panel_on:
            self._draw_asr_panel()

    def _draw_menu(self, snap: GameSnapshot) -> None:
        s = self.screen
        s.fill(theme.BG)
        title = self.big.render("Steady Hands", True, theme.TEXT)
        s.blit(title, ((self.cfg.width - title.get_width()) // 2, 70))
        sub = self.small.render("Surgeon trainer  -  tilt the instrument, call for tools by voice", True, theme.MUTED)
        s.blit(sub, ((self.cfg.width - sub.get_width()) // 2, 140))
        y = 220
        if not snap.menu_levels:
            s.blit(self.font.render("No levels found in levels/", True, theme.BAD), (200, y))
        for i, name in enumerate(snap.menu_levels):
            sel = i == snap.menu_index
            colour = theme.ACCENT if sel else theme.TEXT
            prefix = ">  " if sel else "    "
            s.blit(self.font.render(prefix + name, True, colour), (self.cfg.width // 2 - 200, y))
            y += 46
        mode = self.font.render(f"Mode: {snap.mode}   (press C to switch)", True, theme.MUTED)
        s.blit(mode, ((self.cfg.width - mode.get_width()) // 2, self.cfg.height - 130))
        hint = self.small.render('Turn the knob to pick a level.  Press A or say "new game" to start.', True, theme.MUTED)
        s.blit(hint, ((self.cfg.width - hint.get_width()) // 2, self.cfg.height - 80))
        if not snap.mcu_connected:
            warn = self.small.render("MCU not connected: keyboard only (arrows, space, 1-4)", True, theme.WARN)
            s.blit(warn, ((self.cfg.width - warn.get_width()) // 2, self.cfg.height - 45))
        self.hud.mic_icon(s, self.cfg.width - 40, 30, self.voice, time.monotonic())
        if snap.message:
            msg = self.font.render(snap.message, True, theme.WARN)
            s.blit(msg, ((self.cfg.width - msg.get_width()) // 2, 180))

    def _draw_round(self, snap: GameSnapshot, now: float) -> None:
        s = self.screen
        s.blit(self._map_surface(snap.level_dir), (0, 0))
        # targets
        for t in snap.targets:
            if t.done:
                continue
            colour = theme.TARGET_COLOURS.get(t.needs, theme.TEXT)
            r = 16 + (3 if int(now * 2) % 2 == 0 else 0)
            pygame.draw.circle(s, colour, (t.x, t.y), r)
            pygame.draw.circle(s, theme.BG, (t.x, t.y), r, 2)
            letter = self.small.render(theme.TOOL_LETTERS.get(t.needs, "?"), True, theme.BG)
            s.blit(letter, (t.x - letter.get_width() // 2, t.y - letter.get_height() // 2))
            if t.timer_left is not None:
                frac = max(0.0, min(1.0, t.timer_left / 15.0))
                pygame.draw.arc(s, theme.BAD, (t.x - 24, t.y - 24, 48, 48), 0, 2 * math.pi * frac, 4)
        # dark zones hide targets until "light" is called; the tool stays visible
        if snap.dark_zones and not snap.lit:
            for (x, y, w, h) in snap.dark_zones:
                pygame.draw.rect(s, theme.DARK, (x, y, w, h))
        # tool
        tool_colour = theme.TOOL_STEADY if snap.steady else theme.TOOL
        x, y = int(snap.x), int(snap.y)
        pygame.draw.circle(s, tool_colour, (x, y), 9)
        pygame.draw.circle(s, theme.TARGET_COLOURS.get(snap.tool, theme.TEXT), (x, y), 5)
        pygame.draw.line(s, tool_colour, (x, y - 14), (x, y - 40), 3)  # the handle
        self.hud.draw(s, snap, self.voice, now)
        if snap.message:
            msg = self.font.render(snap.message, True, theme.WARN)
            s.blit(msg, ((self.cfg.width - msg.get_width()) // 2, theme.HUD_HEIGHT + 10))

    # ASR debug side panel (voice.debug_asr): live transcripts on the left edge.

    ASR_PANEL_W = 300
    ASR_OUTCOME_COLOURS = {
        "command": theme.GOOD,
        "low_confidence": theme.WARN,
        "no_match": theme.MUTED,
        "empty": theme.MUTED,
    }

    def _draw_asr_panel(self) -> None:
        s = self.screen
        w = self.ASR_PANEL_W
        panel = pygame.Surface((w, self.cfg.height), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 175))
        s.blit(panel, (0, 0))
        pygame.draw.line(s, theme.MUTED, (w - 1, 0), (w - 1, self.cfg.height))
        x, y = 12, 10
        colour = theme.MIC_COLOURS.get(self.voice.name, theme.MUTED)
        s.blit(self.small.render(f"ASR debug  ·  {self.voice.name}", True, colour), (x, y))
        y += 32
        live = "> " + self.asr_partial if self.asr_partial else ("> ..." if self.voice is VoiceState.PROCESSING else ">")
        s.blit(self.small.render(self._fit(live, self.small, w - 2 * x), True, theme.WARN), (x, y))
        y += 34
        for e in self.asr_log:
            text = e.text if e.text else "(silence)"
            s.blit(self.small.render(self._fit(text, self.small, w - 2 * x), True, theme.TEXT), (x, y))
            y += 24
            tag = e.outcome + (f" -> {e.word}" if e.word else "") + (f"  {e.confidence:.2f}" if e.confidence else "")
            colour = self.ASR_OUTCOME_COLOURS.get(e.outcome, theme.MUTED)
            s.blit(self.small.render(self._fit(tag, self.small, w - 2 * x), True, colour), (x, y))
            y += 32
            if y > self.cfg.height - 56:
                break

    @staticmethod
    def _fit(text: str, font: pygame.font.Font, width: int) -> str:
        while text and font.size(text)[0] > width:
            text = text[:-1]
        return text

    def _overlay(self, title: str, hint: str) -> None:
        s = self.screen
        shade = pygame.Surface((self.cfg.width, self.cfg.height), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 160))
        s.blit(shade, (0, 0))
        t = self.big.render(title, True, theme.TEXT)
        s.blit(t, ((self.cfg.width - t.get_width()) // 2, self.cfg.height // 2 - 60))
        h = self.small.render(hint, True, theme.MUTED)
        s.blit(h, ((self.cfg.width - h.get_width()) // 2, self.cfg.height // 2 + 10))

    def _map_surface(self, level_dir: str) -> pygame.Surface:
        if self._map_cache and self._map_cache[0] == level_dir:
            return self._map_cache[1]
        surface = pygame.Surface((self.cfg.width, self.cfg.height))
        surface.fill(theme.WALL)
        mask_path = Path(level_dir) / "mask.png" if level_dir else None
        if mask_path and mask_path.is_file():
            mask = pygame.image.load(str(mask_path)).convert()
            # Recolour: dark = wall (tissue), light = corridor (skin).
            px = pygame.PixelArray(mask)
            wall = mask.map_rgb((0, 0, 0))
            corridor = mask.map_rgb((255, 255, 255))
            px.replace(wall, surface.map_rgb(theme.WALL), distance=0.4)
            px.replace(corridor, surface.map_rgb(theme.CORRIDOR), distance=0.4)
            del px
            surface.blit(mask, (0, 0))
        else:
            surface.fill(theme.CORRIDOR)
        self._map_cache = (level_dir, surface)
        return surface
