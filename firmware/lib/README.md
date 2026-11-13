# Firmware modules

Each hardware module is its own PlatformIO library in its own folder, so features stay separate and can be added one at a time. PlatformIO finds them automatically.

```
lib/<Name>/<Name>.h
lib/<Name>/<Name>.cpp
```

## Planned modules

| Library | Classes | Role |
| --- | --- | --- |
| `Core` | `Module`, `InputSource`, `InputFrame`, `Firmware`, `LowPassFilter` | Interfaces, the shared input frame, the loop that updates all modules |
| `TiltSensor` | `TiltSensor` | Modulino Movement: filtered tilt |
| `KnobInput` | `KnobInput` | Modulino Knob |
| `ButtonPanel` | `ButtonPanel` | Modulino Buttons and their LEDs |
| `DistanceSensor` | `DistanceSensor` | Modulino Distance (optional) |
| `Alarm` | `Alarm` | Horn and red LED, timed without blocking |
| `StatusLed` | `StatusLed` | Voice state on the on-board RGB LED 4 |
| `BridgeLink` | `BridgeLink` | Sends `InputFrame` to Linux; receives `alarm`, `leds`, `voice_state` |

## Adding a module

1. Create `lib/<Name>/` with a class that derives from `Module`, or from `InputSource` for inputs.
2. For an input, add its field to `InputFrame`.
3. Construct the module in `src/main.cpp` and register it with `firmware.add(...)`.

Never use `delay()` in a module; use `update(nowMs)` instead, so the loop is never blocked.

Class diagram: [PLAN.md](../../PLAN.md#firmware-mcu-c-platformio).
