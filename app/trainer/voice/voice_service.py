"""Runs the speech pipeline in its own thread and publishes commands.

mic -> SignalProcessor -> EnergyVad/Segmenter -> SpeechRecognizer -> CommandInterpreter

While a quiz question is open (QuestionAsked .. QuestionClosed) a segment is
an answer instead: it goes to the answer recogniser (whole sentences) and the
AnswerEvaluator, and only the verdict is published.

Listening only while the game asks for it (ListenRequest), never while the
patient speaks (PlaybackStarted/Finished). The microphone stream is stopped
entirely while not listening, so idle costs no CPU. Audio stays in memory,
and transcripts never leave this service.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque

from ..core.config import VoiceConfig
from ..core.events import (
    AnswerEvent,
    AsrDebugEvent,
    CommandEvent,
    ListenRequest,
    MisheardEvent,
    PlaybackFinished,
    PlaybackStarted,
    QuestionAsked,
    QuestionClosed,
    VoiceState,
    VoiceStateChanged,
)
from ..core.service import Service
from ..quiz.evaluator import AnswerEvaluator, KeywordEvaluator
from ..quiz.question import Question, QuestionBank
from .audio_input import AudioInput
from .command_matcher import CommandMatcher
from .interpreter import CommandInterpreter
from .recognizer import NullRecognizer, SpeechRecognizer
from .signal_processor import SignalProcessor
from .vad import EnergyVad, Segmenter, VoiceActivityDetector

log = logging.getLogger(__name__)

# Commands that still work while a question is open, if they are all that was said.
ANSWER_CONTROLS = ("repeat", "pause", "help")


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
        interpreter: CommandInterpreter | None = None,
        questions: QuestionBank | None = None,
        answer_recognizer: SpeechRecognizer | None = None,
        evaluator: AnswerEvaluator | None = None,
    ) -> None:
        super().__init__(bus)
        self.cfg = cfg
        self.interpreter = interpreter or CommandMatcher(commands)
        self.recognizer = recognizer or NullRecognizer()
        self.questions = questions or QuestionBank()
        self.answer_recognizer = answer_recognizer or NullRecognizer()
        self.evaluator = evaluator or KeywordEvaluator()
        self._question: Question | None = None
        self.audio = audio or AudioInput(cfg.sample_rate, cfg.block_ms, cfg.input_device)
        self.dsp = SignalProcessor(cfg.sample_rate, cfg.highpass_hz, cfg.agc_target_rms, cfg.agc_max_gain)
        self.vad = vad or EnergyVad(cfg.vad_ratio, cfg.vad_min_rms)
        blocks_per_s = 1000 / cfg.block_ms
        self.segmenter = Segmenter(
            start_blocks=max(1, round(cfg.vad_start_ms / cfg.block_ms)),
            hangover_blocks=max(1, round(cfg.vad_hangover_ms / cfg.block_ms)),
            max_blocks=int(cfg.max_segment_s * blocks_per_s),
        )
        # Answers are sentences: allow pauses in them, and more length.
        self.answer_segmenter = Segmenter(
            start_blocks=self.segmenter.start_blocks,
            hangover_blocks=max(1, round(cfg.answer_hangover_ms / cfg.block_ms)),
            max_blocks=int(cfg.answer_max_segment_s * blocks_per_s),
        )
        self._listen_wanted = False
        self._speaking = False
        self._state = VoiceState.OFF
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.segments = 0
        self._partial_blocks = 0
        self._last_partial = ""
        self._preroll: deque[bytes] = deque(maxlen=max(1, round(cfg.vad_preroll_ms / cfg.block_ms)))
        bus.subscribe(ListenRequest, self._on_listen)
        bus.subscribe(QuestionAsked, self._on_question)
        bus.subscribe(QuestionClosed, lambda e: self._set_question(None))
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
        self.answer_recognizer.unload()
        self.interpreter.unload()
        self.evaluator.unload()

    # --- control -------------------------------------------------------------

    def _on_listen(self, ev: ListenRequest) -> None:
        with self._lock:
            self._listen_wanted = ev.on
        self._publish_state()

    def _on_question(self, ev: QuestionAsked) -> None:
        question = self.questions.get(ev.question_id)
        if question is None:
            log.warning("unknown question id %s", ev.question_id)
        self._set_question(question)

    def _set_question(self, question: Question | None) -> None:
        with self._lock:
            self._question = question

    def _open_question(self) -> Question | None:
        with self._lock:
            return self._question

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
        question: Question | None = None  # what the running segment answers
        while not self._stop.is_set():
            wanted = self._should_listen()
            if wanted and not self.audio.running:
                try:
                    self.audio.start()
                    self.vad.reset()
                    self.segmenter.reset()
                    self.answer_segmenter.reset()
                    self.recognizer.reset()
                    self.answer_recognizer.reset()
                    self._preroll.clear()
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
                    self.answer_recognizer.reset()
            if not self.audio.running:
                time.sleep(0.05)
                continue

            block = self.audio.read(timeout=0.1)
            if block is None:
                continue
            filtered, x = self.dsp.split(block)
            speech = self.vad.is_speech(filtered)
            if not in_segment:
                # A segment is a command or an answer from its first block to its last.
                now_open = self._open_question()
                if (now_open is None) != (question is None):
                    self.segmenter.reset()
                    self.answer_segmenter.reset()
                question = now_open
            segmenter = self.answer_segmenter if question is not None else self.segmenter
            recognizer = self.answer_recognizer if question is not None else self.recognizer
            phase = segmenter.update(speech)
            pcm = self.dsp.to_int16(x)
            if phase == "start":
                in_segment = True
                recognizer.reset()
                self._partial_blocks = 0
                self._last_partial = ""
                # replay the word onset that passed while the VAD made up its mind
                for chunk in self._preroll:
                    recognizer.accept(chunk)
                self._preroll.clear()
                recognizer.accept(pcm)
                self._publish_state(processing=True)
            elif phase == "continue":
                recognizer.accept(pcm)
                self._publish_partial(recognizer)
            elif phase == "idle":
                self._preroll.append(pcm)
            if phase == "end" and in_segment:
                in_segment = False
                speech_end_t = time.monotonic()
                self.segments += 1
                if question is not None:
                    self.handle_answer(question, speech_end_t)
                else:
                    self.handle_segment(speech_end_t)
                self._publish_state(processing=False)

    def handle_segment(self, speech_end_t: float) -> None:
        """Finish recognition for the segment and publish the outcome."""
        transcript = self.recognizer.finish()
        match = self.interpreter.interpret(transcript.text)
        if match is None:
            # Noise, other people talking, or words that resemble no command:
            # ignored silently, so the game never interrupts a conversation.
            # "Pardon?" is reserved for a command heard with low confidence.
            log.debug("segment without a command (text length %d)", len(transcript.text))
            self._debug_asr(transcript.text, transcript.confidence, "no_match" if transcript.text else "empty")
            return
        confidence = min(match.score, transcript.confidence if transcript.confidence > 0 else match.score)
        if confidence < self.cfg.confidence_threshold:
            self.bus.publish(MisheardEvent(reason="low_confidence", speech_end_t=speech_end_t))
            self._debug_asr(transcript.text, confidence, "low_confidence", match.word)
            return
        log.info("command %s (%.2f)", match.word, confidence)
        self.bus.publish(CommandEvent(word=match.word, confidence=confidence, speech_end_t=speech_end_t))
        self._debug_asr(transcript.text, confidence, "command", match.word)

    def handle_answer(self, question: Question, speech_end_t: float) -> None:
        """Finish recognition of a spoken answer and publish the verdict only."""
        transcript = self.answer_recognizer.finish()
        text = transcript.text.strip()
        if not text:
            self._debug_asr("", 0.0, "empty")
            return
        if self._open_question() is not question:
            # The window closed while the player was still speaking.
            self._debug_asr(text, transcript.confidence, "too_late")
            return
        if len(text.split()) <= 2:
            control = self.interpreter.interpret(text, ANSWER_CONTROLS)
            if control is not None and control.score == 1.0:
                self.bus.publish(CommandEvent(word=control.word, confidence=1.0, speech_end_t=speech_end_t))
                self._debug_asr(text, transcript.confidence, "command", control.word)
                return
        verdict = self.evaluator.evaluate(question, text)
        confident = transcript.confidence >= self.cfg.answer_confidence_threshold
        if verdict.choice is None and not confident:
            # Noise or someone else talking: do not use up the player's second try.
            self._debug_asr(text, transcript.confidence, "no_match")
            return
        if verdict.choice is None or not confident:
            self.bus.publish(AnswerEvent(question_id=question.id, unclear=True, confidence=transcript.confidence, speech_end_t=speech_end_t))
            self._debug_asr(text, transcript.confidence, "unclear", verdict.choice or "")
            return
        correct = verdict.choice == question.correct
        log.info("answer to %s: %s", question.id, "correct" if correct else "wrong")
        self.bus.publish(AnswerEvent(question_id=question.id, correct=correct, confidence=transcript.confidence, speech_end_t=speech_end_t))
        self._debug_asr(text, transcript.confidence, "answer_correct" if correct else "answer_wrong", verdict.choice)

    # --- ASR debug panel (voice.debug_asr) -----------------------------------

    def _publish_partial(self, recognizer: SpeechRecognizer) -> None:
        """Every 5th block (100 ms), show the engine's running guess."""
        if not self.cfg.debug_asr:
            return
        self._partial_blocks += 1
        if self._partial_blocks % 5:
            return
        text = recognizer.partial()
        if text != self._last_partial:
            self._last_partial = text
            self._debug_asr(text, 0.0, "partial")

    def _debug_asr(self, text: str, confidence: float, outcome: str, word: str = "") -> None:
        if self.cfg.debug_asr:
            self.bus.publish(AsrDebugEvent(text=text, confidence=confidence, outcome=outcome, word=word))


def build_interpreter(cfg: VoiceConfig, commands: dict[str, list[str]]) -> CommandInterpreter:
    """Pick the transcript -> command step from the config."""
    if cfg.interpreter == "keyword":
        return CommandMatcher(commands)
    if cfg.interpreter == "needle":
        # Not built yet: docs/needle-integration.md says where it goes.
        log.warning("voice.interpreter = needle is not available yet; using the keyword matcher")
        return CommandMatcher(commands)
    raise ValueError(f"unknown interpreter: {cfg.interpreter}")


def build_evaluator(cfg: VoiceConfig) -> AnswerEvaluator:
    """Pick the answer -> option step from the config."""
    if cfg.evaluator == "keyword":
        return KeywordEvaluator()
    if cfg.evaluator == "needle":
        # Not built yet: docs/needle-integration.md says where it goes.
        log.warning("voice.evaluator = needle is not available yet; using the keyword evaluator")
        return KeywordEvaluator()
    raise ValueError(f"unknown evaluator: {cfg.evaluator}")


def build_answer_recognizer(cfg: VoiceConfig, questions: QuestionBank) -> SpeechRecognizer:
    """The recogniser for spoken quiz answers. It shares the model with the
    command recogniser, so it adds no second model to memory."""
    if cfg.answer_vocabulary not in ("open", "keywords"):
        raise ValueError(f"unknown answer_vocabulary: {cfg.answer_vocabulary}")
    if cfg.recognizer == "vosk" and len(questions):
        try:
            from .vosk_recognizer import VoskRecognizer

            vocabulary = questions.keywords() if cfg.answer_vocabulary == "keywords" else None
            return VoskRecognizer(cfg.model_dir, vocabulary, cfg.sample_rate)
        except Exception as exc:
            log.error("Vosk unavailable (%s); spoken answers disabled", exc)
    return NullRecognizer()


def build_recognizer(cfg: VoiceConfig, phrases: list[str]) -> SpeechRecognizer:
    """Pick the engine from the config; fall back to NullRecognizer with a clear log line.

    `phrases` restricts the vocabulary unless `voice.command_vocabulary` is "open"."""
    if cfg.command_vocabulary not in ("restricted", "open"):
        raise ValueError(f"unknown command_vocabulary: {cfg.command_vocabulary}")
    if cfg.recognizer == "vosk":
        try:
            from .vosk_recognizer import VoskRecognizer

            vocabulary = phrases if cfg.command_vocabulary == "restricted" else None
            return VoskRecognizer(cfg.model_dir, vocabulary, cfg.sample_rate)
        except Exception as exc:
            log.error("Vosk unavailable (%s); voice commands disabled, keyboard still works", exc)
            return NullRecognizer()
    if cfg.recognizer == "null":
        return NullRecognizer()
    raise ValueError(f"unknown recognizer: {cfg.recognizer}")
