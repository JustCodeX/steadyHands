# UNO Q MCU firmware (PlatformIO)

Arduino sketch for the UNO Q's STM32U585 microcontroller, for buttons, LEDs, and other real-time I/O. Speech processing runs on the board's Linux side, not here.

This project uses the unofficial [`lee-lab-skku/arduinoq`](https://github.com/lee-lab-skku/platform-arduinoq) PlatformIO platform. Its toolchain runs only on Linux, and flashing goes through OpenOCD on the board's own Linux side. As a result, `pio run` cannot build on macOS. `tools/board.sh` copies this folder to the board over USB (adb) and runs PlatformIO on the board. The Git repository on your computer remains the source of truth; the copy on the board is overwritten on each run.

## Usage

```sh
cd firmware
tools/board.sh build      # compile
tools/board.sh upload     # compile and flash
tools/board.sh monitor    # Serial output (Ctrl+C to quit)
tools/board.sh reset      # reset the MCU without building
tools/board.sh pio ...    # any other pio command, run on the board
```

`adb` is taken from your `PATH` or from the Arduino App Lab/IDE installation (`~/Library/Arduino15/packages/arduino/tools/adb`). Set `ANDROID_SERIAL=<serial>` if several boards are connected; list them with `adb devices`.

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

- `Serial` is routed over the MCU↔Linux RouterBridge (`socket://localhost:7500` on the board), not a USB serial port.
- The UNO Q RGB LEDs are `LED3_R/G/B` and `LED4_R/G/B`. `LED_BUILTIN` is defined.
- The sketch has 768 KiB flash and 256 KiB RAM; the Zephyr firmware uses the rest.
