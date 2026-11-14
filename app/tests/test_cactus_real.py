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
NEEDLE = MODELS / "needle3-12L.cact"
WHISTLE = MODELS / "whistle.cact"
needs_needle = pytest.mark.skipif(not NEEDLE.is_file(), reason="no needle3-12L.cact in app/models")
needs_whistle = pytest.mark.skipif(not WHISTLE.is_file(), reason="no whistle.cact in app/models")


@needs_needle
def test_needle_reads_drug_and_amount_without_executing_and_ends_its_worker():
    from trainer.cactus_models.needle_agent import NeedleAgent
    from trainer.cactus_models.needle_orders import SYSTEM
    from trainer.game.actions import MODEL_ACTIONS, ActionCatalog

    agent = NeedleAgent(NEEDLE, SYSTEM, ActionCatalog(MODEL_ACTIONS).schemas())
    calls = agent.calls("Give him 30 milligrams of propofol.")
    assert [(c.name, c.arguments) for c in calls] == [("give_propofol", {"milligrams": 30})]
    assert 0.1 <= calls[0].confidence <= 1.0  # the rung keeps the confidence head
    assert agent.calls("Propofol.") == []  # an invented amount is ungrounded: dropped
    assert agent.peak_ram_mb > 0
    worker = agent._agent._worker
    assert worker is not None  # a rung runs in the runtime's own worker process
    agent.unload()
    assert worker._process.poll() is not None


@needs_needle
def test_needle_orders_from_sentences():
    from trainer.cactus_models.needle_orders import NeedleOrders

    orders = NeedleOrders(DEFAULT_TREATMENTS, NEEDLE)
    try:
        def said(text):
            return [(m.word, m.amount) for m in orders.orders(text)]

        assert said("Turn the oxygen up to 80 percent please.") == [("oxygen", 80.0)]
        assert said("Push 10 micrograms of adrenaline.") == [("adrenaline", 10.0)]
        assert said("More propofol!") == [("propofol", None)]  # named, no amount: the standard dose
        assert said("His sats look good now.") == []  # no drug named: the model is not asked
    finally:
        orders.unload()


def _say(text: str, path: Path) -> bool:
    if shutil.which("say") is None:
        return False
    subprocess.run(["say", "-v", "Samantha", "-o", str(path), "--data-format=LEI16@16000", text], check=True)
    return True


@needs_whistle
def test_whistle_transcribes_a_sentence(tmp_path):
    from trainer.cactus_models.whistle_recognizer import WhistleRecognizer

    path = tmp_path / "said.wav"
    if not _say("Give him 30 milligrams of propofol, and oxygen to 60 percent.", path):
        pytest.skip("no speech synthesiser (macOS say) here")
    with wave.open(str(path)) as w:
        pcm = w.readframes(w.getnframes())
    from trainer.core.config import VoiceConfig
    from trainer.voice.voice_service import build_sentence_recognizer

    rec = build_sentence_recognizer(VoiceConfig(sentence_recognizer="whistle", whistle_weights=str(WHISTLE)), DEFAULT_TREATMENTS)
    assert isinstance(rec, WhistleRecognizer)  # as the app builds it: biased towards the drugs and units
    for i in range(0, len(pcm), 640):  # 20 ms blocks, as the voice thread feeds them
        rec.accept(pcm[i:i + 640])
    heard = rec.finish()
    text = heard.text.lower()
    assert "propofol" in text and "30" in text and "60" in text  # Whistle writes the amounts as digits
    assert 0.5 < heard.confidence <= 1.0
    assert rec.finish().text == ""
