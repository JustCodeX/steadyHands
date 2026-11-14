"""Vosk, either restricted to a phrase list or with its full vocabulary."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .recognizer import SpeechRecognizer, Transcript

log = logging.getLogger(__name__)


class VoskRecognizer(SpeechRecognizer):
    """`phrases` restricts the vocabulary to those phrases (robust, for
    commands); `phrases=None` recognises free speech with the same model.

    The model is loaded once per directory and shared, so a restricted and an
    open recogniser side by side cost one model's memory."""

    _models: dict[str, object] = {}

    def __init__(self, model_dir: str | Path, phrases: list[str] | None, sample_rate: int = 16000) -> None:
        self._model = self._load_model(Path(model_dir))
        self._sample_rate = sample_rate
        self._restricted = phrases is not None
        self._by_vocabulary: dict[tuple[str, ...], object] = {}  # one Kaldi recogniser per phrase list
        if phrases is None:
            from vosk import KaldiRecognizer

            self._rec = KaldiRecognizer(self._model, sample_rate)
            self._rec.SetWords(True)
            log.info("Vosk recogniser with open vocabulary")
        else:
            self.set_vocabulary(phrases)
            log.info("Vosk recogniser restricted to %d phrases", len(set(phrases)))

    def set_vocabulary(self, phrases: list[str]) -> None:
        """Switch a restricted recogniser to another phrase list. Each list gets
        its own Kaldi recogniser on the shared model, built once and kept (a
        few hundred kB each)."""
        if not self._restricted:
            return
        key = tuple(sorted(set(phrases)))
        if key not in self._by_vocabulary:
            from vosk import KaldiRecognizer

            rec = KaldiRecognizer(self._model, self._sample_rate, json.dumps(list(key) + ["[unk]"]))
            rec.SetWords(True)
            self._by_vocabulary[key] = rec
        self._rec = self._by_vocabulary[key]
        self._rec.Reset()

    @classmethod
    def _load_model(cls, model_dir: Path):
        key = str(model_dir.resolve())
        if key not in cls._models:
            from vosk import Model, SetLogLevel

            SetLogLevel(-1)
            if not model_dir.is_dir():
                raise FileNotFoundError(f"Vosk model not found at {model_dir}; run app/setup/download_models.sh")
            cls._models[key] = Model(str(model_dir))
            log.info("Vosk model loaded from %s", model_dir)
        return cls._models[key]

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

    def partial(self) -> str:
        data = json.loads(self._rec.PartialResult())
        text = (data.get("partial") or "").strip()
        return " ".join(w for w in text.split() if w != "[unk]")

    def reset(self) -> None:
        self._rec.Reset()
