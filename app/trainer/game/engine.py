"""The game: state machine, movement, collisions, targets, commands."""
from __future__ import annotations

import logging
import math
import time

from ..core.config import GameConfig, TOOL_WORDS
from ..core.events import (
    CommandEvent,
    GameEvent,
    GameSnapshot,
    GameState,
    IdleChanged,
    InputFrame,
    ListenRequest,
    McuStatus,
    MisheardEvent,
    RoundResult,
    TargetView,
)
from ..core.service import Service
from . import instruments
from .level import Level, LevelCatalog
from .metrics import TrainingMetrics
from .modes import CoopMode, GameMode, SoloMode
from .patient import Patient

log = logging.getLogger(__name__)


class GameEngine(Service):
    name = "game"

    def __init__(self, bus, cfg: GameConfig, levels: LevelCatalog, width: int = 1024, height: int = 600) -> None:
        super().__init__(bus)
        self.cfg = cfg
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
        self._last_pos_frame: InputFrame | None = None
        # position mode: (hand_x, hand_y, tool_x, tool_y) captured as the zero
        # position mode: the previous frame's two distances in mm
        self._pos_prev: tuple[float, float] | None = None
        self._frame_count = 0
        self._menu_index = 0
        self._mcu_connected = False
        self._listening = False

        bus.subscribe(InputFrame, self.on_input)
        bus.subscribe(CommandEvent, self.on_command)
        bus.subscribe(MisheardEvent, self.on_misheard)
        bus.subscribe(IdleChanged, self.on_idle)
        bus.subscribe(McuStatus, self._on_mcu_status)

    # --- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        self.enter_menu()

    def tick(self, dt: float) -> None:
        now = time.monotonic()
        if self.state is GameState.PLAYING:
            self._update_round(dt, now)
        elif self.state is GameState.RESULT and now - self._result_t > self.cfg.result_show_s:
            self.enter_menu()
        if isinstance(self.mode, CoopMode):
            self.mode.expire(now)
        if now > self._message_until:
            self.message = ""
        self.bus.publish(self.snapshot())

    # --- state changes -------------------------------------------------------

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
        self._pos_prev = None  # start from the level's start point, not the hand
        self.patient.reset()
        self.metrics.start()
        self.mode.reset()
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
        self.metrics.end()
        self.metrics.contacts = self.patient.contacts
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
            self._pos_prev = None  # the hand has probably moved while paused
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
        if frame.source == self.cfg.position_source:
            self._last_pos_frame = frame
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
                self._cycle_tool(knob_delta)  # one click of the knob is one tool
            if pressed & InputFrame.BTN_B:
                self.pause()
            elif pressed & InputFrame.BTN_A:
                self._try_grab(manual=True)
            elif pressed & InputFrame.BTN_C:
                self._cycle_tool()
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

    def _cycle_tool(self, step: int = 1) -> None:
        """Pick the next (or previous) tool by hand: knob turn or button C."""
        words = list(TOOL_WORDS)
        self._set_tool(words[(words.index(self.tool.word) + step) % len(words)], by_voice=False)

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

        if word in TOOL_WORDS:
            if self.mode.on_tool_call(word, now):
                self._set_tool(word, by_voice=True)
            else:
                self.say(f"Call-back: {word}?", self.cfg.coop_callback_window_s)
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
        self._misses += 1
        if self._misses >= self.cfg.misses_before_help:
            self._misses = 0
            self.bus.publish(GameEvent(kind="help", detail=",".join(self.available_commands())))
        else:
            self.bus.publish(GameEvent(kind="pardon"))

    def available_commands(self) -> list[str]:
        if self.state is GameState.PLAYING:
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

    # --- round update --------------------------------------------------------

    def _update_round(self, dt: float, now: float) -> None:
        assert self.level is not None
        # Buttons and the knob may come from one board while the position comes
        # from another, so movement follows its own source's last frame.
        frame = self._last_pos_frame if self.cfg.input_mode == "position" else self._last_frame
        if frame is not None:
            self._move(frame, dt, now)
        self.patient.update(dt)
        self._update_targets(dt, now)
        self.time_left -= dt
        if self.level.complete():
            self.end_round(won=True)
        elif self.cfg.invincible:
            self.time_left = max(self.time_left, 1.0)  # losing is disabled for testing
        elif self.patient.awake(self.cfg.max_contacts):
            self.end_round(won=False)
        elif self.time_left <= 0:
            self.time_left = 0.0
            self.end_round(won=False)

    def _move(self, frame: InputFrame, dt: float, now: float) -> None:
        assert self.level is not None
        if self.cfg.input_mode == "position":
            self._move_absolute(frame, dt, now)
            return
        tx, ty = frame.tilt_x, frame.tilt_y
        mag = math.hypot(tx, ty)
        moving = mag > self.cfg.deadzone_g
        self.metrics.add_tilt(tx, ty, moving)
        if not moving:
            return
        # Remove the dead zone smoothly so the tool does not jump at the edge.
        scale = (mag - self.cfg.deadzone_g) / max(1e-6, mag)
        speed = self.cfg.speed_px_per_s * self.sensitivity
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

    def _move_absolute(self, frame: InputFrame, dt: float, now: float) -> None:
        """Position mode: move the tool by how much the distances changed.

        Only the difference between two consecutive frames counts, never the
        distance itself: the tool keeps whatever place it has and the hand
        pushes it from there, so no reading can ever pull it to a fixed spot.
        A jump larger than `position_max_step_mm` is the beam hitting something
        other than the wall and is dropped.
        """
        assert self.level is not None
        if not frame.distance_mm or not frame.distance_y_mm:
            self._pos_prev = None  # no echo: wait for a fresh pair to compare
            return
        mm_x, mm_y = float(frame.distance_mm), float(frame.distance_y_mm)
        if self._pos_prev is None:
            self._pos_prev = (mm_x, mm_y)
            return
        dx_mm = mm_x - self._pos_prev[0]
        dy_mm = mm_y - self._pos_prev[1]
        self._pos_prev = (mm_x, mm_y)
        limit = self.cfg.position_max_step_mm
        if abs(dx_mm) > limit:
            dx_mm = 0.0
        if abs(dy_mm) > limit:
            dy_mm = 0.0
        if self.cfg.position_invert_x:
            dx_mm = -dx_mm
        if self.cfg.position_invert_y:
            dy_mm = -dy_mm
        scale = self.cfg.position_px_per_mm * self.sensitivity
        if now < self.steady_until:
            scale *= self.cfg.steady_factor
        vx = dx_mm * scale / max(dt, 1e-6) / self.cfg.speed_px_per_s
        vy = dy_mm * scale / max(dt, 1e-6) / self.cfg.speed_px_per_s
        self.metrics.add_tilt(vx, vy, math.hypot(vx, vy) > self.cfg.deadzone_g)
        self._step_towards(self.x + dx_mm * scale, self.y + dy_mm * scale, now)

    def _step_towards(self, nx: float, ny: float, now: float) -> None:
        """Walk to (nx, ny) in sub-steps so a hand jump cannot tunnel a wall."""
        assert self.level is not None
        nx = min(max(nx, 0.0), self.width - 1.0)
        ny = min(max(ny, 0.0), self.height - 1.0)
        r = self.cfg.tool_radius
        steps = max(1, int(math.hypot(nx - self.x, ny - self.y) / max(1, r)))
        dx = (nx - self.x) / steps
        dy = (ny - self.y) / steps
        for _ in range(steps):
            cx, cy = self.x + dx, self.y + dy
            if self.level.mask.circle_hits_wall(cx, cy, r):
                # Slide along the wall where possible, otherwise stay.
                if not self.level.mask.circle_hits_wall(cx, self.y, r):
                    self.x = cx
                elif not self.level.mask.circle_hits_wall(self.x, cy, r):
                    self.y = cy
                self._contact(now)
                return
            self.x, self.y = cx, cy

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
                t.timer_left -= dt
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
        )
