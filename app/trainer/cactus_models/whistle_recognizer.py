"""Whistle (Cactus), a small open-vocabulary speech-to-text model."""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from ..voice.recognizer import SpeechRecognizer, Transcript
from .runtime import load_cactus

log = logging.getLogger(__name__)


class WhistleRecognizer(SpeechRecognizer):
    """Transcribes a whole speech segment when it ends. Segments are short (a
    command or one sentence) and the model runs several times faster than
    real time, so streaming would gain little.

    The model has no restricted vocabulary; `set_vocabulary` passes the
    phrases on as words to listen for. Like every model of its family it
    invents words for silence ("Thank you."), so it must only ever see what
    the voice activity gate let through."""

    def __init__(self, weights: str | Path, language: str = "en", keywords: list[str] | None = None, sample_rate: int = 16000) -> None:
        self.weights = Path(weights)
        if not self.weights.is_file():
            raise FileNotFoundError(f"Whistle weights not found at {self.weights}; run app/setup/download_models.sh")
        if sample_rate != 16000:
            raise ValueError("Whistle needs 16 kHz audio")
        self.language = language
        self._keywords = sorted(set(keywords)) if keywords else None
        self._cactus = load_cactus()
        self._chunks: list[bytes] = []
        self._transcribe(np.zeros(8000, dtype=np.float32))  # the first call loads the engine
        log.info("Whistle loaded from %s", self.weights.name)

    def _transcribe(self, samples: np.ndarray) -> dict:
        return self._cactus.transcribe(
            samples.tolist(),
            language=self.language,
            keywords=self._keywords,
            word_timestamps=True,
            weights=str(self.weights),
        )

    def set_vocabulary(self, phrases: list[str]) -> None:
        self._keywords = sorted(set(phrases)) or None

    def accept(self, pcm_int16: bytes) -> None:
        self._chunks.append(pcm_int16)

    def finish(self) -> Transcript:
        pcm, self._chunks = b"".join(self._chunks), []
        if not pcm:
            return Transcript(text="", confidence=0.0)
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        result = self._transcribe(samples)
        text = (result.get("text") or "").strip()
        probabilities = [float(w["probability"]) for w in result.get("words") or [] if "probability" in w]
        confidence = sum(probabilities) / len(probabilities) if probabilities else (1.0 if text else 0.0)
        return Transcript(text=text, confidence=confidence)

    def reset(self) -> None:
        self._chunks = []
