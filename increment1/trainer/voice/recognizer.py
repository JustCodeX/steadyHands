"""Speech-to-text.

D2 is decided: Whistle (Cactus Compute). Apache-2.0, 16.9 MB, 0.63 s for a
3 s clip on the board, with no torch stack. See docs/measurements.md.

`SpeechRecognizer` stays abstract so another engine can be swapped in through
the config without touching VoiceService (PLAN.md, "Adding a feature").
"""

import os
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np

# Must be set before cactus is imported: the library phones home with
# anonymous usage counts otherwise, and C2/C4 promise no outbound traffic.
os.environ.setdefault("CACTUS_TELEMETRY", "0")


# Whisper-family models emit these on silence or noise instead of nothing.
# Measured on the board: left listening to an empty room, Whistle returned
# "Thank you." over and over. The VAD gate catches most of it; this catches
# what slips through. Compared case-insensitively, without punctuation.
HALLUCINATIONS = {
    "thank you",
    "thank you.",
    "thanks for watching",
    "thanks for watching!",
    "you",
    "bye",
    "vielen dank",
    "untertitelung des zdf fur funk",
    "sous-titrage societe radio-canada",
    "sous-titrage sous-titrage",
    "merci",
}


def is_hallucination(text):
    stripped = text.strip().strip(".!?,").lower()
    return not stripped or stripped in HALLUCINATIONS


@dataclass
class Transcript:
    """What the recogniser heard, with the cost of hearing it."""

    text: str
    seconds: float


class SpeechRecognizer(ABC):
    """Turns a segment of audio into text."""

    @abstractmethod
    def transcribe(self, segment):
        """segment: float32 samples at 16 kHz. Returns a Transcript."""

    def warm_up(self):
        """Load the model now rather than on the first spoken command.

        Whistle takes 8.5 s to load and 0.63 s per clip afterwards, so this
        has to happen at startup or the first command blows the latency
        budget.
        """
        self.transcribe(np.zeros(16000, dtype=np.float32))


class WhistleRecognizer(SpeechRecognizer):
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self._tmp = "/tmp/trainer-stt.wav"

    def transcribe(self, segment):
        import time

        import cactus

        self._write_wav(segment)
        t0 = time.monotonic()
        result = cactus.transcribe(self._tmp)
        seconds = time.monotonic() - t0
        text = result.get("text", "") if isinstance(result, dict) else str(result)
        text = text.strip()
        if is_hallucination(text):
            text = ""
        return Transcript(text=text, seconds=seconds)

    def _write_wav(self, segment):
        pcm = np.clip(segment, -32768, 32767).astype(np.int16)
        with wave.open(self._tmp, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.sample_rate)
            w.writeframes(pcm.tobytes())
