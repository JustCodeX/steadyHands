# UNO Q MCU firmware (PlatformIO)

Sketch for the UNO Q's STM32U585: reads the Modulinos, filters the tilt, streams input frames to Linux over the Bridge, and drives the horn, the red LED and the on-board voice-state LED. Speech and the game run on the Linux side ([`../app`](../app)).

This project uses the unofficial [`lee-lab-skku/arduinoq`](https://github.com/lee-lab-skku/platform-arduinoq) PlatformIO platform. Its toolchain runs only on Linux, and flashing goes through OpenOCD on the board's own Linux side. As a result, `pio run` cannot build on macOS. `tools/board.sh` copies this folder to the board over USB (adb) and runs PlatformIO on the board. The Git repository on your computer remains the source of truth; the copy on the board is overwritten on each run.

## Usage

```sh
cd firmware
tools/board.sh build      # compile
tools/board.sh upload     # compile and flash
tools/board.sh monitor    # Monitor output (Ctrl+C to quit)
tools/board.sh reset      # reset the MCU without building
tools/board.sh pio ...    # any other pio command, run on the board
```

Host unit tests for the pure C++ parts (filter, frame, module list) run on your computer without the board:

```sh
uvx --from platformio pio test -e native     # or: pio test -e native
```

`adb` is taken from your `PATH` or from the Arduino App Lab/IDE installation (`~/Library/Arduino15/packages/arduino/tools/adb`). Set `ANDROID_SERIAL=<serial>` if several boards are connected; list them with `adb devices`.

**Over Wi-Fi instead of USB:** put your SSH public key into the board's `~/.ssh/authorized_keys` once (over the cable), then set `BOARD_SSH=arduino@<board-ip>` in your shell. Every `board.sh` command then runs over SSH and the data cable can stay unplugged. The board's adb daemon has no TCP mode, so SSH is the only wireless route.

## What the sketch does

| Module (`lib/`) | Hardware | Behaviour |
| --- | --- | --- |
| `TiltSensor` | Modulino Movement, in the instrument | 100 Hz accelerometer, 5 Hz low-pass, tilt in g |
| `KnobInput` | Modulino Knob | Position and push button |
| `ButtonPanel` | Modulino Buttons | A/B/C and their LEDs (active tool) |
| `DistanceSensor` | Modulino Distance (optional) | Hand height in mm |
| `Alarm` | D6 red LED, D9 horn | Both on together for *n* ms |
| `StatusLed` | On-board RGB LED 4 | Off / green pulsing (listening) / yellow (processing) / blue (speaking) |
| `BridgeLink` | Router Bridge | 50 Hz `input` frames to Linux; `alarm`, `leds`, `voice_state`, `ping`, `status` from Linux |

Modulinos that are missing at boot are retried every 2 s. Every tunable (pins, rates, filter cutoff, horn type) is in [`lib/Core/Config.h`](lib/Core/Config.h). Set `HORN_PASSIVE = true` for a passive piezo (driven with `tone()`), and `RGB_ACTIVE_LOW = true` if LED 4 shows inverted colours.

### Bridge interface

```
MCU -> Linux   notify  input(tilt_x: float, tilt_y: float, knob: int, buttons: int,
                             distance_mm: int, sensors_ok: int, seq: int)
Linux -> MCU   alarm(ms: int) -> bool        horn + red LED
               leds(mask: int) -> bool       button LEDs, bit 0..2 = A..C
               voice_state(s: int) -> bool   0 off, 1 listening, 2 processing, 3 speaking
               ping() -> int                 millis()
               status() -> int               sensor bit mask (1 tilt, 2 knob, 4 buttons, 8 distance)
```

`buttons` bits: 1 = A, 2 = B, 4 = C, 8 = knob pressed. The Linux client is `app/trainer/hardware/mcu_link.py`; `app/tools/bridge_probe.py` exercises the link without the game.

## One-time setup on each board

1. Install PlatformIO Core for the board's `arduino` user at `~/.platformio/penv`. The board image has no `pip`, so the script takes Debian's pip wheel and needs no `sudo`:

   ```sh
   tools/board.sh setup
   ```

2. Allow the `arduino` user to use the router socket that uploads need. Flashing fails with `Permission denied` on `/var/run/arduino-router.sock` until you do this. It asks for the board password and reboots the board:

   ```sh
   tools/board.sh shell
   sudo usermod -aG arduino-router arduino && sudo reboot
   ```

The first `tools/board.sh build` downloads the platform and toolchain to the board, which takes about 8 minutes. Later builds take seconds.

## Notes

- **Libraries.** The platform installs its own patched `Arduino_RouterBridge`, `Arduino_RPClite` and `MsgPack` into `.pio/libdeps/` on every build; never add or vendor them (a copy of `DebugLog` in `lib/` breaks the build). `Arduino_Modulino` and the sensor libraries its header includes come from the PlatformIO registry via `platformio.ini`.
- **`Serial` is the Bridge monitor.** On the UNO Q, `Serial`/`Monitor` is a channel over the RouterBridge, proxied to `socket://localhost:7500` on the board. Only files that can see the RouterBridge header get `Serial`, so a third-party library that uses `Serial` in its `.cpp` does not build. `Modulino.h` pulls in one such library (`Arduino_LTR381RGB`, the light sensor); it is ignored in `platformio.ini` and `lib/LTR381RGBStub/` supplies the header.
- **Do not start App Lab apps** while our sketch is in use; App Lab flashes its own sketch. `tools/board.sh upload` puts ours back.
- The UNO Q RGB LEDs are `LED3_R/G/B` and `LED4_R/G/B`. The sketch has 768 KiB flash and 256 KiB RAM; the Zephyr firmware uses the rest.
