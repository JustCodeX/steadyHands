"""Vosk with the vocabulary restricted to our command phrases."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .recognizer import SpeechRecognizer, Transcript

log = logging.getLogger(__name__)


class VoskRecognizer(SpeechRecognizer):
    def __init__(self, model_dir: str | Path, phrases: list[str], sample_rate: int = 16000) -> None:
        from vosk import KaldiRecognizer, Model, SetLogLevel

        SetLogLevel(-1)
        model_dir = Path(model_dir)
        if not model_dir.is_dir():
            raise FileNotFoundError(f"Vosk model not found at {model_dir}; run app/setup/download_models.sh")
        self._model = Model(str(model_dir))
        grammar = json.dumps(sorted(set(phrases)) + ["[unk]"])
        self._rec = KaldiRecognizer(self._model, sample_rate, grammar)
        self._rec.SetWords(True)
        log.info("Vosk model loaded from %s with %d phrases", model_dir, len(phrases))

    def accept(self, pcm_int16: bytes) -> None:
        self._rec.AcceptWaveform(pcm_int16)

    def finish(self) -> Transcript:
        data = json.loads(self._rec.FinalResult())
        text = (data.get("text") or "").strip()
        words = [w for w in data.get("result", []) if w.get("word") != "[unk]"]
        conf = sum(float(w.get("conf", 0.0)) for w in words) / len(words) if words else 0.0
        if "[unk]" in text:
            text = " ".join(w for w in text.split() if w != "[unk]")
        return Transcript(text=text, confidence=conf)

    def reset(self) -> None:
        self._rec.Reset()
