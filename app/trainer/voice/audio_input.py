"""Microphone capture: 16 kHz mono int16 blocks, kept in memory only.

The wanted device is a USB headset. Many of them (the JBL Tune 530C among
them) record at 48 kHz only, so when the device refuses 16 kHz it is opened at
its own rate and converted here. The headset can also appear after the game
has started (the USB hub connects it late), so the device list is read again
whenever the sound cards changed.
"""
from __future__ import annotations

import logging
import queue
import time

import numpy as np

log = logging.getLogger(__name__)

CARDS_FILE = "/proc/asound/cards"
# Without CARDS_FILE (not Linux) a missing device is looked for this often.
RESCAN_INTERVAL_S = 5.0


def read_sound_cards(path: str = CARDS_FILE) -> str | None:
    """The kernel's list of sound cards, or None where it does not exist."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def usb_sound_card_present(cards: str | None) -> bool | None:
    """True/False for a USB sound card on the bus; None when unknown."""
    if cards is None:
        return None
    return "USB-Audio" in cards


class Decimator:
    """Low-pass filter, then keep every `factor`-th sample.

    The filter state and the sample phase carry over between blocks, so the
    output is the same however the input is cut into blocks."""

    def __init__(self, factor: int, taps: int = 95) -> None:
        if factor < 2:
            raise ValueError("factor must be at least 2")
        self.factor = factor
        # Windowed sinc. Cutoff a little below the new Nyquist frequency so the
        # stop band starts there (48 -> 16 kHz: pass to 6.2 kHz, stop from 7.8 kHz).
        cutoff = 0.4375 / factor  # in cycles per input sample
        n = np.arange(taps) - (taps - 1) / 2
        h = 2 * cutoff * np.sinc(2 * cutoff * n) * np.hamming(taps)
        self._taps = (h / h.sum()).astype(np.float32)
        self.reset()

    def reset(self) -> None:
        self._history = np.zeros(len(self._taps) - 1, dtype=np.float32)
        self._phase = 0

    def process(self, block: np.ndarray) -> np.ndarray:
        """int16 in, int16 out at 1/factor of the rate."""
        buf = np.concatenate((self._history, block.astype(np.float32)))
        filtered = np.convolve(buf, self._taps, mode="valid")  # one value per input sample
        self._history = buf[len(buf) - len(self._history):]
        out = filtered[self._phase :: self.factor]
        self._phase = (self._phase - len(filtered)) % self.factor
        return np.clip(np.rint(out), -32768, 32767).astype(np.int16)


class AudioInput:
    def __init__(
        self,
        sample_rate: int = 16000,
        block_ms: int = 20,
        device: str = "",
        backend=None,
        cards_file: str = CARDS_FILE,
    ) -> None:
        self.sample_rate = sample_rate
        self.block_size = sample_rate * block_ms // 1000
        self.device = device
        self.device_name = ""  # what start() opened
        self.device_rate = 0
        self._backend = backend  # sounddevice, or a stand-in for tests
        self._cards_file = cards_file
        self._cards_seen: str | None = None
        self._cards_known = False
        self._last_rescan = time.monotonic()
        self._warned_missing = False
        self._queue: queue.Queue = queue.Queue(maxsize=200)
        self._stream = None
        self._decimator: Decimator | None = None

    # --- device choice -------------------------------------------------------

    def _sd(self):
        if self._backend is None:
            import sounddevice

            self._backend = sounddevice
        return self._backend

    def _find_device(self):
        """(index, info) of the wanted input device, or (None, None)."""
        if not self.device:
            return None, None
        for idx, dev in enumerate(self._sd().query_devices()):
            if self.device.lower() in dev["name"].lower() and dev["max_input_channels"] > 0:
                return idx, dev
        return None, None

    def _cards_changed(self) -> bool:
        """True when a sound card came or went since the last look (Linux)."""
        cards = read_sound_cards(self._cards_file)
        if not self._cards_known:  # first look: PortAudio has just read the same state
            self._cards_known, self._cards_seen = True, cards
            return False
        changed = cards != self._cards_seen
        self._cards_seen = cards
        return changed

    def _rescan(self) -> None:
        """Make PortAudio read the device list again; it only does so at start-up.

        Safe here because this class owns the only PortAudio stream and it is closed."""
        sd = self._sd()
        try:
            sd._terminate()
            sd._initialize()
        except Exception as exc:  # keep the old list rather than lose the microphone
            log.warning("re-reading the audio devices failed: %s", exc)
        self._last_rescan = time.monotonic()

    def _resolve_device(self):
        if self._cards_changed():
            self._rescan()
        idx, dev = self._find_device()
        if idx is None and self.device and self._cards_seen is None:
            # No card list to compare (not Linux): look again now and then.
            if time.monotonic() - self._last_rescan >= RESCAN_INTERVAL_S:
                self._rescan()
                idx, dev = self._find_device()
        if self.device:
            if idx is None and not self._warned_missing:
                log.warning("input device containing %r not found; using the default input", self.device)
                self._warned_missing = True
            elif idx is not None:
                self._warned_missing = False
        return idx, dev

    def _rates(self, dev) -> list[int]:
        """Rates to try: the pipeline's own, then whole multiples of it."""
        rates = [self.sample_rate]
        if dev is not None:
            native = int(round(dev.get("default_samplerate") or 0))
            for rate in (native, 48000, 32000):
                if rate > self.sample_rate and rate % self.sample_rate == 0 and rate not in rates:
                    rates.append(rate)
        return rates

    # --- stream --------------------------------------------------------------

    def _open(self, idx, rate: int) -> None:
        factor = rate // self.sample_rate
        decimator = Decimator(factor) if factor > 1 else None

        def callback(indata, frames, time_info, status):
            if status:
                log.debug("audio status: %s", status)
            block = indata[:, 0]
            block = decimator.process(block) if decimator is not None else block.copy()
            try:
                self._queue.put_nowait(block)
            except queue.Full:
                pass  # drop rather than block the audio thread

        stream = self._sd().InputStream(
            samplerate=rate,
            channels=1,
            dtype="int16",
            blocksize=self.block_size * factor,
            device=idx,
            callback=callback,
        )
        try:
            stream.start()
        except Exception:
            stream.close()
            raise
        self._stream, self._decimator = stream, decimator

    def start(self) -> None:
        idx, dev = self._resolve_device()
        error: Exception | None = None
        for rate in self._rates(dev):
            try:
                self._open(idx, rate)
            except Exception as exc:  # PortAudioError: this rate is not supported
                error = exc
                continue
            self.device_name = dev["name"] if dev is not None else "default input"
            self.device_rate = rate
            if rate == self.sample_rate:
                log.info("microphone open: %s, %d Hz, %d-sample blocks", self.device_name, rate, self.block_size)
            else:
                log.info("microphone open: %s, %d -> %d Hz", self.device_name, rate, self.sample_rate)
            return
        if idx is None:
            raise error  # the default input does not work either
        log.warning("input device %r cannot be opened (%s); using the default input", dev["name"], error)
        self._open(None, self.sample_rate)
        self.device_name, self.device_rate = "default input", self.sample_rate
        log.info("microphone open: default input, %d Hz, %d-sample blocks", self.sample_rate, self.block_size)

    def stop(self) -> None:
        if self._stream is not None:
            try:
                # abort(), not stop(): stop() waits for the device to deliver its
                # pending audio, and on an input that delivers none (the board's
                # built-in one, measured 13 Nov) that wait is 64 s.
                self._stream.abort()
                self._stream.close()
            finally:
                self._stream = None
                self._decimator = None
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
