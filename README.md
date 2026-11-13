# promptpimps-unoq

PromptPimps hackathon project on the Arduino UNO Q. We are building a local speech prototype for the Speech-to-Speech hackathon (13–14 November 2026, Nürnberg). The topic isn't fixed yet. The leading idea is a steady-hand game with an external LCD and sensors.

## Layout

| Path | What runs there |
| --- | --- |
| [`firmware/`](firmware/) | Arduino sketch for the STM32U585 MCU (PlatformIO): LCD, sensors, buttons, LEDs |

Speech processing (speech-to-text, logic, text-to-speech) will run on the board's Debian Linux side. Its folder will be added once the topic is fixed.

## Quick start

```sh
cd firmware
tools/board.sh setup     # once per board
tools/board.sh upload    # build and flash over USB
tools/board.sh monitor   # Serial output
```

See [firmware/README.md](firmware/README.md) for details and the one-time permission step on each board.
