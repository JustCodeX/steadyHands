# Linux app

The part of the surgeon trainer that runs on the UNO Q's Linux side: game, display, speech, and sound. It talks to the MCU sketch in [`../firmware`](../firmware) over the Bridge.

## Structure

Every feature is a class derived from `Service`. Services are registered with `App` and communicate only through events on the `EventBus`.

| Package | Contents |
| --- | --- |
| `trainer/core/` | `App`, `Service`, `EventBus`, event classes, config |
| `trainer/hardware/` | `McuLink`: Bridge client for the MCU |
| `trainer/voice/` | Microphone, signal processing, VAD, speech-to-text, command matching |
| `trainer/audio/` | Pre-rendered patient lines and spoken results |
| `trainer/game/` | Game engine, modes, levels, patient, training metrics |
| `trainer/game/instruments/` | `Instrument` and one subclass per instrument |
| `trainer/ui/` | Rendering on the HDMI display |
| `trainer/system/` | Idle mode, latency, CPU, and RAM logging |
| `tests/` | Unit tests (pytest) |

Class diagrams and the recipe for new features: [PLAN.md](../PLAN.md#code-design).

## Status

Only the package structure exists so far. The setup (Python environment on the board, models) and the start script follow in M0.
