# UNO Q cheat sheet: power, deploy, run

Personal reminder. The full docs are in [firmware/README.md](../firmware/README.md) and [app/README.md](../app/README.md).

## Power

- **On:** plug the USB-C PD power supply into the hub. The hub powers the board. Wait for the desktop to appear on the HDMI display; the trainer starts by itself (autostart).
- **Off:** shut the board down first, then unplug the supply.
  ```sh
  ssh arduino@192.168.1.235            # or: firmware/tools/board.sh shell
  sudo shutdown -h now                 # asks for the board password
  ```
  Wait until the board's LEDs go off, then unplug the supply.
- Do not just pull the power while it runs. Our docs have no power switch.
- Idle mode only switches the display off. The board stays on.

## Connect

- **USB (adb):** `adb devices` should list the board. Works only before `board_setup.sh` has run.
- **Wi-Fi (SSH):** join the hall Wi-Fi "Hackerthon", then `export BOARD_SSH=arduino@192.168.1.235`. The IP can change, so check it on the board. After `board_setup.sh`, USB adb is disabled, so use SSH.

## Deploy the MCU firmware (from your Mac)

```sh
cd promptpimps-unoq/firmware
tools/board.sh build      # compile on the board
tools/board.sh upload     # compile and flash
tools/board.sh monitor    # serial output, Ctrl+C to quit
```

Do not start App Lab apps while our sketch is in use, because App Lab overwrites the sketch.

## Deploy the Linux app (from your Mac)

```sh
cd promptpimps-unoq
app/tools/sync_to_board.sh          # copies app/ and levels/ to ~/promptpimps-unoq on the board
```

Then restart the trainer on the board:

```sh
pkill -f '[-]m trainer'; app/run.sh     # run on the board; log: app/logs/trainer.log
```

## Setup (only once per board)

- `firmware/tools/board.sh setup`, then the router-group fix from [firmware/README.md](../firmware/README.md).
- On the board: `cd ~/promptpimps-unoq/app && setup/board_setup.sh` (needs the board password).
