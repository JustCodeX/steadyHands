#!/usr/bin/env python3
"""Drive the real voice pipeline with synthetic speech (macOS `say`), no microphone.

Every sentence is rendered to 16 kHz audio, played into VoiceService block by
block (20 ms, real time not needed), and the published outcome is compared
with what the game should do. Runs with the app's own builders, so a config
file chooses the engines exactly as in the game:

    python tools/voice_drive.py --config cactus.toml           # Whistle + Needle
    python tools/voice_drive.py                                  # defaults (no model)
    python tools/voice_drive.py --save-wavs clips/                # only render the voices (on a Mac)
    python tools/voice_drive.py --wav-dir clips/ --config cactus.toml   # on the board, without `say`

Numbers from here are "laptop, synthetic voices": they show the pipeline
works, not how it does with real speakers on the board.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trainer.__main__ import load_questions  # noqa: E402
from trainer.core.config import load  # noqa: E402
from trainer.core.event_bus import EventBus  # noqa: E402
from trainer.core.events import CommandEvent, InstructionWindow, ListenRequest, MisheardEvent  # noqa: E402
from trainer.voice.voice_service import (  # noqa: E402
    VoiceService,
    build_answer_recognizer,
    build_evaluator,
    build_interpreter,
    build_recognizer,
    build_sentence_recognizer,
    build_treatment_interpreter,
    command_phrases,
)

# (what is said, alarm open?, expected outcome: a command/treatment word, "pardon" or None)
CASES: list[tuple[str, bool, str | None]] = [
    ("Clamp!", False, "clamp"),
    ("Forceps.", True, "forceps"),
    ("Steady.", False, "steady"),
    ("Oxygen!", True, "oxygen"),
    ("Give him some adrenaline.", True, "adrenaline"),
    ("He can't breathe, do something.", True, "oxygen"),
    ("His sats are dropping fast.", True, "oxygen"),
    ("The patient is waking up.", True, "anaesthesia"),
    ("He's moving, put him deeper.", True, "anaesthesia"),
    ("His blood pressure is falling.", True, "adrenaline"),
    ("He's going into shock.", True, "adrenaline"),
    ("Hand me the clamp please.", True, "clamp"),
    ("What a lovely day it is.", True, "pardon"),
    ("What a lovely day it is.", False, None),
    ("His sats look good now.", False, None),
    ("He can't breathe, do something.", False, None),
]
VOICES = ("Samantha", "Daniel")


class PlayedAudio:
    """Feeds 20 ms int16 blocks into the voice thread: silence, the clip, silence."""

    running = False

    def __init__(self) -> None:
        self.blocks: list[np.ndarray] = []

    def play(self, samples: np.ndarray) -> None:
        rng = np.random.default_rng(0)
        quiet = [(0.001 * rng.standard_normal(320) * 32767).astype(np.int16) for _ in range(25)]
        pad = np.zeros((-len(samples)) % 320, dtype=np.int16)
        clip = np.concatenate([samples, pad]).reshape(-1, 320)
        self.blocks = quiet + list(clip) + [b.copy() for b in quiet] * 3

    def start(self) -> None:
        self.running = True

    def stop(self) -> None:
        self.running = False

    def read(self, timeout: float = 0.1):
        if self.blocks:
            return self.blocks.pop(0)
        time.sleep(0.005)
        return None


def clip_name(voice: str, index: int) -> str:
    return f"{voice}_{index:02d}.wav"


def say(text: str, voice: str, path: Path) -> None:
    subprocess.run(["say", "-v", voice, "-o", str(path), "--data-format=LEI16@16000", text], check=True)


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError(f"{path} is not 16 kHz mono 16-bit")
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--config", help="TOML file with overrides (cactus.toml for Whistle + Needle)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--wav-dir", type=Path, help="read the clips from here instead of synthesising them")
    p.add_argument("--save-wavs", type=Path, help="only render the clips into this folder, then stop")
    args = p.parse_args(argv)
    if args.wav_dir is None and shutil.which("say") is None:
        print("needs macOS `say` for the synthetic voices, or --wav-dir with clips rendered elsewhere", file=sys.stderr)
        return 2
    if args.save_wavs is not None:
        args.save_wavs.mkdir(parents=True, exist_ok=True)
        for voice in VOICES:
            for i, (text, _, _) in enumerate(CASES):
                say(text, voice, args.save_wavs / clip_name(voice, i))
        print(f"rendered {len(VOICES) * len(CASES)} clips into {args.save_wavs}")
        return 0
    cfg = load(args.config)
    bus = EventBus()
    started = time.perf_counter()
    sentence = build_sentence_recognizer(cfg.voice, cfg.treatments)
    phrases = command_phrases(cfg.commands, cfg.treatments, sentence_path=sentence is not None)
    interpreter = build_interpreter(cfg.voice, phrases)
    audio = PlayedAudio()
    questions = load_questions(cfg)
    svc = VoiceService(
        bus,
        cfg.voice,
        phrases,
        recognizer=build_recognizer(cfg.voice, interpreter.phrases()),
        interpreter=interpreter,
        audio=audio,
        questions=questions,
        answer_recognizer=build_answer_recognizer(cfg.voice, questions),
        evaluator=build_evaluator(cfg.voice),
        treatments=cfg.treatments,
        sentence_recognizer=sentence,
        treatment_interpreter=build_treatment_interpreter(cfg.voice, cfg.treatments) if sentence is not None else None,
    )
    load_s = time.perf_counter() - started
    seen: list = []
    bus.subscribe(CommandEvent, seen.append)
    bus.subscribe(MisheardEvent, seen.append)
    bus.publish(ListenRequest(on=True))
    bus.dispatch()
    svc.start()
    rows = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for voice in VOICES:
                for i, (text, alarm, expected) in enumerate(CASES):
                    if args.wav_dir is not None:
                        samples = read_wav(args.wav_dir / clip_name(voice, i))
                    else:
                        say(text, voice, Path(tmp) / clip_name(voice, i))
                        samples = read_wav(Path(tmp) / clip_name(voice, i))
                    bus.publish(InstructionWindow(open=alarm))
                    bus.dispatch()
                    seen.clear()
                    audio.play(samples)
                    deadline = time.monotonic() + 15
                    while (audio.blocks or svc.state.name == "PROCESSING") and time.monotonic() < deadline:
                        bus.dispatch()
                        time.sleep(0.01)
                    time.sleep(0.05)
                    bus.dispatch()
                    event = seen[0] if seen else None
                    got = event.word if isinstance(event, CommandEvent) else ("pardon" if isinstance(event, MisheardEvent) else None)
                    latency = (event.t - event.speech_end_t) * 1000 if event is not None and event.speech_end_t else None
                    rows.append({"voice": voice, "said": text, "alarm": alarm, "expected": expected, "got": got, "ok": got == expected,
                                 "latency_ms": round(latency) if latency is not None else None})
    finally:
        svc.stop()
    ok = sum(r["ok"] for r in rows)
    latencies = sorted(r["latency_ms"] for r in rows if r["latency_ms"] is not None)
    summary = {
        "config": args.config or "defaults",
        "passed": ok,
        "cases": len(rows),
        "median_ms": latencies[len(latencies) // 2] if latencies else None,
        "worst_ms": latencies[-1] if latencies else None,
        "load_s": round(load_s, 2),
    }
    if args.json:
        print(json.dumps({"summary": summary, "rows": rows}, indent=2))
    else:
        print(f"{summary['config']}: {ok}/{len(rows)} right, end of speech -> event median {summary['median_ms']} ms, "
              f"worst {summary['worst_ms']} ms, engines loaded in {summary['load_s']} s")
        for r in rows:
            if not r["ok"]:
                print(f"   {r['voice']}: {r['said']!r} (alarm {'open' if r['alarm'] else 'closed'}) -> {r['got']} (expected {r['expected']})")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
