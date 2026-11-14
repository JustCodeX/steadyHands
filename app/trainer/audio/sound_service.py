"""Plays the patient's lines and the spoken result; tells the voice service
when it is speaking so the game never hears itself."""
from __future__ import annotations

import array
import logging
import time
from collections import deque

from ..core.config import AudioConfig, TOOL_WORDS
from ..core.events import GameEvent, PlaybackFinished, PlaybackStarted, RoundResult, Subtitle
from ..core.service import Service
from ..voice.audio_input import read_sound_cards, usb_sound_card_present
from .clip_library import ClipLibrary
from .lines import line_text
from .phrase_builder import PhraseBuilder

log = logging.getLogger(__name__)

# Lines that interrupt whatever is playing.
URGENT = {"hit", "bleed_timeout", "win", "lose", "pardon", "vital_alarm", "vital_over", "vital_reminder", "vital_crisis"}
# Lines the result sentence makes redundant.
QUIET_KINDS = {"menu", "paused", "resumed", "round_started"}
# Game events that also get the buzz.
BUZZ_KINDS = {"hit"}
# Queue id of the generated buzz. Not a clip file: see make_buzz_bytes().
SFX_BUZZ = "sfx_buzz"
BUZZ_RATE = 22050


def make_buzz_bytes(rate: int = BUZZ_RATE, seconds: float = 0.35, freq: float = 415.0, level: float = 0.3) -> bytes:
    """A short square-wave buzz as signed 16-bit mono PCM, faded out at the end.

    Pure Python so it needs no clip file and no numpy; pygame plays it as a Sound."""
    n = int(rate * seconds)
    fade = max(1, int(rate * 0.04))
    period = rate / freq
    out = array.array("h")
    for i in range(n):
        v = level if (i % period) < period / 2 else -level
        out.append(int(v * min(1.0, (n - i) / fade) * 32767))
    return out.tobytes()


class SoundService(Service):
    name = "sound"

    def __init__(self, bus, cfg: AudioConfig, clips: ClipLibrary | None = None) -> None:
        super().__init__(bus)
        self.cfg = cfg
        self.clips = clips or ClipLibrary(cfg.clips_dir)
        self.phrases = PhraseBuilder()
        self._queue: deque[str] = deque()
        self._channel = None
        self._playing = False
        self._last_sequence: list[str] = []
        self._variant = 0
        self._ready = False
        self._buzz = None
        bus.subscribe(GameEvent, self._on_game_event)
        bus.subscribe(RoundResult, self._on_result)

    def start(self) -> None:
        import pygame

        try:
            if self.cfg.output_device:
                pygame.mixer.init(frequency=22050, channels=1, devicename=self.cfg.output_device)
            else:
                pygame.mixer.init(frequency=22050, channels=1)
            self._channel = pygame.mixer.Channel(0)
            self._channel.set_volume(self.cfg.volume)
            self._buzz = pygame.mixer.Sound(buffer=make_buzz_bytes())
            self._ready = True
            log.info("audio out ready; %d clips in %s", self.clips.count(), self.clips.clips_dir)
            if usb_sound_card_present(read_sound_cards()) is False:
                # The mixer opens fine on the built-in card, so say it out loud.
                log.warning(
                    "no USB headset on the bus; sound goes to the board's line-out "
                    "(see docs/board-cheatsheet.md, 'No sound in the headset')"
                )
        except pygame.error as exc:
            log.error("no audio output (%s); sound disabled", exc)

    def stop(self) -> None:
        if self._ready:
            import pygame

            pygame.mixer.quit()
            self._ready = False

    def tick(self, dt: float) -> None:
        if not self._ready:
            if self._playing:  # keep the state machine honest without audio
                self._finish()
            return
        if self._channel.get_busy():
            return
        if self._queue:
            self._play_next()
        elif self._playing:
            self._finish()

    # --- queueing ------------------------------------------------------------

    def speak(self, ids: list[str], interrupt: bool = False) -> None:
        ids = [i for i in ids if i]
        if not ids:
            return
        if interrupt:
            self._queue.clear()
            if self._ready and self._channel.get_busy():
                self._channel.stop()
        self._queue.extend(ids)
        self._last_sequence = list(ids)
        if not self._playing:
            self._playing = True
            self.bus.publish(PlaybackStarted())
        if not self._ready:
            # without audio the "speech" is instantaneous
            self._queue.clear()

    def _play_next(self) -> None:
        while self._queue:
            line_id = self._queue.popleft()
            if line_id == SFX_BUZZ:
                if self._buzz is not None:
                    self._channel.play(self._buzz)
                    return
                continue
            sound = self.clips.get(line_id)
            if sound is not None:
                self._channel.play(sound)
                return

    def _finish(self) -> None:
        self._playing = False
        self.bus.publish(PlaybackFinished())

    @property
    def speaking(self) -> bool:
        return self._playing

    # --- events --------------------------------------------------------------

    def _on_game_event(self, ev: GameEvent) -> None:
        if ev.kind == "repeat":
            if self._last_sequence:
                self.speak(list(self._last_sequence), interrupt=True)
            return
        if ev.kind == "hit":
            self._variant += 1
        nurse = self.phrases.nurse(ev.kind, ev.detail)
        if nurse:
            # headset audio reaches only the wearer (open point D4): the room reads along
            self.bus.publish(Subtitle(speaker="nurse", text=line_text(nurse)))
        ids = self.phrases.for_event(ev.kind, ev.detail, self._variant)
        if ev.kind in BUZZ_KINDS and ids:
            ids = [SFX_BUZZ] + ids
        if ev.kind == "tool_changed":
            # Turning the knob passes several tools quickly: only announce the last one.
            self._queue = deque(i for i in self._queue if i not in TOOL_WORDS)
        if ids:
            self.speak(ids, interrupt=ev.kind in URGENT)

    def _on_result(self, r: RoundResult) -> None:
        self.speak(self.phrases.result(r), interrupt=True)
