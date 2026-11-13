import numpy as np
import pytest

from trainer.core.config import DEFAULT_COMMANDS, VoiceConfig
from trainer.core.event_bus import EventBus
from trainer.core.events import CommandEvent, ListenRequest, MisheardEvent, PlaybackStarted, VoiceState, VoiceStateChanged
from trainer.voice.audio_input import AudioInput, Decimator, usb_sound_card_present
from trainer.voice.recognizer import SpeechRecognizer, Transcript
from trainer.voice.signal_processor import SignalProcessor
from trainer.voice.vad import EnergyVad, Segmenter
from trainer.voice.voice_service import VoiceService, build_interpreter, build_recognizer


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


# --- headset microphone: rate conversion and device choice ---------------------


def tone(freq, rate, seconds=1.0, level=0.5):
    t = np.arange(int(rate * seconds)) / rate
    return (level * 32767 * np.sin(2 * np.pi * freq * t)).astype(np.int16)


def rms(x):
    return float(np.sqrt(np.mean(np.square(x.astype(np.float64)))))


def test_decimator_keeps_speech_band_and_removes_what_would_alias():
    low, high = tone(1000, 48000), tone(10000, 48000)
    out_low = Decimator(3).process(low)
    out_high = Decimator(3).process(high)
    assert len(out_low) == 16000
    assert abs(rms(out_low[200:]) / rms(low) - 1.0) < 0.02  # level kept
    assert rms(out_high[200:]) / rms(high) < 0.01  # more than 40 dB down
    # still a 1 kHz tone at the new rate
    spectrum = np.abs(np.fft.rfft(out_low[200:16200].astype(np.float64)))
    assert abs(np.argmax(spectrum) * 16000 / len(out_low[200:]) - 1000) < 5


def test_decimator_output_does_not_depend_on_the_block_size():
    x = tone(700, 48000, seconds=0.5)
    whole = Decimator(3).process(x)
    for size in (960, 1000):  # 1000 is not a multiple of 3: the phase must carry over
        d = Decimator(3)
        parts = [d.process(x[i : i + size]) for i in range(0, len(x), size)]
        assert np.array_equal(np.concatenate(parts), whole)


class FakeStream:
    def __init__(self, backend, samplerate, blocksize, device, callback, **kwargs):
        dev = backend.devices[device] if device is not None else {"rates": {16000}}
        if samplerate not in dev["rates"]:
            raise backend.PortAudioError("Invalid sample rate")
        self.samplerate, self.blocksize, self.device, self.callback = samplerate, blocksize, device, callback
        backend.streams.append(self)

    def start(self):
        pass

    def abort(self):
        self.aborted = True

    def close(self):
        pass


class FakeSoundDevice:
    """Stands in for the sounddevice module. `plugged` is what a rescan would find."""

    class PortAudioError(Exception):
        pass

    BUILTIN = {"name": "Arduino-Imola-HPH-LOUT: - (hw:0,2)", "max_input_channels": 4, "default_samplerate": 48000.0, "rates": {16000, 48000}}
    HEADSET = {"name": "JBL Tune 530C: USB Audio (hw:1,0)", "max_input_channels": 1, "default_samplerate": 48000.0, "rates": {48000}}

    def __init__(self, plugged):
        self.plugged = list(plugged)
        self.devices = list(plugged)
        self.streams = []
        self.rescans = 0

    def query_devices(self):
        return self.devices

    def InputStream(self, **kwargs):
        return FakeStream(self, **kwargs)

    def _terminate(self):
        pass

    def _initialize(self):
        self.rescans += 1
        self.devices = list(self.plugged)


def make_input(sd, tmp_path, cards="0 [ArduinoImolaHPH]\n"):
    cards_file = tmp_path / "cards"
    cards_file.write_text(cards)
    return AudioInput(16000, 20, "USB Audio", backend=sd, cards_file=str(cards_file)), cards_file


def test_headset_is_opened_at_its_own_rate_and_converted(tmp_path, caplog):
    sd = FakeSoundDevice([FakeSoundDevice.BUILTIN, FakeSoundDevice.HEADSET])
    audio, _ = make_input(sd, tmp_path)
    with caplog.at_level("INFO"):
        audio.start()
    stream = sd.streams[-1]
    assert (stream.device, stream.samplerate, stream.blocksize) == (1, 48000, 960)
    assert "JBL Tune 530C" in caplog.text and "48000 -> 16000 Hz" in caplog.text
    stream.callback(tone(1000, 48000, seconds=0.02).reshape(-1, 1), 960, None, None)
    block = audio.read(timeout=0.1)
    assert block.dtype == np.int16 and len(block) == 320  # what the pipeline expects
    audio.stop()
    assert not audio.running and stream.aborted  # abort: stop() can block for a minute


def test_without_headset_the_default_input_is_used_with_one_warning(tmp_path, caplog):
    sd = FakeSoundDevice([FakeSoundDevice.BUILTIN])
    audio, _ = make_input(sd, tmp_path)
    with caplog.at_level("INFO"):
        audio.start()
        audio.stop()
        audio.start()
    stream = sd.streams[-1]
    assert (stream.device, stream.samplerate, stream.blocksize) == (None, 16000, 320)
    assert caplog.text.count("not found") == 1  # not once per listening phase
    assert sd.rescans == 0  # the sound cards did not change: no rescan


def test_headset_that_appears_late_is_found_on_the_next_start(tmp_path):
    sd = FakeSoundDevice([FakeSoundDevice.BUILTIN])
    audio, cards_file = make_input(sd, tmp_path)
    audio.start()
    assert sd.streams[-1].device is None
    audio.stop()
    # the hub connects the headset: the kernel lists a new card, PortAudio's list is stale
    sd.plugged.append(FakeSoundDevice.HEADSET)
    cards_file.write_text("0 [ArduinoImolaHPH]\n 1 [T530C]: USB-Audio - JBL Tune 530C\n")
    audio.start()
    assert sd.rescans == 1
    assert (sd.streams[-1].device, sd.streams[-1].samplerate) == (1, 48000)


def test_usb_sound_card_detection():
    assert usb_sound_card_present(" 0 [ArduinoImolaHPH]: qcm2290 - Arduino-Imola-HPH-LOUT\n") is False
    assert usb_sound_card_present(" 1 [T530C]: USB-Audio - JBL Tune 530C\n") is True
    assert usb_sound_card_present(None) is None  # not Linux: unknown, so no warning


def test_needle_interpreter_falls_back_to_the_keyword_matcher(caplog):
    with caplog.at_level("WARNING"):
        interpreter = build_interpreter(VoiceConfig(interpreter="needle"), DEFAULT_COMMANDS)
    assert interpreter.interpret("clamp").word == "clamp"
    assert "needle" in caplog.text
    with pytest.raises(ValueError):
        build_interpreter(VoiceConfig(interpreter="magic"), DEFAULT_COMMANDS)


def test_command_vocabulary_decides_whether_the_recogniser_is_restricted(monkeypatch):
    import trainer.voice.vosk_recognizer as vosk_module

    seen = []

    class SpyRecognizer(FakeRecognizer):
        def __init__(self, model_dir, phrases, sample_rate):
            seen.append(phrases)

    monkeypatch.setattr(vosk_module, "VoskRecognizer", SpyRecognizer)
    build_recognizer(VoiceConfig(), ["clamp", "swab"])
    build_recognizer(VoiceConfig(command_vocabulary="open"), ["clamp", "swab"])
    assert seen == [["clamp", "swab"], None]
    with pytest.raises(ValueError):
        build_recognizer(VoiceConfig(command_vocabulary="huge"), [])
