"""All settings in one place. Defaults here; overrides from a TOML file
(`--config path` or STEADYHANDS_CONFIG) with the same nesting."""
from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = APP_DIR.parent

# Command word -> phrases the matcher accepts for it. Keep words that sound different.
DEFAULT_COMMANDS: dict[str, list[str]] = {
    "forceps": ["forceps", "tweezers"],
    "swab": ["swab", "sponge"],
    "clamp": ["clamp"],
    "scalpel": ["scalpel", "knife"],
    "light": ["light", "lights"],
    "steady": ["steady"],
    "cancel": ["cancel", "undo"],
    "repeat": ["repeat", "again"],
    "help": ["help"],
    "pause": ["pause"],
    "continue": ["continue", "resume"],
    "new game": ["new game", "start", "new round"],
}

TOOL_WORDS = ("forceps", "swab", "clamp", "scalpel")
TREATMENT_WORDS = ("oxygen", "propofol", "adrenaline")

# Drug -> its names, for the nurse's orders on the vitals monitor. An order
# names the drug and, with Whistle and Needle, an amount ("Propofol 30").
# They stay apart from the commands above, which stay on the Vosk grammar:
# neither path fires the other's words. Only without the Cactus models do
# these names join the Vosk grammar (orders at the standard dose), so the
# game stays playable by voice (criterion T3).
DEFAULT_TREATMENTS: dict[str, list[str]] = {
    "oxygen": ["oxygen"],
    "propofol": ["propofol"],
    "adrenaline": ["adrenaline", "epinephrine"],
}


@dataclass
class DisplayConfig:
    width: int = 1024
    height: int = 600
    fullscreen: bool = True
    fps: int = 30
    driver: str = ""  # e.g. "dummy" for headless tests


@dataclass
class GameConfig:
    speed_px_per_s: float = 420.0  # at full tilt (1 g)
    deadzone_g: float = 0.06
    knob_sensitivity_per_step: float = 0.04  # knob changes speed by this fraction per step
    sensitivity_min: float = 0.3
    sensitivity_max: float = 2.0
    tool_radius: int = 9
    target_radius: int = 26
    grab_dwell_s: float = 1.0  # hover this long with the right tool to grab hands-free
    contact_cooldown_s: float = 0.5
    max_contacts: int = 3
    steady_factor: float = 0.4
    steady_duration_s: float = 6.0
    light_duration_s: float = 6.0
    coop_callback_window_s: float = 8.0  # the assistant must hand the called instrument over within this time
    result_show_s: float = 12.0
    heart_rate_base: int = 72
    heart_rate_per_contact: int = 22
    heart_rate_decay_per_s: float = 4.0
    misses_before_help: int = 2


@dataclass
class VoiceConfig:
    enabled: bool = True
    # The older commands: "vosk" | "null". They stay on Vosk; Whistle and
    # Needle serve only the treatments (below).
    recognizer: str = "vosk"
    # Transcript -> command word: "keyword", the phrase matcher.
    interpreter: str = "keyword"
    # "restricted": the recogniser only knows the command phrases (robust).
    # "open": its full vocabulary (for experiments; mishears more).
    command_vocabulary: str = "restricted"
    model_dir: str = str(APP_DIR / "models" / "vosk-model-small-en-us-0.15")
    sample_rate: int = 16000
    block_ms: int = 20
    # Substring of the device name; "" = default input. "USB Audio" matches a USB
    # headset ("JBL Tune 530C: USB Audio (hw:1,0)"). Without one the default input is used.
    input_device: str = "USB Audio"
    highpass_hz: float = 100.0
    agc_target_rms: float = 0.08
    agc_max_gain: float = 12.0
    vad_ratio: float = 3.0  # speech if rms > ratio * noise floor
    vad_min_rms: float = 0.01
    vad_start_ms: int = 60
    vad_hangover_ms: int = 400
    # Fed to the recogniser before the segment: the quiet word onset ("f" in
    # "forceps") that the VAD needs vad_start_ms to react to would be lost.
    vad_preroll_ms: int = 250
    max_segment_s: float = 3.0
    # Adaptive end: a segment longer than this is a sentence. It then ends
    # after long_hangover_ms of silence and may last long_max_segment_s.
    short_segment_s: float = 1.2
    long_hangover_ms: int = 700
    long_max_segment_s: float = 6.0
    confidence_threshold: float = 0.6
    # --- the nurse's treatments (vitals monitor) ---
    # Sentences for the treatments: "none" (the treatment phrases join the
    # Vosk command grammar; no model needed), "whistle" (Cactus), or "vosk"
    # (open vocabulary). The older commands stay on the Vosk grammar either way.
    sentence_recognizer: str = "none"
    # Sentence -> orders: "keyword" (drug names only, standard doses) or
    # "needle" (drug and amount, when a drug is named).
    treatment_interpreter: str = "keyword"
    sentence_confidence_threshold: float = 0.5
    # --- spoken quiz answers (whole sentences) ---
    # Spoken answer -> one of the question's options. "keyword" looks for the
    # options' phrases. "needle" adds the tool-calling model for answers that
    # name none of them ("the thing you cut with").
    evaluator: str = "keyword"
    # Which engine hears whole sentences for answers: "vosk" | "whistle".
    answer_engine: str = "vosk"
    # "open": free speech; follows sentences but mishears rare words.
    # "keywords": only the open question's answer phrases; knows the words
    # but loses them inside a sentence. "both": the two hear the same audio.
    answer_vocabulary: str = "both"
    answer_max_segment_s: float = 8.0
    answer_hangover_ms: int = 700  # people pause in the middle of a sentence
    answer_confidence_threshold: float = 0.5
    debug_asr: bool = False  # on-screen side panel with everything the recogniser hears
    # --- Cactus models (optional; see app/cactus.toml) ---
    # 12 layers: the smallest rung that reads drug and amount well enough (tools/needle_eval.py, 14 Nov)
    needle_weights: str = str(APP_DIR / "models" / "needle3-12L.cact")
    needle_min_confidence: float = 0.1  # the runtime itself holds back calls below 0.1
    # Needle only runs when a drug is named in the sentence (its tools'
    # triggers): without this the published rungs call a tool for almost any talk.
    needle_require_trigger: bool = True
    whistle_weights: str = str(APP_DIR / "models" / "whistle.cact")
    whistle_language: str = "en"  # pinned: auto-detection confuses languages on short segments


@dataclass
class QuizConfig:
    """Questions the patient asks during a round, and what a wrong answer costs.

    Off by default since 14 Nov 2026: the vitals monitor replaced it in the
    levels. The code and the levels' quiz blocks stay; `enabled = true` in a
    TOML file brings it back."""

    enabled: bool = False
    questions_file: str = str(APP_DIR / "assets" / "questions.json")
    questions_per_round: int = 2  # a level can override this (level.json, "quiz")
    first_after_s: float = 8.0
    interval_s: float = 12.0  # from one question's end to the next question
    answer_window_s: float = 8.0  # counts only while the patient is silent
    min_time_left_s: float = 12.0  # no new question this close to the end of the round
    unclear_limit: int = 2  # this many unclear answers count as a wrong one
    wrong_time_penalty_s: float = 5.0
    wrong_heart_rate_bump: int = 15
    max_stress: int = 3
    stress_speed_step: float = 0.15  # the instrument moves this much faster per stress level
    stress_bleed_step: float = 0.25  # bleeding timers run this much faster per stress level


@dataclass
class VitalsConfig:
    """The vitals monitor (game/vitals.py). A level says how many episodes it has."""

    enabled: bool = True
    first_after_s: float = 8.0  # the first episode starts this long into the round
    interval_s: tuple[float, float] = (8.0, 16.0)  # from one episode's end to the next one's start
    drift_to_critical_s: float = 18.0  # a drifting value goes from normal to critical in about this time
    reminder_s: float = 6.0  # the nurse repeats the alarm with the value after this long without the right instruction
    crisis_after_s: float = 4.0  # critical for this long costs a life
    recover_s: float = 3.0  # after an order the value reaches where it settles in about this time
    min_time_left_s: float = 15.0  # no new episode this close to the end of the round
    effect_s: float = 8.0  # a dose's overshoot and side effects last this long, then wear off
    repeat_window_s: float = 2.0  # the same order again within this time counts once (heard twice)
    fio2_baseline: float = 30.0  # oxygen setting (%) at the start; the nurse weans back to it
    wean_per_s: float = 5.0  # how fast she takes the oxygen back down once the saturation is stable
    pulse_per_microgram: float = 0.8  # adrenaline makes the pulse jump (bpm per microgram)
    # An order that names the drug but no amount gets this. It fits about
    # half of the episodes; the monitor tells the right amount (game/vitals.py).
    standard_doses: dict[str, float] = field(default_factory=lambda: {"oxygen": 55.0, "propofol": 30.0, "adrenaline": 10.0})


@dataclass
class AudioConfig:
    enabled: bool = True
    clips_dir: str = str(APP_DIR / "assets" / "clips")
    output_device: str = ""
    volume: float = 0.9
    tts_engine: str = "piper"  # setup only: "piper" | "espeak"
    piper_voice: str = str(APP_DIR / "models" / "piper" / "en_US-lessac-medium.onnx")
    # The nurse's own voice, so the room hears two people. Without the file
    # her lines are rendered with piper_voice. Setup only, like piper_voice.
    nurse_voice: str = str(APP_DIR / "models" / "piper" / "en_GB-jenny_dioco-medium.onnx")


@dataclass
class McuConfig:
    enabled: bool = True
    # Show the active tool on the Modulino Buttons LEDs.
    tool_leds: bool = False
    address: str = "unix:///var/run/arduino-router.sock"
    connect_timeout_s: float = 5.0
    frame_timeout_s: float = 2.0


@dataclass
class SystemConfig:
    idle_timeout_s: float = 60.0
    # DPMS-off cuts the panel's power; its inrush on wake browns out the USB hub
    # and drops the headset (measured 13 Nov). The renderer already paints the
    # screen black while idle, so this stays off unless a separate supply feeds
    # the display.
    display_dpms: bool = False
    display_name: str = ":0"
    metrics_log: str = str(APP_DIR / "logs" / "metrics.csv")
    sample_interval_s: float = 5.0


@dataclass
class Config:
    display: DisplayConfig = field(default_factory=DisplayConfig)
    game: GameConfig = field(default_factory=GameConfig)
    quiz: QuizConfig = field(default_factory=QuizConfig)
    vitals: VitalsConfig = field(default_factory=VitalsConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    mcu: McuConfig = field(default_factory=McuConfig)
    system: SystemConfig = field(default_factory=SystemConfig)
    levels_dir: str = str(REPO_DIR / "levels")
    commands: dict[str, list[str]] = field(default_factory=lambda: {k: list(v) for k, v in DEFAULT_COMMANDS.items()})
    treatments: dict[str, list[str]] = field(default_factory=lambda: {k: list(v) for k, v in DEFAULT_TREATMENTS.items()})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _apply(obj: Any, data: dict[str, Any]) -> None:
    names = {f.name for f in fields(obj)}
    for key, value in data.items():
        if key not in names:
            raise KeyError(f"unknown config key: {key}")
        current = getattr(obj, key)
        if is_dataclass(current) and isinstance(value, dict):
            _apply(current, value)
        else:
            setattr(obj, key, value)


def load(path: str | os.PathLike | None = None) -> Config:
    """Defaults, overlaid with a TOML file if given (or STEADYHANDS_CONFIG)."""
    cfg = Config()
    path = path or os.environ.get("STEADYHANDS_CONFIG")
    if path:
        with open(path, "rb") as f:
            _apply(cfg, tomllib.load(f))
    return cfg
