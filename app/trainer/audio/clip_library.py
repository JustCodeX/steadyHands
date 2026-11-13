"""Loads WAV clips by line id, lazily, from the clips folder."""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


class ClipLibrary:
    def __init__(self, clips_dir: str | Path) -> None:
        self.clips_dir = Path(clips_dir)
        self._cache: dict[str, object] = {}
        self._missing: set[str] = set()

    def path(self, line_id: str) -> Path:
        return self.clips_dir / f"{line_id.replace(' ', '_')}.wav"

    def has(self, line_id: str) -> bool:
        return self.path(line_id).is_file()

    def count(self) -> int:
        return len(list(self.clips_dir.glob("*.wav"))) if self.clips_dir.is_dir() else 0

    def get(self, line_id: str):
        """Returns a pygame Sound, or None if the clip is missing."""
        if line_id in self._cache:
            return self._cache[line_id]
        p = self.path(line_id)
        if not p.is_file():
            if line_id not in self._missing:
                self._missing.add(line_id)
                log.warning("missing clip %s (run app/tools/render_clips.py)", p.name)
            return None
        import pygame

        sound = pygame.mixer.Sound(str(p))
        self._cache[line_id] = sound
        return sound
