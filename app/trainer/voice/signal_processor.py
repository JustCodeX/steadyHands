"""High-pass filter and level normalisation on int16 blocks."""
from __future__ import annotations

import math

import numpy as np


class SignalProcessor:
    def __init__(
        self,
        sample_rate: int = 16000,
        highpass_hz: float = 100.0,
        target_rms: float = 0.08,
        max_gain: float = 12.0,
        attack: float = 0.3,
        release: float = 0.02,
    ) -> None:
        # one-pole high-pass: y[n] = a * (y[n-1] + x[n] - x[n-1])
        rc = 1.0 / (2 * math.pi * highpass_hz) if highpass_hz > 0 else 0.0
        dt = 1.0 / sample_rate
        self._a = rc / (rc + dt) if highpass_hz > 0 else 0.0
        self._prev_x = 0.0
        self._prev_y = 0.0
        self.target_rms = target_rms
        self.max_gain = max_gain
        self.attack = attack
        self.release = release
        self.gain = 1.0

    def highpass(self, x: np.ndarray) -> np.ndarray:
        if self._a == 0.0:
            return x
        a = self._a
        y = np.empty_like(x)
        prev_x, prev_y = self._prev_x, self._prev_y
        for i in range(len(x)):
            xi = x[i]
            prev_y = a * (prev_y + xi - prev_x)
            prev_x = xi
            y[i] = prev_y
        self._prev_x, self._prev_y = prev_x, prev_y
        return y

    def normalise(self, x: np.ndarray) -> np.ndarray:
        rms = float(np.sqrt(np.mean(x * x))) if len(x) else 0.0
        if rms > 1e-4:
            wanted = min(self.max_gain, max(1.0, self.target_rms / rms))
            # fast when the signal is too loud, slow when it is quiet
            rate = self.attack if wanted < self.gain else self.release
            self.gain += rate * (wanted - self.gain)
        return np.clip(x * self.gain, -1.0, 1.0)

    def process(self, block_int16: np.ndarray) -> np.ndarray:
        """int16 in, float32 in -1..1 out: filtered and levelled."""
        x = block_int16.astype(np.float32) / 32768.0
        return self.normalise(self.highpass(x)).astype(np.float32)

    @staticmethod
    def to_int16(x: np.ndarray) -> bytes:
        return (np.clip(x, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
