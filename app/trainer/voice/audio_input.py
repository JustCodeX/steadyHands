"""Microphone capture: 16 kHz mono int16 blocks, kept in memory only."""
from __future__ import annotations

import logging
import queue

import numpy as np

log = logging.getLogger(__name__)


class AudioInput:
    def __init__(self, sample_rate: int = 16000, block_ms: int = 20, device: str = "") -> None:
        self.sample_rate = sample_rate
        self.block_size = sample_rate * block_ms // 1000
        self.device = device
        self._queue: queue.Queue = queue.Queue(maxsize=200)
        self._stream = None

    def _resolve_device(self):
        if not self.device:
            return None
        import sounddevice as sd

        for idx, dev in enumerate(sd.query_devices()):
            if self.device.lower() in dev["name"].lower() and dev["max_input_channels"] > 0:
                return idx
        log.warning("input device containing %r not found; using default", self.device)
        return None

    def start(self) -> None:
        import sounddevice as sd

        def callback(indata, frames, time_info, status):
            if status:
                log.debug("audio status: %s", status)
            try:
                self._queue.put_nowait(indata[:, 0].copy())
            except queue.Full:
                pass  # drop rather than block the audio thread

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=self.block_size,
            device=self._resolve_device(),
            callback=callback,
        )
        self._stream.start()
        log.info("microphone open: %d Hz, %d-sample blocks", self.sample_rate, self.block_size)

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._queue.mutex:
            self._queue.queue.clear()

    @property
    def running(self) -> bool:
        return self._stream is not None

    def read(self, timeout: float = 0.1) -> np.ndarray | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
