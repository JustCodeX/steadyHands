# Firmware libraries

One PlatformIO library per class, as in [PLAN.md](../../PLAN.md#firmware-mcu-c-platformio). Every class lives in the `sh` namespace (the Modulino library already has a global `Module`).

| Folder | Class | Job |
| --- | --- | --- |
| `Core/` | `Module`, `InputSource`, `InputFrame`, `Firmware`, `LowPassFilter`, `Config.h` | Interfaces, the frame, the module list, the filter, every tunable |
| `TiltSensor/` | `TiltSensor` | Modulino Movement in the instrument, filtered tilt |
| `KnobInput/` | `KnobInput` | Modulino Knob position and button |
| `ButtonPanel/` | `ButtonPanel` | Modulino Buttons A/B/C and their LEDs |
| `DistanceSensor/` | `DistanceSensor` | Modulino Distance (optional) |
| `Alarm/` | `Alarm` | Horn and red LED |
| `StatusLed/` | `StatusLed` | On-board RGB LED 4 for the voice state |
| `BridgeLink/` | `BridgeLink` | Frames to Linux, commands from Linux |

**Third-party libraries are not vendored here.** The `arduinoq` PlatformIO platform installs its own patched `Arduino_RouterBridge`, `Arduino_RPClite` and `MsgPack` into `.pio/libdeps/` on every build, and the Modulino libraries come from the registry via `platformio.ini`. A copy of `DebugLog` in `lib/` would shadow the core's no-op shim and break the build.

Missing Modulinos are not fatal: a module reports "not found" and retries every 2 s, so you can plug the chain in after boot (power off first, see WIRING.md).
