"""The gate in front of the recogniser.

Whistle is a Whisper-family model, and those hallucinate on silence: left
running on an empty room it returns "Thank you." over and over. Measured on
the board, not theory - see docs/measurements.md.

So speech-to-text must only ever see audio that actually contains speech.
This is the cheap energy gate; Silero or WebRTC VAD can replace it behind the
same interface if the hall turns out to need something better.

It also saves energy, which is a judging criterion: the model does not run at
all while nobody is speaking.
"""

import numpy as np

FRAME_MS = 30
# Below this RMS a frame counts as silence. 16-bit samples, so full scale is
# 32768; a quiet room measures well under 200.
SILENCE_RMS = 220
# How much of the clip has to be speech before we bother transcribing.
MIN_VOICED_FRACTION = 0.06


class VoiceActivityDetector:
    """Decides whether a segment is worth sending to speech-to-text."""

    def __init__(self, sample_rate=16000, frame_ms=FRAME_MS,
                 silence_rms=SILENCE_RMS, min_voiced=MIN_VOICED_FRACTION):
        self.frame_samples = int(sample_rate * frame_ms / 1000)
        self.silence_rms = silence_rms
        self.min_voiced = min_voiced

    def voiced_fraction(self, segment):
        """How much of the segment carries speech-level energy, 0.0 to 1.0."""
        usable = len(segment) // self.frame_samples * self.frame_samples
        if usable == 0:
            return 0.0
        frames = segment[:usable].reshape(-1, self.frame_samples)
        energy = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
        return float((energy > self.silence_rms).mean())

    def has_speech(self, segment):
        return self.voiced_fraction(segment) >= self.min_voiced
