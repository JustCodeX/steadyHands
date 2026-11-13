import numpy as np

from trainer.core.config import DEFAULT_COMMANDS, VoiceConfig
from trainer.core.event_bus import EventBus
from trainer.core.events import CommandEvent, ListenRequest, MisheardEvent, PlaybackStarted, VoiceState, VoiceStateChanged
from trainer.voice.recognizer import SpeechRecognizer, Transcript
from trainer.voice.signal_processor import SignalProcessor
from trainer.voice.vad import EnergyVad, Segmenter
from trainer.voice.voice_service import VoiceService


class FakeRecognizer(SpeechRecognizer):
    def __init__(self, text, conf=0.9):
        self.text, self.conf = text, conf

    def accept(self, pcm):
        pass

    def finish(self):
        return Transcript(self.text, self.conf)


class FakeAudio:
    running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def read(self, timeout=0.1):
        return None


def test_highpass_removes_dc_and_keeps_tone():
    sp = SignalProcessor(16000, 100.0, target_rms=0.08, max_gain=1.0)
    t = np.arange(16000) / 16000
    x = (0.5 + 0.2 * np.sin(2 * np.pi * 1000 * t)) * 32767
    y = sp.highpass(x.astype(np.float32) / 32768.0)
    tail = y[8000:]
    assert abs(float(np.mean(tail))) < 0.01
    assert float(np.std(tail)) > 0.1


def test_split_keeps_vad_input_unlevelled():
    sp = SignalProcessor(16000, 0.0, target_rms=0.1, max_gain=12.0, release=1.0)
    quiet = (0.005 * np.random.randn(320)).astype(np.float32)
    filtered, levelled = sp.split((quiet * 32767).astype(np.int16))
    assert float(np.sqrt(np.mean(filtered**2))) < 0.01
    assert float(np.sqrt(np.mean(levelled**2))) > 0.03


def test_normalise_lifts_quiet_signal():
    sp = SignalProcessor(16000, 0.0, target_rms=0.1, max_gain=12.0, release=1.0)
    quiet = (0.005 * np.random.randn(320)).astype(np.float32)
    out = sp.normalise(quiet)
    assert float(np.sqrt(np.mean(out * out))) > 0.03


def test_energy_vad_and_segmenter():
    vad = EnergyVad(ratio=3.0, min_rms=0.01)
    seg = Segmenter(start_blocks=2, hangover_blocks=3, max_blocks=50)
    rng = np.random.default_rng(0)
    quiet = (0.002 * rng.standard_normal(320)).astype(np.float32)
    loud = (0.2 * rng.standard_normal(320)).astype(np.float32)
    for _ in range(20):
        assert not vad.is_speech(quiet)
        assert seg.update(False) == "idle"
    phases = [seg.update(vad.is_speech(loud)) for _ in range(5)]
    assert phases[1] == "start" and phases[2] == "continue"
    phases = [seg.update(vad.is_speech(quiet)) for _ in range(4)]
    assert "end" in phases


def make_service(recognizer, threshold=0.6):
    bus = EventBus()
    cfg = VoiceConfig(confidence_threshold=threshold)
    svc = VoiceService(bus, cfg, DEFAULT_COMMANDS, recognizer=recognizer, audio=FakeAudio())
    return bus, svc


def test_segment_to_command_event():
    bus, svc = make_service(FakeRecognizer("clamp", 0.95))
    seen = []
    bus.subscribe(CommandEvent, seen.append)
    svc.handle_segment(speech_end_t=1.0)
    bus.dispatch()
    assert seen[0].word == "clamp" and seen[0].speech_end_t == 1.0


def test_low_confidence_is_misheard_and_gibberish_is_silent():
    bus, svc = make_service(FakeRecognizer("clamp", 0.2))
    seen = []
    bus.subscribe(MisheardEvent, seen.append)
    bus.subscribe(CommandEvent, seen.append)
    svc.handle_segment(speech_end_t=1.0)
    bus.dispatch()
    assert len(seen) == 1 and isinstance(seen[0], MisheardEvent)

    for text in ("lorem ipsum dolor", ""):
        bus, svc = make_service(FakeRecognizer(text, 0.9))
        seen = []
        bus.subscribe(MisheardEvent, seen.append)
        bus.subscribe(CommandEvent, seen.append)
        svc.handle_segment(speech_end_t=1.0)
        bus.dispatch()
        assert seen == []  # unrelated talk and noise are ignored


def test_states_follow_listen_and_playback():
    bus, svc = make_service(FakeRecognizer("", 0.0))
    states = []
    bus.subscribe(VoiceStateChanged, lambda e: states.append(e.state))
    bus.publish(ListenRequest(on=True))
    bus.dispatch()
    bus.publish(PlaybackStarted())
    bus.dispatch()
    bus.publish(ListenRequest(on=False))
    bus.dispatch()
    assert states == [VoiceState.LISTENING, VoiceState.SPEAKING, VoiceState.OFF]
