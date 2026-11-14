"""Runs the speech pipeline in its own thread and publishes commands.

mic -> SignalProcessor -> EnergyVad/Segmenter -> CommandUnderstanding
                                                 (Vosk grammar for the older commands,
                                                  Whistle + Needle for the nurse's treatments)

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
    InstructionWindow,
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
from .interpreter import CommandInterpreter, OrderInterpreter
from .recognizer import EnsembleRecognizer, NullRecognizer, SpeechRecognizer
from .signal_processor import SignalProcessor
from .understanding import CommandUnderstanding, Understood
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
        treatments: dict[str, list[str]] | None = None,
        sentence_recognizer: SpeechRecognizer | None = None,
        treatment_interpreter: OrderInterpreter | None = None,
    ) -> None:
        super().__init__(bus)
        self.cfg = cfg
        self.interpreter = interpreter or CommandMatcher(commands)
        self.recognizer = recognizer or NullRecognizer()
        self.understanding = CommandUnderstanding(
            self.recognizer,
            self.interpreter,
            cfg.confidence_threshold,
            treatments or {},
            sentence_recognizer,
            treatment_interpreter,
            cfg.sentence_confidence_threshold,
            cfg.short_segment_s,
        )
        self._expecting = False
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
            long_after_blocks=int(cfg.short_segment_s * blocks_per_s),
            long_hangover_blocks=max(1, round(cfg.long_hangover_ms / cfg.block_ms)),
            long_max_blocks=int(cfg.long_max_segment_s * blocks_per_s),
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
        bus.subscribe(InstructionWindow, self._on_instruction_window)
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
        self.understanding.unload()
        self.answer_recognizer.unload()
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

    def _on_instruction_window(self, ev: InstructionWindow) -> None:
        with self._lock:
            self._expecting = ev.open

    def _expecting_instruction(self) -> bool:
        with self._lock:
            return self._expecting

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
                    self.understanding.reset()
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
                    self.understanding.reset()
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
                if now_open is not question:
                    self.segmenter.reset()
                    self.answer_segmenter.reset()
                    if now_open is not None:
                        self.answer_recognizer.set_vocabulary(now_open.keywords())
                        self.evaluator.prepare(now_open)
                question = now_open
            segmenter = self.answer_segmenter if question is not None else self.segmenter
            recognizer = self.answer_recognizer if question is not None else self.understanding
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
                    self.handle_segment(speech_end_t, segmenter.last_length * self.cfg.block_ms / 1000.0)
                self._publish_state(processing=False)

    def handle_segment(self, speech_end_t: float, duration_s: float = 0.0) -> None:
        """Decide the segment and publish the outcome (never the words)."""
        u: Understood = self.understanding.finish(duration_s, self._expecting_instruction())
        if u.kind == "treatment":
            for order in u.orders:
                amount = "standard dose" if order.amount is None else f"{order.amount:g}"
                log.info("order %s %s (%.2f)", order.word, amount, order.score)
                self.bus.publish(CommandEvent(word=order.word, confidence=order.score, amount=order.amount, speech_end_t=speech_end_t))
            self._debug_asr(u.text, u.confidence, u.kind, " + ".join(o.word for o in u.orders))
        elif u.kind == "command":
            log.info("command %s (%.2f)", u.word, u.confidence)
            self.bus.publish(CommandEvent(word=u.word, confidence=u.confidence, speech_end_t=speech_end_t))
            self._debug_asr(u.text, u.confidence, u.kind, u.word)
        elif u.kind == "unclear":
            # "Pardon?" for a command heard with low confidence, and "Pardon, doctor?"
            # for a sentence without a treatment while the nurse waits for one.
            self.bus.publish(MisheardEvent(reason=u.reason, speech_end_t=speech_end_t))
            self._debug_asr(u.text, u.confidence, u.reason, u.word)
        else:
            # Noise, other people talking, or words that resemble no command:
            # ignored silently, so the game never interrupts a conversation.
            log.debug("segment without a command (text length %d)", len(u.text))
            self._debug_asr(u.text, u.confidence, "no_match" if u.text else "empty")

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
    """The transcript -> command step for the older commands: the phrase matcher.
    (Needle serves the treatments only: build_treatment_interpreter.)"""
    if cfg.interpreter == "keyword":
        return CommandMatcher(commands)
    raise ValueError(f"unknown interpreter: {cfg.interpreter} (Needle decides treatments only: voice.treatment_interpreter)")


def build_sentence_recognizer(cfg: VoiceConfig, treatments: dict[str, list[str]]) -> SpeechRecognizer | None:
    """The recogniser that hears sentences for the treatments, or None (then the
    treatment phrases belong in the command grammar, see command_phrases)."""
    if cfg.sentence_recognizer == "none" or cfg.recognizer == "null":
        return None
    if cfg.sentence_recognizer == "whistle":
        from ..game.actions import ORDER_WORDS

        try:
            return _whistle(cfg, sorted({p for phrases in treatments.values() for p in phrases} | set(ORDER_WORDS)))
        except Exception as exc:
            log.error("Whistle unavailable (%s); treatments by their names through the command grammar", exc)
            return None
    if cfg.sentence_recognizer == "vosk":
        try:
            from .vosk_recognizer import VoskRecognizer

            return VoskRecognizer(cfg.model_dir, None, cfg.sample_rate)
        except Exception as exc:
            log.error("Vosk (open vocabulary) unavailable (%s); treatments through the command grammar", exc)
            return None
    raise ValueError(f"unknown sentence_recognizer: {cfg.sentence_recognizer}")


def build_treatment_interpreter(cfg: VoiceConfig, treatments: dict[str, list[str]]) -> OrderInterpreter:
    """Sentence -> orders: the drug names (standard doses), or Needle, which also reads the amount."""
    from .named_orders import NamedOrders

    if cfg.treatment_interpreter == "keyword":
        return NamedOrders(treatments)
    if cfg.treatment_interpreter == "needle":
        try:
            from ..cactus_models.needle_orders import NeedleOrders

            return NeedleOrders(treatments, cfg.needle_weights, min_confidence=cfg.needle_min_confidence, require_trigger=cfg.needle_require_trigger)
        except Exception as exc:
            log.error("Needle unavailable (%s); orders by drug name only, at the standard dose", exc)
            return NamedOrders(treatments)
    raise ValueError(f"unknown treatment_interpreter: {cfg.treatment_interpreter}")


def command_phrases(commands: dict[str, list[str]], treatments: dict[str, list[str]], sentence_path: bool) -> dict[str, list[str]]:
    """What the Vosk grammar listens for. With a sentence path the treatments
    are not in it, so neither path fires the other's words; without one they
    are, so the treatments still work by voice without any model (T3)."""
    return dict(commands) if sentence_path else {**commands, **treatments}


def build_evaluator(cfg: VoiceConfig) -> AnswerEvaluator:
    """Pick the answer -> option step from the config."""
    if cfg.evaluator == "keyword":
        return KeywordEvaluator()
    if cfg.evaluator == "needle":
        try:
            from ..cactus_models.needle_evaluator import NeedleEvaluator

            return NeedleEvaluator(cfg.needle_weights, cfg.needle_min_confidence)
        except Exception as exc:
            log.error("Needle unavailable (%s); using the keyword evaluator", exc)
            return KeywordEvaluator()
    raise ValueError(f"unknown evaluator: {cfg.evaluator}")


def _whistle(cfg: VoiceConfig, keywords: list[str]) -> SpeechRecognizer:
    from ..cactus_models.whistle_recognizer import WhistleRecognizer

    return WhistleRecognizer(cfg.whistle_weights, cfg.whistle_language, keywords, cfg.sample_rate)


def build_answer_recognizer(cfg: VoiceConfig, questions: QuestionBank) -> SpeechRecognizer:
    """The recogniser for spoken quiz answers. The Vosk members share the
    model with the command recogniser, so they add no second model to memory.
    A member that cannot be built is left out with a log line."""
    if cfg.answer_vocabulary not in ("both", "open", "keywords"):
        raise ValueError(f"unknown answer_vocabulary: {cfg.answer_vocabulary}")
    if cfg.answer_engine not in ("vosk", "whistle"):
        raise ValueError(f"unknown answer_engine: {cfg.answer_engine}")
    if cfg.recognizer == "null" or not len(questions):
        return NullRecognizer()

    def vosk(phrases: list[str] | None) -> SpeechRecognizer:
        from .vosk_recognizer import VoskRecognizer

        return VoskRecognizer(cfg.model_dir, phrases, cfg.sample_rate)

    wanted = []
    if cfg.answer_vocabulary in ("both", "open"):
        if cfg.answer_engine == "whistle":
            wanted.append(("Whistle", lambda: _whistle(cfg, questions.keywords())))
        else:
            wanted.append(("Vosk (open vocabulary)", lambda: vosk(None)))
    if cfg.answer_vocabulary in ("both", "keywords"):
        # narrowed to the open question's options when it is asked
        wanted.append(("Vosk (answer phrases)", lambda: vosk(questions.keywords())))
    members = []
    for name, build in wanted:
        try:
            members.append(build())
        except Exception as exc:
            log.error("%s unavailable for spoken answers (%s)", name, exc)
    if not members:
        return NullRecognizer()
    return members[0] if len(members) == 1 else EnsembleRecognizer(members)


def build_recognizer(cfg: VoiceConfig, phrases: list[str]) -> SpeechRecognizer:
    """The recogniser for the older commands: Vosk. Falls back to
    NullRecognizer with a clear log line.

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
    raise ValueError(f"unknown recognizer: {cfg.recognizer} (the older commands stay on Vosk)")
