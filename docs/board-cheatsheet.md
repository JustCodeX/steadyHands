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

## No sound in the headset

The workshop USB hub refuses the headset and the touch panel in most boots. The root service `steadyhands-usb-host` restarts the board's USB-C port until both are connected (up to 15 tries, about 12 s each). Each try drops the hub's Ethernet and the touch panel for a few seconds; Wi-Fi and HDMI stay up.

```sh
grep USB-Audio /proc/asound/cards              # prints a line = headset is connected
journalctl -u steadyhands-usb-host -n 10       # what the service did
```

| Journal line | Meaning |
|---|---|
| `failed hub port(s) 1-1-port1 1-1-port3: port restart 4 of 15` | Devices on these ports did not connect; try 4 is running. |
| `no failed hub port left after 4 port restart(s)` | Connected after 4 tries. |
| `gave up after 15 port restart(s); still failed: ...` | No luck. Start 15 new tries with the command below. |

```sh
sudo systemctl restart steadyhands-usb-host    # 15 new tries (board password)
# one try by hand:
echo device | sudo tee /sys/class/usb_role/4e00000.usb-role-switch/role
```

- Headset connected but silent: `wpctl status` must show the JBL sink with a `*`. If not, `wpctl set-default <id>` (or run `setup/board_setup.sh` again).
- `app/logs/trainer.log` names the microphone in use (`microphone open: JBL Tune 530C ..., 48000 -> 16000 Hz`) and warns with `no USB headset on the bus` when sound goes to the line-out.
- After changing `app/setup/usb-host-mode.sh`, install it again (board password):
  ```sh
  cd ~/promptpimps-unoq/app && sudo install -m 755 setup/usb-host-mode.sh /usr/local/bin/steadyhands-usb-host.sh && sudo systemctl restart steadyhands-usb-host
  ```
