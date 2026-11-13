"""One speech segment -> an older command or a nurse's treatment.

Two paths that never fire each other's words:

- The older commands (instruments, steady, light, pause, ...) stay on the
  Vosk grammar and the keyword matcher, exactly as before.
- The treatments of the vitals monitor (oxygen, anaesthesia, adrenaline) go
  through a sentence recogniser (Whistle) and a treatment interpreter
  (keywords first, then Needle).

Both recognisers hear the same segment. A short call with a command phrase
("Clamp!") is decided by the grammar at once and the sentence recogniser
never runs. A longer segment, or one the grammar did not catch, is
transcribed by Whistle at its end; if it holds a treatment, that wins (the
grammar forces any speech onto its nearest phrase, so its word for "he can't
breathe" means nothing), otherwise the grammar's result stands as before.

Needle only runs while the game expects an instruction (an alarm is open,
`expecting`): measured on the published rungs, it calls a tool for talk
about the patient ("his sats look good now") too. Outside an alarm only a
treatment named in so many words counts. Without a sentence recogniser the
treatment phrases join the grammar instead, so the game stays playable by
voice without any model (criterion T3).

Transcripts never leave this module and VoiceService.
"""
from __future__ import annotations

from dataclasses import dataclass

from .command_matcher import CommandMatcher
from .interpreter import CommandInterpreter
from .recognizer import SpeechRecognizer


@dataclass(frozen=True)
class Understood:
    kind: str  # "command" | "treatment" | "unclear" | "ignored"
    word: str = ""
    confidence: float = 0.0
    reason: str = ""  # for "unclear": "low_confidence" | "no_instruction"
    text: str = ""  # for the on-screen debug panel only
    sentence_ran: bool = False  # the sentence recogniser was used (for the energy numbers)


class CommandUnderstanding:
    def __init__(
        self,
        command_recognizer: SpeechRecognizer,
        command_interpreter: CommandInterpreter,
        confidence_threshold: float,
        treatments: dict[str, list[str]],
        sentence_recognizer: SpeechRecognizer | None = None,
        treatment_interpreter: CommandInterpreter | None = None,
        sentence_confidence_threshold: float = 0.5,
        short_segment_s: float = 1.2,
    ) -> None:
        self.command_recognizer = command_recognizer
        self.command_interpreter = command_interpreter
        self.confidence_threshold = confidence_threshold
        self.sentence_recognizer = sentence_recognizer
        self.treatment_phrases = CommandMatcher(treatments)
        self.treatment_interpreter = treatment_interpreter or self.treatment_phrases
        self.sentence_confidence_threshold = sentence_confidence_threshold
        self.short_segment_s = short_segment_s

    # --- audio -------------------------------------------------------------------

    def reset(self) -> None:
        self.command_recognizer.reset()
        if self.sentence_recognizer is not None:
            self.sentence_recognizer.reset()

    def accept(self, pcm_int16: bytes) -> None:
        self.command_recognizer.accept(pcm_int16)
        if self.sentence_recognizer is not None:
            self.sentence_recognizer.accept(pcm_int16)  # buffered only; transcribed at the end if needed

    def partial(self) -> str:
        return self.command_recognizer.partial()

    def unload(self) -> None:
        self.command_recognizer.unload()
        self.command_interpreter.unload()
        if self.sentence_recognizer is not None:
            self.sentence_recognizer.unload()
        self.treatment_interpreter.unload()

    # --- decision ------------------------------------------------------------------

    def finish(self, duration_s: float, expecting: bool) -> Understood:
        """Decide the segment that just ended. `expecting`: the game waits for a
        treatment (an alarm is open)."""
        heard = self.command_recognizer.finish()
        match = self.command_interpreter.interpret(heard.text)
        confidence = 0.0
        if match is not None:
            confidence = min(match.score, heard.confidence if heard.confidence > 0 else match.score)
        command = Understood("command", match.word, confidence, text=heard.text) if match else None
        sure = command is not None and match.score == 1.0 and confidence >= self.confidence_threshold
        if self.sentence_recognizer is None or (sure and duration_s <= self.short_segment_s):
            if self.sentence_recognizer is not None:
                self.sentence_recognizer.reset()
            return self._grammar_only(command, heard.text)

        sentence = self.sentence_recognizer.finish()
        text = sentence.text.strip()
        treatment = self._treatment(text, expecting) if sentence.confidence >= self.sentence_confidence_threshold else None
        if treatment is not None:
            return Understood("treatment", treatment[0], treatment[1], text=text, sentence_ran=True)
        if sure:
            return Understood("command", match.word, confidence, text=heard.text, sentence_ran=True)
        if expecting and text:
            return Understood("unclear", reason="no_instruction", text=text, sentence_ran=True)
        result = self._grammar_only(command, heard.text)
        return Understood(result.kind, result.word, result.confidence, result.reason, result.text, sentence_ran=True)

    def _grammar_only(self, command: Understood | None, text: str) -> Understood:
        """The behaviour without a sentence path: the grammar's word, "Pardon?" if unsure."""
        if command is None:
            return Understood("ignored", text=text)
        if command.confidence < self.confidence_threshold:
            return Understood("unclear", command.word, command.confidence, reason="low_confidence", text=text)
        return command

    def _treatment(self, text: str, expecting: bool) -> tuple[str, float] | None:
        if not text:
            return None
        named = self.treatment_phrases.interpret(text)
        if named is not None and named.score == 1.0:
            return named.word, 1.0
        if not expecting:
            return None  # outside an alarm only a treatment said in so many words counts
        hit = self.treatment_interpreter.interpret(text)
        return (hit.word, hit.score) if hit is not None else None
