"""Pre-renders the patient's lines to WAV. Runs at setup, never during play.

Speech synthesis during a round would cost latency and energy for no benefit:
the lines are fixed, so they are rendered once and then only played back
(PLAN.md, "Speech pipeline", step 6).

Piper is driven through its command line rather than its Python API, which
changes between releases; this only runs at setup, so the process cost is
irrelevant.
"""

import subprocess
import urllib.request
from pathlib import Path

from .lines import LINES

# en_US-lessac-medium: a clear, neutral American English voice.
VOICE = "en_US-lessac-medium"
VOICE_BASE = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
    "en/en_US/lessac/medium/" + VOICE
)


class TtsRenderer:
    def __init__(self, out_dir, voice_dir, python=None):
        self.out_dir = Path(out_dir)
        self.voice_dir = Path(voice_dir)
        self.python = python or "python3"

    def ensure_voice(self):
        """Download the voice model once. Never committed to the repo."""
        self.voice_dir.mkdir(parents=True, exist_ok=True)
        model = self.voice_dir / f"{VOICE}.onnx"
        config = self.voice_dir / f"{VOICE}.onnx.json"
        for path, url in ((model, VOICE_BASE + ".onnx"),
                          (config, VOICE_BASE + ".onnx.json")):
            if not path.exists():
                print(f"downloading {path.name} ...")
                urllib.request.urlretrieve(url, path)
        return model

    def render_all(self, lines=None):
        """Render every line that is not on disk yet. Returns {id: path}."""
        model = self.ensure_voice()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        rendered = {}
        for line_id, text in (lines or LINES).items():
            path = self.out_dir / f"{line_id}.wav"
            if not path.exists():
                subprocess.run(
                    [self.python, "-m", "piper", "--model", str(model),
                     "--output_file", str(path)],
                    input=text.encode(), check=True, capture_output=True,
                )
            rendered[line_id] = path
        return rendered
