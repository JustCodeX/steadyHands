# Headset audio: what is wrong and how we fix it

Status, 13 Nov 2026: steps 1 to 3 are implemented on branch `audio/headset-recovery` and covered by unit tests. The checks on the board are still open; see "Board checks" at the end. Step 4 is not started.

## Summary

The headset (JBL Tune 530C, USB) has three separate problems. Together they explain why sound "worked earlier" and then stopped without any hardware change.

| # | Problem | Effect | Fix |
|---|---|---|---|
| 1 | The USB hub refuses the headset in most boots | No headset on the board at all | Restart the USB port automatically until the headset appears (step 3) |
| 2 | The board's saved default output was its own line-out | No sound in the headset even when it was connected | Fixed on the board; make it part of setup (step 2) |
| 3 | The game records from the board's built-in input, not the headset mic | No voice command has ever been recognised on the board | Record from the headset at 48 kHz and convert to 16 kHz (step 1) |

Work order: step 1 first, because it needs the headset connected and no reboot. Step 3 last, because testing it means rebooting, which loses the current working state.

## What we measured

All times are the board clock (UTC).

### Problem 1: the hub

- The headset is on hub port `1-1.3`, the display's touch panel on `1-1.1`. In a bad boot the kernel logs `device descriptor read/64, error -32` and `unable to enumerate USB device` for both. The hub's built-in Ethernet keeps working.
- 3 of 10 boots connected the headset: 14:38, 16:28, 17:49. The other 7 did not.
- Kernel logs of good and bad boots are identical up to the point where the hub is asked for the devices. Cold start versus warm reboot does not predict the result.
- In a bad boot, replugging the headset into the same port fails every time.
- Restarting only the board's USB port re-rolls the hub, like a reboot does:
  ```sh
  echo device | sudo tee /sys/class/usb_role/4e00000.usb-role-switch/role
  ```
  The host-mode service switches the port back within 3 s. On 13 Nov this took 9 tries: 8 failed, the 9th connected headset and touch.
- The hub has no free port, so moving the plug is not an option.
- What inside the hub decides good or bad is unknown. It cannot be seen from software.

### Problem 2: default output

- `~/.local/state/wireplumber/default-nodes` on the board named the built-in line-out as the configured default output. A configured default wins over a newly connected device.
- In the boot at 17:49 the headset was connected for about 70 s and a round was played, but nothing was heard.

### Problem 3: microphone

- `AudioInput` opens the PortAudio default input at 16 kHz. On the board that is the built-in input `hw:0,2`, where nothing is plugged in.
- The headset mic supports 48 kHz mono only. Opening it at 16 kHz fails with `Invalid sample rate`. Recording at 48 kHz works (tested, 1.5 s).
- `logs/trainer.log` on the board has no `command ...` line, and all 10 logged rounds show `calls_correct=0, calls_wrong=0`.

- Found while testing step 1 on the board (13 Nov, 18:30 UTC): the built-in input delivers no audio at all. A stream on it opens and reports "active", but its callback is never called, at 16 kHz and at 48 kHz. Closing such a stream with `stop()` blocks for 64 s; `abort()` returns at once. So without the headset the old code also stalled the voice thread for a minute each time listening ended. `AudioInput.stop()` now uses `abort()`.

### Why nobody noticed

The trainer logs `audio out ready` and `microphone open` in every case, because it falls back to the built-in card without saying so.

## Already done on the board

- Headset set as default output with `wpctl set-default`. The game's audio stream moved to the headset at once. The setting is saved; when the headset is missing, output falls back to the line-out.
- The USB port restart brought the headset up at about 18:01. This state lasts only until the next reboot or power cycle.

## Plan

### Step 1: record from the headset microphone

Files: `app/trainer/voice/audio_input.py`, `app/trainer/core/config.py`, `app/tests/test_voice_pipeline.py`.

1. **Pick the headset.** `VoiceConfig.input_device` already takes a name fragment. Give it the default `"USB Audio"`, which matches `JBL Tune 530C: USB Audio (hw:1,0)` and any other USB headset. If no such device exists, keep today's fallback to the default input and log a warning.
2. **Convert the rate.** Try to open the device at 16 kHz. If that fails, open it at its own rate (48 kHz for the JBL) and convert each block to 16 kHz inside `AudioInput`: low-pass filter, then keep every third sample. The filter keeps its state between blocks. NumPy only, no new dependency. The rest of the pipeline (`SignalProcessor`, VAD, recogniser) keeps receiving 16 kHz blocks of 320 samples and does not change.
3. **Find a headset that appears late.** With step 3 the headset can show up after the game has started. PortAudio keeps the device list it read at start, so `AudioInput.start()` must re-read the list when the wanted device is not in it.
4. **Say what is used.** Log the device name and both rates, for example `microphone open: JBL Tune 530C, 48000 -> 16000 Hz`.

Tests:
- Converter: a 1 kHz tone at 48 kHz comes out at 16 kHz with the right length and level; a 10 kHz tone is strongly reduced.
- Device choice with a fake device list: headset present, headset missing, headset appearing on the second try.

Check on the board: start a round, say each tool word, and expect lines such as `command forceps (0.85)` in `logs/trainer.log`.

This does not touch the speech engine. That choice stays with Timon (D2 in `PLAN.md`).

### Step 2: make the output setting part of setup, and make the fault visible

Files: `app/setup/board_setup.sh`, `app/trainer/audio/sound_service.py`.

1. `board_setup.sh` sets the headset as default output when it is connected, and prints a hint when it is not.
2. At start, `SoundService` checks whether a USB sound card is present (`/proc/asound/cards`). If not, it logs a warning: no headset on the bus, sound goes to the board's line-out.

Check: unplug the headset, start the trainer, the warning is in the log. Plug it in, restart, the warning is gone and sound is in the headset.

### Step 3: bring the headset up on every boot

Files: `app/setup/usb-host-mode.sh` (installed as `/usr/local/bin/steadyhands-usb-host.sh`, runs as root), `app/setup/board_setup.sh`, `docs/board-cheatsheet.md`.

1. Extend the existing loop. When a hub port has a device attached that failed to connect, write `device` to the role file, let the loop switch it back to `host`, wait about 10 s, and check again.
2. Stop after 15 tries per incident and write one line to the journal with the number of tries and the result.
3. Do nothing when no device is attached, so an unplugged headset does not cause restarts.
4. Reinstall with step 1 of `board_setup.sh`. This asks for the board password.
5. Add the manual command and the meaning of the journal line to the cheat sheet.

How the script recognises "attached but failed": the port files `/sys/bus/usb/devices/*/*:1.0/*-port*/state`. Read on the board in a bad boot (13 Nov, 18:20 UTC): the two failed ports `1-1-port1` and `1-1-port3` read `default`, empty ports read `not attached`, working ports read `configured`. The script treats every other value than `not attached` and `configured` as failed, and acts only when two looks 3 s apart agree, because a port passes through `default` while a device connects normally.

Check: reboot 10 times. The headset is present within 3 minutes after each boot, and the journal shows how many tries each boot needed.

Side effects to verify:
- Each restart disconnects the hub's Ethernet and the touch panel for a few seconds. Wi-Fi and HDMI are not affected.
- The game starts about 12 s after boot, possibly before the headset is up. Output should move to the headset by itself once it appears (it did when the default was switched). The microphone is covered by step 1.3.

### Step 4: refine the voice commands for the tools

Separate task, after step 1 works on the board. Today's words are forceps/tweezers, swab/sponge, clamp, scalpel/knife (`DEFAULT_COMMANDS` in `app/trainer/core/config.py`).

## Risks and open points

- **The retry is a workaround.** The numbers are small (1 in 9 port restarts, 3 in 10 boots), so a boot may need many tries. The real fix is a hub that does not show the fault. Ask the organisers for a second hub to compare.
- **Until step 3 is installed, do not reboot or power-cycle the board** when the headset is working. If it is lost, run the manual command above until `grep USB-Audio /proc/asound/cards` prints a line.
- **Screen lock.** After idle mode blanks the display, the desktop locks and the game is blocked until someone logs in on the HDMI screen. This is a separate problem and still needs a decision on turning the locker off.

## Board checks

To be filled in on the board. A row counts only when it was seen there.

| Check | Result |
|---|---|
| New app code on the board (`sync_to_board.sh`) | done, 18:35 UTC |
| Without headset: warning in the log, default input used, `stop()` returns at once | done: 3 start/stop cycles, 0.01 s each |
| Device list is read again with the real audio library | done: 0.07 s |
| Service installed (`/usr/local/bin/steadyhands-usb-host.sh` is the new script) | done, 18:42 UTC |
| Headset comes up through port restarts; journal shows the number of tries | done once: `no failed hub port left after 9 port restart(s)` at 18:44:07, 1 min 51 s after the service start. Headset and touch panel both connected. |
| Sound in the headset after it came up while the game was running | routing done: `wpctl status` shows the game's stream on the JBL sink without a restart. Nobody has listened yet. |
| Headset microphone through `AudioInput` (test script on the board) | done: `JBL Tune 530C: USB Audio (hw:1,0), 48000 -> 16000 Hz`, 100 blocks of 320 samples in 2 s, signal present |
| `microphone open: JBL ..., 48000 -> 16000 Hz` in `trainer.log` | done after the reboot at 18:47 UTC: `microphone open: JBL Tune 530C: USB Audio (hw:0,0), 48000 -> 16000 Hz` on every listening phase |
| `command <word>` lines in `trainer.log` when the tool words are spoken | partly: `command cancel (1.00)` at 18:49:19 and `command scalpel (1.00)` at 18:49:28, the first voice commands ever logged on the board. Forceps, swab and clamp not seen yet. |
| 10 reboots, headset present within 3 minutes each time | 1 of 10: the reboot at 18:47 connected the headset at once, so the service had nothing to do. A boot that needs the restarts has not been seen with the service installed. |
