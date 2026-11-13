# Linux app

The part of the surgeon trainer that runs on the UNO Q's Linux side: game, display, speech and sound. It talks to the MCU sketch in [`../firmware`](../firmware) over the Router Bridge, as a plain Python program (no App Lab container).

## Structure

Every feature is a class derived from `Service`. Services are registered with `App` and communicate only through events on the `EventBus` (`trainer/core/events.py` lists them all). Events carry numbers and short identifiers only, never audio or transcripts.

| Package | Classes |
| --- | --- |
| `trainer/core/` | `App`, `Service`, `EventBus`, the event dataclasses, `config.py` (every setting, TOML overrides) |
| `trainer/hardware/` | `McuLink` (Bridge client), `KeyboardInput` (dev mode and demo fallback) |
| `trainer/voice/` | `AudioInput`, `SignalProcessor` (high-pass, level normalisation), `EnergyVad` + `Segmenter`, `SpeechRecognizer` → `VoskRecognizer` / `EnsembleRecognizer` / `NullRecognizer`, `CommandInterpreter` → `CommandMatcher`, `VoiceService` |
| `trainer/quiz/` | `Question` + `QuestionBank` (`assets/questions.json`), `AnswerEvaluator` → `KeywordEvaluator` |
| `trainer/audio/` | `lines.py` (every spoken line), `ClipLibrary`, `PhraseBuilder`, `SoundService`, `TtsRenderer` (setup only) |
| `trainer/game/` | `GameEngine`, `GameState`, `SoloMode` / `CoopMode`, `Level` + `LevelCatalog`, `CollisionMap`, `Patient`, `TrainingMetrics`, `QuizDirector` (when to ask, answer window), `Stress`, `ActionCatalog` (the commands as tool schemas) |
| `trainer/game/instruments/` | `Instrument` and `Forceps`, `Swab`, `Clamp`, `Scalpel` |
| `trainer/ui/` | `Renderer` (picks the screen), `MenuScreen`, `RoundView`, `Hud`, `PauseOverlay`, `ResultScreen`, `MapPainter` (level mask → wound picture), `Fonts`, `theme.py` |
| `trainer/ui/art/` | Artwork drawn with code and cached: `InstrumentArt`, `TargetArt`, `PatientArt`, `Glyphs`, `Backdrop`, `canvas.py` (drawing helpers) |
| `trainer/system/` | `PowerManager` (idle mode), `MetricsLogger` (latency, CPU, RAM per state → `logs/metrics.csv`) |
| `tools/` | `make_levels.py`, `render_clips.py`, `bridge_probe.py`, `sync_to_board.sh` |
| `setup/` | `board_setup.sh`, `download_models.sh` |
| `tests/` | pytest suite, runs headless on any computer |

Class diagrams and the recipe for new features: [PLAN.md](../PLAN.md#code-design).

## Setup on the board

Copy the repo to the board (`app/tools/sync_to_board.sh` mirrors `app/` and `levels/` over USB, or over Wi-Fi with `BOARD_SSH=arduino@<board-ip>` set; or `git clone` on the board), then on the board:

```sh
cd ~/promptpimps-unoq/app
setup/board_setup.sh       # apt packages (sudo), autologin for :0, venv, models, levels, clips
```

The setup needs the board password once (for `apt`, the autologin file, and the USB host-mode service). The board's USB-C port falls back to device mode, which disconnects the hub's USB devices (headset, touch); USB adb does the same, so adbd is disabled and a small root service keeps the port in host mode. The same service restarts the port when the hub fails to connect the headset or the touch panel at boot (see [the cheat sheet](../docs/board-cheatsheet.md#no-sound-in-the-headset)). Use SSH (`BOARD_SSH`) instead of USB adb on a board set up this way. It downloads the Vosk small English model (40 MB) and the Piper voice (60 MB) into `app/models/` (git-ignored) and renders every patient line to `assets/clips/` once. Nothing is downloaded or synthesised during play.

## Running

On the board the trainer starts with the desktop (`~/.config/autostart/steadyhands.desktop`, installed by the setup). To restart it by hand, stop the running one first; output goes to `app/logs/trainer.log`.

```sh
pkill -f '[-]m trainer'; app/run.sh    # on the board: fullscreen on the HDMI display, MCU, voice, sound
app/run.sh --windowed -v          # window, verbose log
python -m trainer --no-mcu --no-voice --windowed   # on a laptop: keyboard only
```

Controls without voice: tilt moves, the knob picks the instrument (while paused it sets the steering speed), a knob press switches on the light in dark zones, A uses the instrument, B pauses, C also steps to the next instrument.

Keyboard: arrows tilt (Shift = slow), Space = A, M = B, C = C, +/- turn the knob, Enter presses it. As if spoken: 1-4 call tools, L light, S steady, X cancel, R repeat, H help, N new game. Y and U answer the open quiz question right and wrong. Esc quits.

Settings: copy the defaults from `trainer/core/config.py` into a TOML file and pass `--config file.toml` (or set `STEADYHANDS_CONFIG`). Typical overrides: `voice.input_device = ""` (default input instead of the USB headset), `audio.output_device`, `game.speed_px_per_s`, `voice.confidence_threshold`, `mcu.tool_leds = true` (show the active tool on the Modulino Buttons LEDs).

Wall contact plays a generated buzz through the audio output (`trainer/audio/sound_service.py`, `make_buzz_bytes`).

## Tests

```sh
cd app && python -m pytest        # headless: SDL dummy drivers are set in tests/conftest.py
```

## M0 checks on the board

```sh
app/.venv/bin/python app/tools/bridge_probe.py 5    # frames/s from the MCU, then button-LED and voice-state test
```
