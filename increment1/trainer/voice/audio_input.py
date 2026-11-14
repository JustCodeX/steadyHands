"""Microphone capture.

Capture goes through `arecord` as a subprocess rather than PortAudio.
`sounddevice` and `pyaudio` need the PortAudio shared library, which would
need apt and therefore sudo on the board; reading raw frames from arecord
avoids that dependency entirely.

The USB headset cannot do 16 kHz natively (it falls back to 48 kHz and warns
"try the plug plugin"), so the device is addressed as `plughw:`, which lets
ALSA resample.
"""

import subprocess

import numpy as np

DEFAULT_DEVICE = "plughw:0,0"
SAMPLE_RATE = 16000


class AudioInput:
    """Reads mono 16-bit audio from an ALSA capture device."""

    def __init__(self, device=DEFAULT_DEVICE, sample_rate=SAMPLE_RATE):
        self.device = device
        self.sample_rate = sample_rate

    def record(self, seconds):
        """Record a fixed-length clip and return it as float32 samples."""
        raw = subprocess.run(
            ["arecord", "-D", self.device, "-f", "S16_LE",
             "-r", str(self.sample_rate), "-c", "1",
             "-d", str(seconds), "-t", "raw", "-q"],
            capture_output=True, check=True,
        ).stdout
        return np.frombuffer(raw, dtype=np.int16).astype(np.float32)

    def stream(self, chunk_ms=30):
        """Yield fixed-size chunks for as long as the caller keeps reading.

        Used by the VAD gate, which needs a steady frame size rather than
        whole clips.
        """
        frames = int(self.sample_rate * chunk_ms / 1000)
        proc = subprocess.Popen(
            ["arecord", "-D", self.device, "-f", "S16_LE",
             "-r", str(self.sample_rate), "-c", "1", "-t", "raw", "-q"],
            stdout=subprocess.PIPE,
        )
        try:
            while True:
                buf = proc.stdout.read(frames * 2)
                if len(buf) < frames * 2:
                    break
                yield np.frombuffer(buf, dtype=np.int16).astype(np.float32)
        finally:
            proc.terminate()
            proc.wait(timeout=5)
