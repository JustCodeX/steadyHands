"""The game: state machine, movement, collisions, targets, commands."""
from __future__ import annotations

import logging
import math
import random
import time

from ..core.config import TOOL_WORDS, TREATMENT_WORDS, GameConfig, QuizConfig, VitalsConfig
from ..core.events import (
    AnswerEvent,
    CommandEvent,
    GameEvent,
    GameSnapshot,
    GameState,
    IdleChanged,
    InputFrame,
    InstructionWindow,
    ListenRequest,
    McuStatus,
    MisheardEvent,
    PlaybackFinished,
    PlaybackStarted,
    QuestionAsked,
    QuestionClosed,
    RoundResult,
    TargetView,
    VitalView,
)
from ..quiz.question import QuestionBank
from ..core.service import Service
from . import instruments
from .level import Level, LevelCatalog
from .metrics import TrainingMetrics
from .modes import CoopMode, GameMode, SoloMode
from .patient import Patient
from .quiz_director import QuizDirector, QuizOutcome, QuizStep
from .stress import Stress
from .vitals import SPECS, TreatmentResult, VitalsMonitor

log = logging.getLogger(__name__)


class GameEngine(Service):
    name = "game"

    def __init__(
        self,
        bus,
        cfg: GameConfig,
        levels: LevelCatalog,
        width: int = 1024,
        height: int = 600,
        quiz_cfg: QuizConfig | None = None,
        questions: QuestionBank | None = None,
        vitals_cfg: VitalsConfig | None = None,
        rng: random.Random | None = None,
    ) -> None:
        super().__init__(bus)
        self.cfg = cfg
        self.quiz_cfg = quiz_cfg or QuizConfig()
        self.quiz = QuizDirector(self.quiz_cfg, questions)  # without questions it never asks
        self.stress = Stress(self.quiz_cfg)
        self.vitals_cfg = vitals_cfg or VitalsConfig()
        self.vitals = VitalsMonitor(self.vitals_cfg, rng)
        self._patient_speaking = False
        self.levels = levels
        self.width = width
        self.height = height

        self.state = GameState.MENU
        self.mode: GameMode = SoloMode()
        self.level: Level | None = None
        self.patient = Patient(cfg.heart_rate_base, cfg.heart_rate_per_contact, cfg.heart_rate_decay_per_s)
        self.metrics = TrainingMetrics()
        self.tool = instruments.make("forceps")
        self.previous_tool: str | None = None

        self.x = 0.0
        self.y = 0.0
        self.sensitivity = 1.0
        self.time_left = 0.0
        self.last_command = ""
        self.message = ""
        self._message_until = 0.0
        self.steady_until = 0.0
        self.light_until = 0.0
        self._last_contact_t = -1e9
        self._dwell_target: str | None = None
        self._dwell_elapsed = 0.0
        self._result: RoundResult | None = None
        self._result_t = 0.0
        self._misses = 0
        self._prev_buttons = 0
        self._prev_knob: int | None = None
        self._last_frame: InputFrame | None = None
        self._frame_count = 0
        self._menu_index = 0
        self._mcu_connected = False
        self._listening = False
        self._instruction_open = False
        self._instruction_misses = 0

        bus.subscribe(InputFrame, self.on_input)
        bus.subscribe(CommandEvent, self.on_command)
        bus.subscribe(MisheardEvent, self.on_misheard)
        bus.subscribe(IdleChanged, self.on_idle)
        bus.subscribe(McuStatus, self._on_mcu_status)
        bus.subscribe(AnswerEvent, self.on_answer)
        bus.subscribe(PlaybackStarted, lambda e: self._set_patient_speaking(True))
        bus.subscribe(PlaybackFinished, lambda e: self._set_patient_speaking(False))

    # --- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        self.enter_menu()

    def tick(self, dt: float) -> None:
        now = time.monotonic()
        if self.state is GameState.PLAYING:
            self._update_round(dt, now)
        elif self.state is GameState.RESULT and now - self._result_t > self.cfg.result_show_s:
            self.enter_menu()
        self.mode.expire(now)
        if now > self._message_until:
            self.message = ""
        self.bus.publish(self.snapshot())

    # --- state changes -------------------------------------------------------

    def _set_instruction_window(self, open_: bool) -> None:
        """Tell the voice service whether the nurse waits for a treatment."""
        if open_ != self._instruction_open:
            self._instruction_open = open_
            self._instruction_misses = 0
            self.bus.publish(InstructionWindow(open=open_))

    def _set_listening(self, on: bool) -> None:
        if on != self._listening:
            self._listening = on
            self.bus.publish(ListenRequest(on=on))

    def enter_menu(self) -> None:
        self.state = GameState.MENU
        self._result = None
        self._set_listening(True)  # "new game" and "help" work in the menu
        self.bus.publish(GameEvent(kind="menu"))

    def start_round(self, level_index: int | None = None) -> None:
        if level_index is not None:
            self._menu_index = level_index
        try:
            self.level = self.levels.load(self._menu_index)
        except (FileNotFoundError, OSError, KeyError, ValueError) as exc:
            log.error("cannot load level %d: %s", self._menu_index, exc)
            self.say("No level found", 3)
            return
        self.level.reset()
        self.x, self.y = float(self.level.start[0]), float(self.level.start[1])
        self.patient.reset()
        self.metrics.start()
        self.mode.reset("forceps")
        self.stress.reset()
        if self.quiz.abandon():  # "new game" while a question was open
            self.bus.publish(QuestionClosed())
        count = self.level.quiz_count if self.level.quiz_count is not None else self.quiz_cfg.questions_per_round
        self.quiz.reset(count, self.level.quiz_topics)
        self.vitals.reset(self.level.vitals_episodes, self.level.vitals_kinds)
        self.tool = instruments.make("forceps")
        self.previous_tool = None
        self.time_left = self.level.time_limit_s
        self.steady_until = self.light_until = 0.0
        self._dwell_target = None
        self._misses = 0
        self.last_command = ""
        self.state = GameState.PLAYING
        self._set_listening(True)
        self.bus.publish(GameEvent(kind="round_started", detail=self.tool.word))
        log.info("round started: %s (%s)", self.level.name, self.mode.name)

    def end_round(self, won: bool) -> None:
        assert self.level is not None
        if self.quiz.abandon():
            self.bus.publish(QuestionClosed())
        self._set_instruction_window(False)
        self.metrics.end()
        self.metrics.contacts = self.patient.contacts
        self.metrics.questions_correct = self.quiz.correct
        self.metrics.questions_wrong = self.quiz.wrong
        self.metrics.treatments_correct = self.vitals.correct
        self.metrics.treatments_wrong = self.vitals.wrong
        self.metrics.crises = self.patient.crises
        self._result = self.metrics.result(self.level.name, won)
        self._result_t = time.monotonic()
        self.state = GameState.RESULT
        if won:  # the menu comes back with the next level selected
            self._menu_index = (self._menu_index + 1) % max(1, len(self.levels.names()))
        self._set_listening(True)
        self.bus.publish(GameEvent(kind="win" if won else "lose"))
        self.bus.publish(self._result)
        log.info("round over: %s", self._result)

    def pause(self) -> None:
        if self.state is GameState.PLAYING:
            self.state = GameState.PAUSED
            self.bus.publish(GameEvent(kind="paused"))

    def resume(self) -> None:
        if self.state is GameState.PAUSED:
            self.state = GameState.PLAYING
            self.bus.publish(GameEvent(kind="resumed"))

    def toggle_mode(self) -> None:
        self.mode = SoloMode() if isinstance(self.mode, CoopMode) else CoopMode(self.cfg.coop_callback_window_s)
        self.say(f"Mode: {self.mode.name}", 2)

    def on_idle(self, ev: IdleChanged) -> None:
        if ev.idle and self.state in (GameState.MENU, GameState.RESULT):
            self.state = GameState.IDLE
            self._set_listening(False)
        elif not ev.idle and self.state is GameState.IDLE:
            self.enter_menu()

    def _on_mcu_status(self, ev: McuStatus) -> None:
        self._mcu_connected = ev.connected

    def say(self, text: str, seconds: float = 2.0) -> None:
        self.message = text
        self._message_until = time.monotonic() + seconds

    # --- input ---------------------------------------------------------------

    def on_input(self, frame: InputFrame) -> None:
        pressed = frame.buttons & ~self._prev_buttons  # rising edges
        self._prev_buttons = frame.buttons
        if self._prev_knob is None:
            self._prev_knob = frame.knob
        knob_delta = frame.knob - self._prev_knob
        self._prev_knob = frame.knob
        self._last_frame = frame
        self._frame_count += 1

        if self.state is GameState.MENU:
            if knob_delta:
                self._menu_index = (self._menu_index + (1 if knob_delta > 0 else -1)) % max(1, len(self.levels.names()))
            if pressed & InputFrame.BTN_A or pressed & InputFrame.BTN_KNOB:
                self.start_round()
            elif pressed & InputFrame.BTN_C:
                self.toggle_mode()
        elif self.state is GameState.PLAYING:
            if knob_delta:
                self._manual_select(knob_delta)  # one click of the knob is one tool
            if pressed & InputFrame.BTN_B:
                self.pause()
            elif pressed & InputFrame.BTN_A:
                self._try_grab(manual=True)
            elif pressed & InputFrame.BTN_C:
                self._handover(time.monotonic())
            elif pressed & InputFrame.BTN_KNOB:
                self._switch_on_light(time.monotonic())
        elif self.state is GameState.PAUSED:
            if knob_delta:
                self.sensitivity = max(
                    self.cfg.sensitivity_min,
                    min(self.cfg.sensitivity_max, self.sensitivity + knob_delta * self.cfg.knob_sensitivity_per_step),
                )
            if pressed & InputFrame.BTN_B:
                self.resume()
        elif self.state is GameState.RESULT:
            if pressed & InputFrame.BTN_A:
                self.enter_menu()

    def _manual_select(self, step: int) -> None:
        """The knob: in solo it changes the instrument, in co-op it moves the assistant's choice."""
        word = self.mode.on_manual_select(self.tool.word, step)
        if word:
            self._set_tool(word, by_voice=False)

    def _handover(self, now: float) -> None:
        """Button C: in solo the next instrument, in co-op the assistant hands over what was called."""
        called = self.mode.pending()
        handover = self.mode.on_handover(self.tool.word, now)
        if handover.wrong:
            self.metrics.calls_wrong += 1
            self.say(f"The surgeon called: {called}", 2)
            self.bus.publish(GameEvent(kind="wrong_tool", detail=called))
        elif handover.tool:
            self._set_tool(handover.tool, by_voice=handover.confirmed)
        elif self.mode.selection():
            self.say("No instrument was called", 2)

    def _switch_on_light(self, now: float) -> None:
        """Light up the dark zones for a while: knob press or the "light" command."""
        if self.level is None or not self.level.dark_zones:
            return
        self.light_until = now + self.cfg.light_duration_s
        self.bus.publish(GameEvent(kind="light"))

    # --- commands ------------------------------------------------------------

    def on_command(self, ev: CommandEvent) -> None:
        word = ev.word
        self.last_command = word
        self._misses = 0
        now = time.monotonic()

        if word == "new game":
            if self.state in (GameState.MENU, GameState.RESULT, GameState.PAUSED, GameState.PLAYING):
                self.start_round()
            return
        if word == "help":
            self.bus.publish(GameEvent(kind="help", detail=",".join(self.available_commands())))
            return
        if word == "repeat":
            if self.quiz.pending is not None:  # say the open question again
                self.bus.publish(GameEvent(kind="question", detail=self.quiz.pending.id))
            else:
                self.bus.publish(GameEvent(kind="repeat"))
            return
        if word == "pause":
            self.pause()
            return
        if word == "continue":
            self.resume()
            return
        if self.state is not GameState.PLAYING:
            return

        if word in TREATMENT_WORDS:
            self._treat(word)
        elif word in TOOL_WORDS:
            if self.mode.on_tool_call(word, now):
                self._set_tool(word, by_voice=True)
            else:
                self.say(f"Called: {word}", 2)
                self.bus.publish(GameEvent(kind="awaiting_callback", detail=word))
        elif word == "cancel":
            if self.previous_tool:
                self._set_tool(self.previous_tool, by_voice=True, is_cancel=True)
            else:
                self.say("Nothing to cancel", 2)
        elif word == "steady":
            self.steady_until = now + self.cfg.steady_duration_s
            self.metrics.steady_uses += 1
            self.bus.publish(GameEvent(kind="steady"))
        elif word == "light":
            self._switch_on_light(now)

    def on_misheard(self, ev: MisheardEvent) -> None:
        self.last_command = "?"
        if ev.reason == "no_instruction":
            # A sentence without a treatment while the nurse waits: she asks
            # again, and after two tries names what she can give.
            if self.state is not GameState.PLAYING or not self.vitals.alarm_raised():
                return
            self._instruction_misses += 1
            if self._instruction_misses >= self.cfg.misses_before_help:
                self._instruction_misses = 0
                self.bus.publish(GameEvent(kind="you_can_order"))
            else:
                self.bus.publish(GameEvent(kind="pardon_doctor"))
            return
        self._misses += 1
        if self._misses >= self.cfg.misses_before_help:
            self._misses = 0
            self.bus.publish(GameEvent(kind="help", detail=",".join(self.available_commands())))
        else:
            self.bus.publish(GameEvent(kind="pardon"))

    def available_commands(self) -> list[str]:
        if self.state is GameState.PLAYING:
            if self.vitals.alarm_open():  # the nurse waits for an instruction
                return list(TREATMENT_WORDS)
            needed = {t.needs for t in self.level.remaining()} if self.level else set()
            tools = [w for w in TOOL_WORDS if w in needed] or ["forceps"]
            return tools + ["steady", "cancel", "pause"]
        if self.state is GameState.PAUSED:
            return ["continue", "new game"]
        return ["new game", "help"]

    def _set_tool(self, word: str, by_voice: bool, is_cancel: bool = False) -> None:
        if word == self.tool.word:
            return
        self.previous_tool = None if is_cancel else self.tool.word
        self.tool = instruments.make(word)
        self._dwell_target = None
        if by_voice and not is_cancel:
            self.metrics.calls_correct += 1
        self.bus.publish(GameEvent(kind="tool_changed", detail=word))

    # --- vitals monitor ----------------------------------------------------------

    def _update_vitals(self, dt: float) -> None:
        events = self.vitals.update(dt, self.time_left, blocked=self.quiz.pending is not None)
        self._set_instruction_window(self.vitals.alarm_raised())
        for ev in events:
            if ev.kind == "crisis":
                self.patient.on_crisis()
                self.say("Crisis: the team had to step in", 3)
            self.bus.publish(GameEvent(kind=f"vital_{ev.kind}", detail=f"{ev.vital}:{ev.value}"))

    def _treat(self, word: str) -> None:
        """An instruction to the nurse. The physiology decides what it does."""
        self._instruction_misses = 0
        outcome = self.vitals.treat(word)
        if word == "adrenaline":
            self.patient.startle(self.vitals_cfg.pulse_jump_bpm)
        if outcome.result is TreatmentResult.WRONG:
            self.say(f"{word.capitalize()} did not help: {SPECS[outcome.vital].label}", 3)
        elif outcome.result is TreatmentResult.UNNEEDED:
            self.say(f"{word.capitalize()} was not needed", 3)
        self.bus.publish(GameEvent(kind="treatment", detail=f"{word}:{outcome.result.value}:{outcome.vital}"))

    def _vital_views(self) -> list[VitalView]:
        if not self.vitals.active:
            return []
        return [
            VitalView(key=k, label=v.spec.label, value=round(v.value), unit=v.spec.unit, status=v.status.value, trend=v.trend)
            for k, v in self.vitals.vitals.items()
        ]

    # --- quiz ----------------------------------------------------------------

    def _set_patient_speaking(self, speaking: bool) -> None:
        self._patient_speaking = speaking

    def _update_quiz(self, dt: float) -> None:
        if self.quiz.pending is None and self.vitals.alarm_open():
            return  # one open turn at a time: no question while the nurse waits for an instruction
        step = self.quiz.tick(dt, self._patient_speaking, self.time_left)
        if step is QuizStep.ASK:
            question = self.quiz.pending
            self.bus.publish(QuestionAsked(question_id=question.id))
            self.bus.publish(GameEvent(kind="question", detail=question.id))
        elif step is QuizStep.TIMEOUT:
            self._wrong_answer("quiz_timeout")

    def on_answer(self, ev: AnswerEvent) -> None:
        if self.state is not GameState.PLAYING:
            return
        outcome = self.quiz.answer(ev)
        if outcome is QuizOutcome.UNCLEAR:
            self.last_command = "?"
            self.bus.publish(GameEvent(kind="pardon"))
        elif outcome is QuizOutcome.CORRECT:
            self.stress.better()
            self.say("Correct", 2)
            self.bus.publish(QuestionClosed())
            self.bus.publish(GameEvent(kind="quiz_correct", detail=self.quiz.last.id))
        elif outcome is QuizOutcome.WRONG:
            self._wrong_answer("quiz_wrong")

    def _wrong_answer(self, kind: str) -> None:
        """A wrong or missing answer: less time, a faster pulse, one stress level up."""
        self.stress.worse()
        self.time_left -= self.quiz_cfg.wrong_time_penalty_s
        self.patient.startle(self.quiz_cfg.wrong_heart_rate_bump)
        self.say(f"Wrong: -{self.quiz_cfg.wrong_time_penalty_s:.0f} s", 3)
        self.bus.publish(QuestionClosed())
        self.bus.publish(GameEvent(kind=kind, detail=self.quiz.last.id))

    # --- round update --------------------------------------------------------

    def _update_round(self, dt: float, now: float) -> None:
        assert self.level is not None
        frame = self._last_frame
        if frame is not None:
            self._move(frame, dt, now)
        self.patient.update(dt)
        self._update_targets(dt, now)
        self._update_vitals(dt)
        self._update_quiz(dt)
        self.time_left -= dt
        if self.level.complete():
            self.end_round(won=True)
        elif self.patient.awake(self.cfg.max_contacts):
            self.end_round(won=False)
        elif self.time_left <= 0:
            self.time_left = 0.0
            self.end_round(won=False)

    def _move(self, frame: InputFrame, dt: float, now: float) -> None:
        assert self.level is not None
        tx, ty = frame.tilt_x, frame.tilt_y
        mag = math.hypot(tx, ty)
        moving = mag > self.cfg.deadzone_g
        self.metrics.add_tilt(tx, ty, moving)
        if not moving:
            return
        # Remove the dead zone smoothly so the tool does not jump at the edge.
        scale = (mag - self.cfg.deadzone_g) / max(1e-6, mag)
        speed = self.cfg.speed_px_per_s * self.sensitivity * self.stress.speed_factor
        if now < self.steady_until:
            speed *= self.cfg.steady_factor
        nx = self.x + tx * scale * speed * dt
        ny = self.y + ty * scale * speed * dt
        nx = min(max(nx, 0.0), self.width - 1.0)
        ny = min(max(ny, 0.0), self.height - 1.0)
        r = self.cfg.tool_radius
        if self.level.mask.circle_hits_wall(nx, ny, r):
            # Slide along the wall where possible, otherwise stay.
            if not self.level.mask.circle_hits_wall(nx, self.y, r):
                self.x = nx
            elif not self.level.mask.circle_hits_wall(self.x, ny, r):
                self.y = ny
            self._contact(now)
        else:
            self.x, self.y = nx, ny

    def _contact(self, now: float) -> None:
        if now - self._last_contact_t < self.cfg.contact_cooldown_s:
            return
        self._last_contact_t = now
        self.patient.on_contact()
        self.metrics.contacts = self.patient.contacts
        self.bus.publish(GameEvent(kind="hit"))

    def _target_under_tool(self):
        assert self.level is not None
        for t in self.level.remaining():
            if math.hypot(t.x - self.x, t.y - self.y) <= self.cfg.target_radius:
                return t
        return None

    def _update_targets(self, dt: float, now: float) -> None:
        assert self.level is not None
        for t in self.level.remaining():
            if t.timer_left is not None:
                t.timer_left -= dt * self.stress.bleed_factor
                if t.timer_left <= 0:
                    t.timer_left = t.timer_s
                    self.patient.on_contact()
                    self.metrics.contacts = self.patient.contacts
                    self.bus.publish(GameEvent(kind="bleed_timeout", detail=t.id))
        # Hands-free grab: hover with the right tool for grab_dwell_s.
        target = self._target_under_tool()
        if target is None or not self.tool.can_handle(target):
            self._dwell_target = None
            return
        if self._dwell_target != target.id:
            self._dwell_target = target.id
            self._dwell_elapsed = 0.0
        else:
            self._dwell_elapsed += dt
            if self._dwell_elapsed >= self.cfg.grab_dwell_s:
                self._dwell_target = None
                self._apply_tool(target)

    def _try_grab(self, manual: bool) -> None:
        target = self._target_under_tool()
        if target is None:
            return
        if self.tool.can_handle(target):
            self._apply_tool(target)
        else:
            self.metrics.calls_wrong += 1
            self.say(f"Needs {target.needs}", 2)
            self.bus.publish(GameEvent(kind="wrong_tool", detail=target.needs))

    def _apply_tool(self, target) -> None:
        kind = self.tool.apply(target)
        self.bus.publish(GameEvent(kind=kind, detail=target.id))

    # --- view ----------------------------------------------------------------

    def snapshot(self) -> GameSnapshot:
        now = time.monotonic()
        level = self.level
        in_round = level is not None and self.state in (GameState.PLAYING, GameState.PAUSED)
        hover = self._target_under_tool() if in_round else None
        dwell = self._dwell_elapsed / max(1e-6, self.cfg.grab_dwell_s) if self._dwell_target else 0.0
        return GameSnapshot(
            state=self.state,
            mode=self.mode.name,
            level_name=level.name if level else "",
            level_dir=str(level.directory) if level else "",
            x=self.x,
            y=self.y,
            tool=self.tool.word,
            targets=[
                TargetView(id=t.id, x=t.x, y=t.y, needs=t.needs, done=t.done, timer_left=t.timer_left, timer_s=t.timer_s)
                for t in (level.targets if level else [])
            ],
            time_left=max(0.0, self.time_left),
            contacts=self.patient.contacts,
            max_contacts=self.cfg.max_contacts,
            heart_rate=int(self.patient.heart_rate),
            last_command=self.last_command,
            message=self.message,
            steady=now < self.steady_until,
            lit=now < self.light_until,
            dark_zones=list(level.dark_zones) if level else [],
            pending_call=self.mode.pending(),
            menu_levels=self.levels.names(),
            menu_index=self._menu_index,
            result=self._result,
            mcu_connected=self._mcu_connected,
            tools=TOOL_WORDS,
            hover_target=hover.id if hover else "",
            dwell=min(1.0, dwell),
            sensitivity=self.sensitivity,
            sensitivity_range=(self.cfg.sensitivity_min, self.cfg.sensitivity_max),
            tool_radius=self.cfg.tool_radius,
            light_left=max(0.0, self.light_until - now),
            question_text=self.quiz.pending.text if in_round and self.quiz.pending else "",
            question_left=self.quiz.window_fraction(),
            stress=self.stress.level,
            nurse_selection=self.mode.selection(),
            max_stress=self.quiz_cfg.max_stress,
            crises=self.patient.crises,
            vitals=self._vital_views() if in_round else [],
            vitals_alarm=in_round and self.vitals.alarm_open(),
        )
