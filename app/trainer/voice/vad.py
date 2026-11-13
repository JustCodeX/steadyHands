"""Voice activity detection: an energy gate with an adaptive noise floor,
plus a segmenter that turns block decisions into speech segments."""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class VoiceActivityDetector(ABC):
    @abstractmethod
    def is_speech(self, block: np.ndarray) -> bool:
        """block: float32 samples in -1..1."""

    def reset(self) -> None:  # noqa: B027
        pass


class EnergyVad(VoiceActivityDetector):
    def __init__(self, ratio: float = 3.0, min_rms: float = 0.01, floor_rate: float = 0.05) -> None:
        self.ratio = ratio
        self.min_rms = min_rms
        self.floor_rate = floor_rate
        self.noise_floor = 0.005
        self.last_rms = 0.0

    def is_speech(self, block: np.ndarray) -> bool:
        rms = float(np.sqrt(np.mean(block * block))) if len(block) else 0.0
        self.last_rms = rms
        speech = rms > self.min_rms and rms > self.ratio * self.noise_floor
        if not speech:
            # track the floor only while quiet, so speech does not raise it
            self.noise_floor += self.floor_rate * (rms - self.noise_floor)
            self.noise_floor = max(self.noise_floor, 1e-4)
        return speech

    def reset(self) -> None:
        self.noise_floor = 0.005


class Segmenter:
    """Hysteresis around the block decisions.

    A segment starts after `start_blocks` speech blocks in a row and ends after
    `hangover_blocks` silent blocks; it is cut at `max_blocks`."""

    def __init__(self, start_blocks: int = 3, hangover_blocks: int = 20, max_blocks: int = 150) -> None:
        self.start_blocks = start_blocks
        self.hangover_blocks = hangover_blocks
        self.max_blocks = max_blocks
        self.reset()

    def reset(self) -> None:
        self.active = False
        self._speech_run = 0
        self._silence_run = 0
        self._length = 0

    def update(self, speech: bool) -> str:
        """Returns "start", "end", "continue" or "idle"."""
        if not self.active:
            self._speech_run = self._speech_run + 1 if speech else 0
            if self._speech_run >= self.start_blocks:
                self.active = True
                self._silence_run = 0
                self._length = self._speech_run
                return "start"
            return "idle"
        self._length += 1
        self._silence_run = 0 if speech else self._silence_run + 1
        if self._silence_run >= self.hangover_blocks or self._length >= self.max_blocks:
            self.reset()
            return "end"
        return "continue"
