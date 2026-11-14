#!/usr/bin/env python3
"""Increment 1: a spoken word gets a spoken answer, entirely on the board.

This is the hackathon's first milestone (PLAN.md, T5) and the thinnest
vertical slice of the trainer: microphone -> speech-to-text -> command ->
the patient answers. No MCU, no display, no game loop.

  python3 increment1.py --setup     render the patient's lines (once)
  python3 increment1.py             listen, answer, and report the latency
  python3 increment1.py -n 20       twenty rounds, for the P6 measurement

Latency is measured from the end of the recording, because that is when the
player stops speaking.
"""

import argparse
import statistics
import sys
import time
from pathlib import Path

from trainer.audio.clips import ClipLibrary
from trainer.audio.tts_renderer import TtsRenderer
from trainer.voice.audio_input import AudioInput
from trainer.voice.commands import CommandMatcher
from trainer.voice.recognizer import WhistleRecognizer

HERE = Path(__file__).parent
CLIP_DIR = HERE / "assets" / "lines"
VOICE_DIR = HERE / "assets" / "voice"

# Which line the patient answers a recognised command with.
ANSWER = {
    "forceps": "took_forceps",
    "swab": "took_swab",
    "clamp": "took_clamp",
    "scalpel": "took_scalpel",
    "help": "help",
}


def setup():
    renderer = TtsRenderer(CLIP_DIR, VOICE_DIR, python=sys.executable)
    rendered = renderer.render_all()
    print(f"{len(rendered)} lines rendered to {CLIP_DIR}")


def one_round(audio, recognizer, matcher, clips, seconds):
    # An audible cue, so the player does not have to watch a terminal to know
    # when to speak. The game will use the same idea for its listening state.
    clips.play("round_start")
    print(f"\nSpeak now ({seconds} s): ", end="", flush=True)
    segment = audio.record(seconds)
    spoken_end = time.monotonic()          # the player has stopped talking

    transcript = recognizer.transcribe(segment)
    event = matcher.match(transcript)
    line = ANSWER.get(event.command, "pardon") if event.recognised else "pardon"
    to_answer = time.monotonic() - spoken_end

    print(f"heard {transcript.text!r}")
    if event.recognised:
        print(f"  -> {event.command} ({event.action}), confidence {event.confidence:.2f}")
    else:
        print(f"  -> nothing above the threshold (best {event.confidence:.2f})")
    print(f"  -> answering {line!r} after {to_answer*1000:.0f} ms")

    clips.play(line)
    return to_answer, event


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--setup", action="store_true",
                        help="render the patient's lines, then exit")
    parser.add_argument("-n", "--rounds", type=int, default=1)
    parser.add_argument("-d", "--seconds", type=int, default=3,
                        help="length of each recording")
    args = parser.parse_args()

    if args.setup:
        setup()
        return 0

    clips = ClipLibrary(CLIP_DIR)
    if not clips.has("pardon"):
        print("The lines have not been rendered yet. Run: "
              "python3 increment1.py --setup", file=sys.stderr)
        return 1

    audio = AudioInput()
    recognizer = WhistleRecognizer()
    matcher = CommandMatcher()

    print("loading the speech model ...", end="", flush=True)
    t0 = time.monotonic()
    recognizer.warm_up()
    print(f" {time.monotonic()-t0:.1f} s")

    latencies, recognised = [], 0
    for _ in range(args.rounds):
        seconds, event = one_round(audio, recognizer, matcher, clips, args.seconds)
        latencies.append(seconds)
        recognised += bool(event.recognised)

    if len(latencies) > 1:
        print(f"\n{len(latencies)} rounds, {recognised} recognised")
        print(f"latency median {statistics.median(latencies)*1000:.0f} ms, "
              f"worst {max(latencies)*1000:.0f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
