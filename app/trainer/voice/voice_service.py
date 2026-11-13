"""Runs the speech pipeline in its own thread and publishes commands.

mic -> SignalProcessor -> EnergyVad/Segmenter -> SpeechRecognizer -> CommandMatcher

Listening only while the game asks for it (ListenRequest), never while the
patient speaks (PlaybackStarted/Finished). The microphone stream is stopped
entirely while not listening, so idle costs no CPU. Audio stays in memory.
"""
from __future__ import annotations

import logging
import threading
import time

from ..core.config import VoiceConfig
from ..core.events import (
    CommandEvent,
    ListenRequest,
    MisheardEvent,
    PlaybackFinished,
    PlaybackStarted,
    VoiceState,
    VoiceStateChanged,
)
from ..core.service import Service
from .audio_input import AudioInput
from .command_matcher import CommandMatcher
from .recognizer import NullRecognizer, SpeechRecognizer
from .signal_processor import SignalProcessor
from .vad import EnergyVad, Segmenter, VoiceActivityDetector

log = logging.getLogger(__name__)


class VoiceService(Service):
    name = "voice"

    def __init__(
        self,
        bus,
        cfg: VoiceConfig,
        commands: dict[str, list[str]],
        recognizer: SpeechRecognizer | None = None,
        audio: AudioInput | None = None,
        vad: VoiceActivityDetector | None = None,
    ) -> None:
        super().__init__(bus)
        self.cfg = cfg
        self.matcher = CommandMatcher(commands)
        self.recognizer = recognizer or NullRecognizer()
        self.audio = audio or AudioInput(cfg.sample_rate, cfg.block_ms, cfg.input_device)
        self.dsp = SignalProcessor(cfg.sample_rate, cfg.highpass_hz, cfg.agc_target_rms, cfg.agc_max_gain)
        self.vad = vad or EnergyVad(cfg.vad_ratio, cfg.vad_min_rms)
        blocks_per_s = 1000 / cfg.block_ms
        self.segmenter = Segmenter(
            start_blocks=max(1, round(cfg.vad_start_ms / cfg.block_ms)),
            hangover_blocks=max(1, round(cfg.vad_hangover_ms / cfg.block_ms)),
            max_blocks=int(cfg.max_segment_s * blocks_per_s),
        )
        self._listen_wanted = False
        self._speaking = False
        self._state = VoiceState.OFF
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.segments = 0
        bus.subscribe(ListenRequest, self._on_listen)
        bus.subscribe(PlaybackStarted, lambda e: self._set_speaking(True))
        bus.subscribe(PlaybackFinished, lambda e: self._set_speaking(False))

    # --- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="voice", daemon=True)
        self._thread.start()
        self._publish_state()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._safe_audio_stop()
        self.recognizer.unload()

    # --- control -------------------------------------------------------------

    def _on_listen(self, ev: ListenRequest) -> None:
        with self._lock:
            self._listen_wanted = ev.on
        self._publish_state()

    def _set_speaking(self, speaking: bool) -> None:
        with self._lock:
            self._speaking = speaking
        self._publish_state()

    def _should_listen(self) -> bool:
        with self._lock:
            return self._listen_wanted and not self._speaking

    def _publish_state(self, processing: bool = False) -> None:
        with self._lock:
            if not self._listen_wanted:
                state = VoiceState.OFF
            elif self._speaking:
                state = VoiceState.SPEAKING
            elif processing:
                state = VoiceState.PROCESSING
            else:
                state = VoiceState.LISTENING
        if state != self._state:
            self._state = state
            self.bus.publish(VoiceStateChanged(state=state))

    @property
    def state(self) -> VoiceState:
        return self._state

    # --- pipeline ------------------------------------------------------------

    def _safe_audio_stop(self) -> None:
        try:
            self.audio.stop()
        except Exception:
            log.exception("stopping audio failed")

    def _run(self) -> None:
        in_segment = False
        speech_end_t = None
        while not self._stop.is_set():
            wanted = self._should_listen()
            if wanted and not self.audio.running:
                try:
                    self.audio.start()
                    self.vad.reset()
                    self.segmenter.reset()
                    self.recognizer.reset()
                    in_segment = False
                except Exception as exc:
                    log.error("microphone unavailable: %s", exc)
                    with self._lock:
                        self._listen_wanted = False
                    self._publish_state()
                    time.sleep(1.0)
                    continue
            elif not wanted and self.audio.running:
                self._safe_audio_stop()
                if in_segment:
                    in_segment = False
                    self.recognizer.reset()
            if not self.audio.running:
                time.sleep(0.05)
                continue

            block = self.audio.read(timeout=0.1)
            if block is None:
                continue
            filtered, x = self.dsp.split(block)
            speech = self.vad.is_speech(filtered)
            phase = self.segmenter.update(speech)
            if phase == "start":
                in_segment = True
                self.recognizer.reset()
                self.recognizer.accept(self.dsp.to_int16(x))
                self._publish_state(processing=True)
            elif phase == "continue":
                self.recognizer.accept(self.dsp.to_int16(x))
            elif phase == "end" and in_segment:
                in_segment = False
                speech_end_t = time.monotonic()
                self.segments += 1
                self.handle_segment(speech_end_t)
                self._publish_state(processing=False)

    def handle_segment(self, speech_end_t: float) -> None:
        """Finish recognition for the segment and publish the outcome."""
        transcript = self.recognizer.finish()
        match = self.matcher.match(transcript.text)
        if match is None:
            # Noise, other people talking, or words that resemble no command:
            # ignored silently, so the game never interrupts a conversation.
            # "Pardon?" is reserved for a command heard with low confidence.
            log.debug("segment without a command (text length %d)", len(transcript.text))
            return
        confidence = min(match.score, transcript.confidence if transcript.confidence > 0 else match.score)
        if confidence < self.cfg.confidence_threshold:
            self.bus.publish(MisheardEvent(reason="low_confidence", speech_end_t=speech_end_t))
            return
        log.info("command %s (%.2f)", match.word, confidence)
        self.bus.publish(CommandEvent(word=match.word, confidence=confidence, speech_end_t=speech_end_t))


def build_recognizer(cfg: VoiceConfig, matcher_phrases: list[str]) -> SpeechRecognizer:
    """Pick the engine from the config; fall back to NullRecognizer with a clear log line."""
    if cfg.recognizer == "vosk":
        try:
            from .vosk_recognizer import VoskRecognizer

            return VoskRecognizer(cfg.model_dir, matcher_phrases, cfg.sample_rate)
        except Exception as exc:
            log.error("Vosk unavailable (%s); voice commands disabled, keyboard still works", exc)
            return NullRecognizer()
    if cfg.recognizer == "null":
        return NullRecognizer()
    raise ValueError(f"unknown recognizer: {cfg.recognizer}")
