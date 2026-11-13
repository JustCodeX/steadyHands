"""Draws the game on the display and turns pygame input into events.

The Renderer only decides which screen to show; each screen is its own class
(MenuScreen, RoundView + Hud, PauseOverlay, ResultScreen). Pictures are drawn
once and cached, so a frame is a handful of blits, capped at `fps`.
"""
from __future__ import annotations

import logging
import os
import time

import pygame

from ..core.config import DisplayConfig
from ..core.events import (
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
from .art.backdrop import Backdrop
from .art.glyphs import Glyphs
from .art.instrument_art import InstrumentArt
from .art.patient_art import PatientArt
from .art.target_art import TargetArt
from .fonts import Fonts
from .hud import Hud
from .map_painter import MapPainter
from .menu_screen import MenuScreen
from .pause_overlay import PauseOverlay
from .result_screen import ResultScreen
from .round_view import RoundView

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
        self._last_draw = 0.0
        self._frames = 0
        self.fonts: Fonts | None = None
        self.hud: Hud | None = None
        self.menu: MenuScreen | None = None
        self.round_view: RoundView | None = None
        self.pause_overlay: PauseOverlay | None = None
        self.result_screen: ResultScreen | None = None
        bus.subscribe(GameSnapshot, self._on_snapshot)
        bus.subscribe(VoiceStateChanged, self._on_voice)
        bus.subscribe(IdleChanged, self._on_idle)

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
        size = (self.cfg.width, self.cfg.height)
        self.fonts = Fonts()
        glyphs = Glyphs(self.fonts)
        instruments, targets, patient = InstrumentArt(), TargetArt(), PatientArt()
        backdrop = Backdrop(size)
        self.hud = Hud(self.cfg.width, self.fonts, instruments, targets, patient, glyphs)
        self.menu = MenuScreen(size, self.fonts, backdrop, patient, glyphs)
        self.round_view = RoundView(size, self.fonts, MapPainter(size), instruments, targets, glyphs)
        self.pause_overlay = PauseOverlay(size, self.fonts, glyphs)
        self.result_screen = ResultScreen(size, self.fonts, backdrop, patient, glyphs)
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

    # --- drawing -------------------------------------------------------------

    def draw(self, now: float) -> None:
        assert self.screen is not None
        snap = self.snapshot
        if snap is None or snap.state is GameState.IDLE or self.idle:
            self.screen.fill(theme.DARK)
            return
        if snap.state is GameState.MENU:
            self.menu.draw(self.screen, snap, now)
            if self.voice is not VoiceState.OFF:
                self.hud.mic_icon(self.screen, self.cfg.width - 40, 30, self.voice, now)
        elif snap.state is GameState.RESULT and snap.result is not None:
            self.result_screen.draw(self.screen, snap.result)
        else:
            self.round_view.draw(self.screen, snap, now)
            self.hud.draw(self.screen, snap, self.voice, now, shaken=self.round_view.hit_recently(now))
            if snap.message:
                self._toast(snap.message)
            if snap.state is GameState.PAUSED:
                self.pause_overlay.draw(self.screen, snap)

    def _toast(self, message: str) -> None:
        """A short message from the game, under the HUD."""
        text = self.fonts.text("head", message, theme.TEXT)
        box = text.get_rect().inflate(44, 18)
        box.midtop = (self.cfg.width // 2, theme.HUD_HEIGHT + 12)
        pygame.draw.rect(self.screen, theme.PANEL, box, border_radius=18)
        pygame.draw.rect(self.screen, theme.WARN, box, 3, border_radius=18)
        self.screen.blit(text, text.get_rect(center=box.center))
