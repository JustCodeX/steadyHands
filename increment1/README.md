# Increment 1: a spoken word gets a spoken answer

**Status: works on the board, measured. 301 ms from the end of speech to the
patient's reply, with an avatar on the 7-inch display.**

This is the hackathon's first milestone ([PLAN.md](../PLAN.md#hackathon-criteria-check),
T5) and the thinnest vertical slice of the trainer:

```
headset mic -> arecord -> VAD gate -> Whistle (speech-to-text) -> CommandMatcher
                                                                       |
                       avatar on the display  <--  pre-rendered line ->  headset
```

No MCU, no display, no game loop. That is deliberate: the whole increment runs
on the Linux side, so none of it depends on the `arduinoq` PlatformIO core or
the Bridge, which are still untested.

## Why this folder exists

Everything here is **self-contained on purpose**, so it cannot collide with
anyone else's work. The classes below are the ones PLAN.md assigns to
`app/trainer/` — exactly the files the Voice person is meant to create. If
they had been written straight into `app/`, that person would have found them
already in their way.

Nothing outside this folder was changed. `app/`, `firmware/`, `docs/`,
`levels/` and the planning documents are untouched.

Moving a class into `app/trainer/` is a deliberate decision for whoever owns
that package, not something this folder did behind their back.

## Try it on the board

The board needs the environment from
[docs/measurements.md](docs/measurements.md#python-environment-on-the-board)
(a venv with `cactus-compute[mic]`, `piper-tts` and `numpy`). Then:

```sh
# from your machine
tar --exclude=__pycache__ --exclude=assets -cf - . \
  | ssh arduino@<board-ip> 'mkdir -p ~/trainer-app && tar -C ~/trainer-app -xf -'

# on the board
cd ~/trainer-app
~/trainer-venv/bin/python increment1.py --setup   # render the patient's lines, once
~/trainer-venv/bin/python increment1.py           # one round
~/trainer-venv/bin/python increment1.py -n 20     # twenty rounds, for the P6 measurement
```

### The avatar

```sh
tools/assistant-ctl.sh start     # face on the display, listens continuously
tools/assistant-ctl.sh log 20    # what it heard
tools/assistant-ctl.sh stop
```

The display is held by lightdm's greeter until you free it, once per boot:

```sh
sudo systemctl stop lightdm      # the board should show the trainer, not a desktop
```

The face shows what the voice system is doing - the four states from
[PLAN.md](../PLAN.md) - with the matched command underneath and the raw
transcript below that, so you can always see *why* it did what it did.

You hear "I am ready. Let us begin.", then say a command: `forceps`, `swab`,
`clamp`, `scalpel` or `help`. The patient answers, and the latency is printed.

## What is in here

| File | Class | What it does |
| --- | --- | --- |
| `trainer/voice/audio_input.py` | `AudioInput` | Capture through `arecord`, plus `stream()` for the VAD that comes next |
| `trainer/voice/recognizer.py` | `SpeechRecognizer`, `WhistleRecognizer` | Abstract base plus Whistle, with `warm_up()` |
| `trainer/voice/commands.py` | `CommandMatcher`, `CommandEvent` | Free transcription to one command, or deliberately none |
| `trainer/audio/lines.py` | — | The patient's lines, scripted (no LLM, T3) |
| `trainer/audio/tts_renderer.py` | `TtsRenderer` | Piper, setup only — never runs during play |
| `trainer/audio/clips.py` | `ClipLibrary` | Playback, blocking so the mic never hears the patient |
| `trainer/voice/vad.py` | `VoiceActivityDetector` | Energy gate, so silence never reaches the recogniser |
| `trainer/ui/framebuffer.py` | `Framebuffer` | Drawing into `/dev/fb0` without X or root |
| `trainer/ui/avatar.py` | `Avatar` | The face, its four states, command and transcript |
| `increment1.py` | — | The closed loop, with latency measurement |
| `assistant.py` | — | The same loop with the avatar, running continuously |

`tools/` holds a side quest: `applab.py` drives the board from the command
line the way Arduino App Lab's UI does (apps, bricks, AI models, resources)
through App Lab's local control server on `127.0.0.1:8800`. `applab_targets.py`
and `vscode-tasks.json` put those commands in the VS Code sidebar. Wiring
instructions are at the bottom of this file. It is optional and nothing in the
increment depends on it.

## Decisions this increment settled

**D2 is decided: Whistle (Cactus Compute).** Apache-2.0, 16.9 MB, 0.63 s per
3 s clip, and no torch stack. Moonshine was rejected on licence — CC BY-NC-SA
is not an open source licence and would block C5 and D5. Vosk was not needed.
Full comparison in [docs/measurements.md](docs/measurements.md#speech-to-text-d2-decided).

**Capture does not use PortAudio.** `sounddevice` and `pyaudio` need a shared
library that would require `apt` and therefore sudo on the board. Reading raw
frames from `arecord` into numpy avoids that completely.

**The headset cannot do 16 kHz natively.** Address it as `plughw:0,0`, never
`hw:0,0`, or ALSA silently gives you 48 kHz.

**Telemetry is off, in code.** `cactus-compute` reports anonymous usage counts
by default. No audio and no transcripts, but it is still an outbound call, and
C2/C4 promise none. `CACTUS_TELEMETRY=0` is set in `recognizer.py` before
`cactus` is imported, not in a shell profile someone can forget.

## The thing that will cost you time

The first run failed, usefully. Whistle transcribed the spoken word `forceps`
as **"Four steps."** The matcher rejected it and the patient said "Pardon?" —
correct behaviour, useless command.

The fix was in our matcher, not the recogniser: it compared single words only,
and `four` is far from `forceps` while `foursteps` is close. `commands.py` now
also compares adjacent words joined together, and carries an `ALIASES` table
of known mis-transcriptions.

**Every command word still needs to be spoken into the real headset and
checked against what Whistle returns.** Only `forceps` has been through this.
`swab`, `clamp`, `scalpel`, `steady` and `cancel` have not — and `cancel`
against `scalpel` looks like a candidate for confusion. Run `increment1.py -n 20`,
speak each command, and extend `ALIASES` with what you actually hear. That
same run produces the median and worst-case latency the criteria table wants.

Rejection stays safe meanwhile: "banana bread" (0.55) and "The weather is nice
today" (0.60) are correctly ignored, which matters for co-op, where the two
players talk to each other constantly.

## Two failures the room found for us

Running this with an open microphone in the hackathon room broke it twice, in
ways worth knowing about before you build on it. Both are fixed; the detail
is in [docs/measurements.md](docs/measurements.md#voice-gating-two-real-failures-both-fixed).

**Whistle hallucinates on silence.** Listening to a quiet room it returned
"Thank you." again and again. Hence the VAD gate and a hallucination list.

**Ordinary conversation triggered a command.** The French `pas` in
"Je ne sais pas si vous voyez" matched `pause` at the old 0.75 threshold and
paused the game. The threshold is now 0.82 with a length guard. Ten minutes
of German and French conversation afterwards produced no false triggers.

⚠ The headset picks up the whole room, not just the wearer. The plan assumed
a close-talking mic would handle hall noise; it does not on its own, and the
rejection logic is what makes it usable. **Do not loosen the threshold
without re-testing in noise.**

## What this increment does not do

No `SignalProcessor` yet (high-pass, normalisation), and the VAD is a plain
energy gate rather than Silero or WebRTC. Recording is still a fixed window,
not speech-triggered. No `EventBus`, `Service` or `App`; the loop calls the
classes directly. No MCU, no Bridge, no game. Those are the next slices, and
their interfaces are already agreed in
[PLAN.md](../PLAN.md#interfaces-agree-on-these-first-so-we-can-work-in-parallel).

## Optional: the App Lab commands in VS Code

Two lines in `firmware/platformio.ini` add them to PROJECT TASKS > Custom.
The `arduinoq` platform refuses to load on a non-Linux host, so they need
their own environment:

```ini
[env:applab]
platform = native
extra_scripts = pre:../increment1/tools/applab_targets.py
build_src_filter = -<*>
```

Add `default_envs = uno_q` under a `[platformio]` section so a plain `pio run`
ignores it. For the command palette instead, merge `tools/vscode-tasks.json`
into `.vscode/tasks.json`.
