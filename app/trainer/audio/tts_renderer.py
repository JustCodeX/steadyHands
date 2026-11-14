"""Setup-time text-to-speech: renders every line in lines.py to a WAV file.

Engines: Piper (preferred, neural, offline) or espeak-ng (fallback). Nothing
here runs during play.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import wave
from pathlib import Path

from ..quiz.question import QuestionBank
from .lines import all_lines, nurse_ids

log = logging.getLogger(__name__)


class TtsRenderer:
    def __init__(
        self,
        out_dir: str | Path,
        engine: str = "piper",
        piper_voice: str | Path | None = None,
        questions: QuestionBank | None = None,
        nurse_voice: str | Path | None = None,
    ) -> None:
        self.questions = questions
        self.out_dir = Path(out_dir)
        self.engine = engine
        self.piper_voice = Path(piper_voice) if piper_voice else None
        # the nurse's own voice if its file is there, else the patient's
        self.nurse_voice = Path(nurse_voice) if nurse_voice and Path(nurse_voice).is_file() else None
        self._voices: dict[Path, object] = {}

    def render_all(self, force: bool = False, force_nurse: bool = False) -> int:
        """Render missing clips. `force`: all again; `force_nurse`: the nurse's
        again (after her voice file was added or changed)."""
        self.out_dir.mkdir(parents=True, exist_ok=True)
        nurse = nurse_ids()
        n = 0
        for line_id, text in all_lines(self.questions).items():
            out = self.out_dir / f"{line_id.replace(' ', '_')}.wav"
            if out.exists() and not (force or (force_nurse and line_id in nurse)):
                continue
            self.render(text, out, self.voice_for(line_id))
            n += 1
        return n

    def voice_for(self, line_id: str) -> Path | None:
        if self.nurse_voice is not None and line_id in nurse_ids():
            return self.nurse_voice
        return self.piper_voice

    def render(self, text: str, out: Path, voice: Path | None = None) -> None:
        if self.engine == "piper":
            self._render_piper(text, out, voice or self.piper_voice)
        elif self.engine == "espeak":
            self._render_espeak(text, out)
        else:
            raise ValueError(f"unknown TTS engine {self.engine}")

    def _render_piper(self, text: str, out: Path, voice: Path | None) -> None:
        if voice is None or not voice.is_file():
            raise FileNotFoundError(f"Piper voice not found: {voice}")
        if voice not in self._voices:
            from piper import PiperVoice

            self._voices[voice] = PiperVoice.load(str(voice))
        with wave.open(str(out), "wb") as wf:
            self._voices[voice].synthesize_wav(text, wf)

    @staticmethod
    def _render_espeak(text: str, out: Path) -> None:
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        if not exe:
            raise FileNotFoundError("espeak-ng not installed")
        subprocess.run([exe, "-v", "en-us", "-s", "160", "-w", str(out), text], check=True)
