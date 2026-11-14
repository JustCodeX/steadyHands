"""Playback of the pre-rendered lines."""

import subprocess
from pathlib import Path

DEFAULT_DEVICE = "plughw:0,0"


class ClipLibrary:
    """The rendered lines on disk, played through ALSA."""

    def __init__(self, clip_dir, device=DEFAULT_DEVICE):
        self.clip_dir = Path(clip_dir)
        self.device = device

    def path(self, line_id):
        return self.clip_dir / f"{line_id}.wav"

    def has(self, line_id):
        return self.path(line_id).exists()

    def play(self, line_id):
        """Play a line and block until it has finished.

        Blocking is deliberate where the caller has nothing else to do: the
        mic must stay ignored while the patient speaks, so the game never
        reacts to its own voice.
        """
        self.start(line_id).wait()

    def start(self, line_id):
        """Start a line and return the process, so the caller can animate.

        The avatar's mouth has to move while the line plays, which it cannot
        do if playback blocks the draw loop.
        """
        clip = self.path(line_id)
        if not clip.exists():
            raise FileNotFoundError(f"line {line_id!r} has not been rendered: {clip}")
        return subprocess.Popen(
            ["aplay", "-D", self.device, "-q", str(clip)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
