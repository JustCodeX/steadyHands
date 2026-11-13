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

from .lines import all_lines

log = logging.getLogger(__name__)


class TtsRenderer:
    def __init__(self, out_dir: str | Path, engine: str = "piper", piper_voice: str | Path | None = None) -> None:
        self.out_dir = Path(out_dir)
        self.engine = engine
        self.piper_voice = Path(piper_voice) if piper_voice else None
        self._voice = None

    def render_all(self, force: bool = False) -> int:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        n = 0
        for line_id, text in all_lines().items():
            out = self.out_dir / f"{line_id.replace(' ', '_')}.wav"
            if out.exists() and not force:
                continue
            self.render(text, out)
            n += 1
        return n

    def render(self, text: str, out: Path) -> None:
        if self.engine == "piper":
            self._render_piper(text, out)
        elif self.engine == "espeak":
            self._render_espeak(text, out)
        else:
            raise ValueError(f"unknown TTS engine {self.engine}")

    def _render_piper(self, text: str, out: Path) -> None:
        if self._voice is None:
            from piper import PiperVoice

            if self.piper_voice is None or not self.piper_voice.is_file():
                raise FileNotFoundError(f"Piper voice not found: {self.piper_voice}")
            self._voice = PiperVoice.load(str(self.piper_voice))
        with wave.open(str(out), "wb") as wf:
            self._voice.synthesize_wav(text, wf)

    @staticmethod
    def _render_espeak(text: str, out: Path) -> None:
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        if not exe:
            raise FileNotFoundError("espeak-ng not installed")
        subprocess.run([exe, "-v", "en-us", "-s", "160", "-w", str(out), text], check=True)
