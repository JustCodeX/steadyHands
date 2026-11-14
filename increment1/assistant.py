#!/usr/bin/env python3
"""The assistant avatar: a face on the display that listens and answers.

Increment 1 with a face on it. The pipeline is unchanged - microphone ->
Whistle -> CommandMatcher -> pre-rendered line - but the player now sees what
the voice system is doing instead of reading a terminal.

The four states come from PLAN.md, "Speech interaction": off, listening,
processing, speaking. They are the same states the board's RGB LED 4 shows,
so screen and LED never disagree.

  python3 assistant.py       fullscreen on the 7-inch display

Stop it with Ctrl+C.

Audio capture and transcription run on a worker thread, so the face keeps
animating while the assistant listens and thinks.
"""

import argparse
import queue
import sys
import threading
import time
from pathlib import Path

from trainer.audio.clips import ClipLibrary
from trainer.ui.avatar import LISTENING, OFF, PROCESSING, SPEAKING, Avatar
from trainer.voice.audio_input import AudioInput
from trainer.voice.commands import CommandMatcher
from trainer.voice.recognizer import WhistleRecognizer
from trainer.voice.vad import VoiceActivityDetector

HERE = Path(__file__).parent
CLIP_DIR = HERE / "assets" / "lines"

ANSWER = {
    "forceps": "took_forceps",
    "swab": "took_swab",
    "clamp": "took_clamp",
    "scalpel": "took_scalpel",
    "help": "help",
}
LISTEN_SECONDS = 4


def listener(audio, recognizer, matcher, vad, results, stop):
    """Record and recognise in the background, so the face keeps moving."""
    while not stop.is_set():
        results.put(("state", LISTENING, ""))
        segment = audio.record(LISTEN_SECONDS)
        spoken_end = time.monotonic()
        if stop.is_set():
            return

        # Never transcribe silence: Whistle hallucinates "Thank you." on an
        # empty room, and running the model on nothing wastes energy.
        if not vad.has_speech(segment):
            continue

        results.put(("state", PROCESSING, ""))
        transcript = recognizer.transcribe(segment)
        event = matcher.match(transcript)
        line = ANSWER.get(event.command, "pardon") if event.recognised else "pardon"
        results.put(("answer", line, event, time.monotonic() - spoken_end,
                     transcript.text))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args()

    clips = ClipLibrary(CLIP_DIR)
    if not clips.has("pardon"):
        print("The lines have not been rendered. Run: "
              "python3 increment1.py --setup", file=sys.stderr)
        return 1

    avatar = Avatar()

    avatar.set_state(PROCESSING, "waking up")
    avatar.draw()
    recognizer = WhistleRecognizer()
    recognizer.warm_up()

    audio = AudioInput()
    matcher = CommandMatcher()
    vad = VoiceActivityDetector()
    results, stop = queue.Queue(), threading.Event()
    worker = threading.Thread(
        target=listener, args=(audio, recognizer, matcher, vad, results, stop),
        daemon=True)
    worker.start()

    playing = None
    try:
        while avatar.pump():
            while not results.empty():
                item = results.get()
                if item[0] == "state":
                    _, state, subtitle = item
                    if playing is None:
                        avatar.set_state(
                            state, subtitle,
                            transcript="" if state == LISTENING else None)
                else:
                    _, line, event, latency, heard = item
                    label = event.command if event.recognised else "?"
                    print(f"heard {heard!r} -> {label} ({latency*1000:.0f} ms)")
                    avatar.set_state(SPEAKING,
                                     label if event.recognised else "Pardon?",
                                     transcript=heard)
                    playing = clips.start(line)

            if playing is not None and playing.poll() is not None:
                playing = None            # the listener thread sets the next state

            avatar.draw()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        avatar.set_state(OFF)
        avatar.draw()
        time.sleep(0.3)
        avatar.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
