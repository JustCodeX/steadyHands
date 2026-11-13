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
    alarm_ms: int = 350
    steady_factor: float = 0.4
    steady_duration_s: float = 6.0
    light_duration_s: float = 6.0
    coop_callback_window_s: float = 5.0
    result_show_s: float = 12.0
    heart_rate_base: int = 72
    heart_rate_per_contact: int = 22
    heart_rate_decay_per_s: float = 4.0
    misses_before_help: int = 2


@dataclass
class VoiceConfig:
    enabled: bool = True
    recognizer: str = "vosk"  # "vosk" | "null"
    model_dir: str = str(APP_DIR / "models" / "vosk-model-small-en-us-0.15")
    sample_rate: int = 16000
    block_ms: int = 20
    input_device: str = ""  # substring of the device name; "" = default
    highpass_hz: float = 100.0
    agc_target_rms: float = 0.08
    agc_max_gain: float = 12.0
    vad_ratio: float = 3.0  # speech if rms > ratio * noise floor
    vad_min_rms: float = 0.01
    vad_start_ms: int = 60
    vad_hangover_ms: int = 400
    max_segment_s: float = 3.0
    confidence_threshold: float = 0.6


@dataclass
class AudioConfig:
    enabled: bool = True
    clips_dir: str = str(APP_DIR / "assets" / "clips")
    output_device: str = ""
    volume: float = 0.9
    tts_engine: str = "piper"  # setup only: "piper" | "espeak"
    piper_voice: str = str(APP_DIR / "models" / "piper" / "en_US-lessac-medium.onnx")


@dataclass
class McuConfig:
    enabled: bool = True
    address: str = "unix:///var/run/arduino-router.sock"
    connect_timeout_s: float = 5.0
    frame_timeout_s: float = 2.0


@dataclass
class SystemConfig:
    idle_timeout_s: float = 60.0
    display_name: str = ":0"
    metrics_log: str = str(APP_DIR / "logs" / "metrics.csv")
    sample_interval_s: float = 5.0


@dataclass
class Config:
    display: DisplayConfig = field(default_factory=DisplayConfig)
    game: GameConfig = field(default_factory=GameConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    mcu: McuConfig = field(default_factory=McuConfig)
    system: SystemConfig = field(default_factory=SystemConfig)
    levels_dir: str = str(REPO_DIR / "levels")
    commands: dict[str, list[str]] = field(default_factory=lambda: {k: list(v) for k, v in DEFAULT_COMMANDS.items()})

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
