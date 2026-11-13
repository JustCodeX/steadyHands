"""The adapters against the real Cactus runtime (cactus-compute 4.2.0).

Skipped unless the package is installed and the model files are in
app/models/. Checks the runtime behaviour the adapters rely on, not the
model's quality (that is tools/needle_eval.py).
"""
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from trainer.core.config import APP_DIR, DEFAULT_TREATMENTS

pytest.importorskip("cactus")
MODELS = APP_DIR / "models"
NEEDLE = MODELS / "needle3-9L.cact"
WHISTLE = MODELS / "whistle.cact"
needs_needle = pytest.mark.skipif(not NEEDLE.is_file(), reason="no needle3-9L.cact in app/models")
needs_whistle = pytest.mark.skipif(not WHISTLE.is_file(), reason="no whistle.cact in app/models")


@needs_needle
def test_needle_proposes_a_call_without_executing_and_ends_its_worker():
    from trainer.cactus_models.needle_agent import NeedleAgent
    from trainer.cactus_models.needle_interpreter import SYSTEM
    from trainer.game.actions import MODEL_ACTIONS, ActionCatalog

    agent = NeedleAgent(NEEDLE, SYSTEM, ActionCatalog(MODEL_ACTIONS).schemas())
    call = agent.call("he can't breathe, his sats are dropping")
    assert call is not None and call.name == "give_oxygen" and call.arguments == {}
    assert 0.1 <= call.confidence <= 1.0  # the rung keeps the confidence head
    assert agent.peak_ram_mb > 0
    worker = agent._agent._worker
    assert worker is not None  # a rung runs in the runtime's own worker process
    agent.unload()
    assert worker._process.poll() is not None


@needs_needle
def test_needle_interpreter_turns_a_sentence_into_a_treatment():
    from trainer.cactus_models.needle_interpreter import NeedleInterpreter

    interpreter = NeedleInterpreter(DEFAULT_TREATMENTS, NEEDLE)
    try:
        assert interpreter.interpret("his blood pressure is dropping fast").word == "adrenaline"
        assert interpreter.interpret("give me the clamp") is None  # no trigger word: the model is not asked
    finally:
        interpreter.unload()


def _say(text: str, path: Path) -> bool:
    if shutil.which("say") is None:
        return False
    subprocess.run(["say", "-v", "Samantha", "-o", str(path), "--data-format=LEI16@16000", text], check=True)
    return True


@needs_whistle
def test_whistle_transcribes_a_sentence(tmp_path):
    from trainer.cactus_models.whistle_recognizer import WhistleRecognizer

    path = tmp_path / "said.wav"
    if not _say("He can't breathe, give him more oxygen please.", path):
        pytest.skip("no speech synthesiser (macOS say) here")
    with wave.open(str(path)) as w:
        pcm = w.readframes(w.getnframes())
    rec = WhistleRecognizer(WHISTLE, language="en")
    for i in range(0, len(pcm), 640):  # 20 ms blocks, as the voice thread feeds them
        rec.accept(pcm[i:i + 640])
    heard = rec.finish()
    assert "oxygen" in heard.text.lower() and "breathe" in heard.text.lower()
    assert 0.5 < heard.confidence <= 1.0
    assert rec.finish().text == ""
