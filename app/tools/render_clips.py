#!/usr/bin/env python3
"""Render every patient line and quiz question to WAV once (setup step, not during play).

An existing clip is kept: after changing a question's text, run with --force.

Usage: python tools/render_clips.py [--engine piper|espeak] [--voice path.onnx] [--force]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trainer.audio.tts_renderer import TtsRenderer  # noqa: E402
from trainer.core.config import load  # noqa: E402
from trainer.quiz.question import QuestionBank  # noqa: E402


def main() -> int:
    cfg = load()
    p = argparse.ArgumentParser()
    p.add_argument("--engine", default=cfg.audio.tts_engine, choices=["piper", "espeak"])
    p.add_argument("--voice", default=cfg.audio.piper_voice)
    p.add_argument("--out", default=cfg.audio.clips_dir)
    p.add_argument("--force", action="store_true")
    p.add_argument("--force-nurse", action="store_true", help="render the nurse's clips again (after adding her voice)")
    p.add_argument("--nurse-voice", default=cfg.audio.nurse_voice)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO)
    questions = QuestionBank.load(cfg.quiz.questions_file)
    renderer = TtsRenderer(args.out, args.engine, args.voice, questions, args.nurse_voice)
    print(f"nurse voice: {renderer.nurse_voice or 'none (the patient voice speaks her lines)'}")
    try:
        n = renderer.render_all(force=args.force, force_nurse=args.force_nurse)
    except Exception as exc:
        print(f"TTS failed with {args.engine}: {exc}", file=sys.stderr)
        if args.engine == "piper":
            print("Falling back to espeak-ng", file=sys.stderr)
            n = TtsRenderer(args.out, "espeak", questions=questions).render_all(force=args.force)
        else:
            return 1
    print(f"rendered {n} clips into {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
