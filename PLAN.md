# Plan: Steady Hands (working title)

Draft of 13 November 2026, from our team discussion. ✅ marks a decision; ❓ marks a question still open. Wiring is in [WIRING.md](WIRING.md).

## The idea in one sentence

You guide a surgical instrument through a patient map on a 7-inch screen by tilting the instrument in your hand, and you call for tools by voice. Everything runs offline on the Arduino UNO Q.

> The game is inspired by classic steady-hand operation games. We use our own name, patient, and artwork, so we can publish the build and demo it publicly.

## Why it is worth building

- **It brings people together.** In co-op mode, the surgeon and the assistant only win if they talk to each other.
- **It is inclusive.** The assistant plays by voice only and needs no steady hands. People with a tremor or limited hand mobility, and young children, can play as equals.
- **It is offline and private.** Nothing goes to the internet or the cloud, and no audio is stored. It can be used where there is no reliable internet, such as a children's ward, a care home, or a school.
- **It is energy-aware.** Speech recognition runs only while a round is in progress and someone is speaking, and we measure the energy used (see [Energy and environment](#energy-and-environment)).
- ❓ **Setting for the pitch.** Proposal: a children's hospital waiting room, where children and parents play together and get to know the instrument names in a playful way. We claim no clinical benefit.

## Decisions

| Topic | Decision |
| --- | --- |
| ✅ Language | English |
| ✅ Players | One-player surgeon mode; two-player co-op as an extra mode |
| ✅ Listening | The mic listens all the time while a round runs, and is off in menus and idle |
| ✅ Where speech runs | On the UNO Q's Linux side; the Nicla Voice is dropped |
| ✅ Audio | Headset |
| ✅ Display | Elecrow 7" IPS, HDMI, 1024×600 |
| ✅ Energy measurement | PeakTech digital multimeter (see [WIRING.md](WIRING.md#energy-measurement-with-the-peaktech)) |
| ❓ D1 Toolchain | App Lab app, or PlatformIO sketch plus standalone Python (see [D1](#d1-toolchain)) |
| ❓ D2 Speech-to-text | Whistle or Vosk, chosen after the M0 test (see [Speech pipeline](#speech-pipeline)) |
| ❓ D3 Name and setting | "Steady Hands" is a placeholder |
| ❓ D4 Audio for the audience | Headset audio only reaches the person wearing it. Does the display have an audio jack, or can we get a USB speaker? |

## Gameplay

### One-player mode

The surgeon holds the **instrument**, a handle containing the Modulino Movement, and tilts it to steer the tool tip through the corridors of the patient map. The surgeon wears the headset and calls for tools. Touching a wall sounds the horn, flashes the red LED, makes the patient react ("Ouch!"), and raises the patient's heart rate. After three touches, the patient wakes up and the round is lost. Removing every item before time runs out wins.

### Co-op mode (two players)

- The **surgeon** only steers.
- The **assistant** wears the headset and runs the operating room by voice: hands over tools, switches on the light, and calls "steady" for precision mode.
- The surgeon has to ask for what they need ("Clamp, quick!"), so the players talk to each other and the game listens to the assistant.

### Controls

| Input | Action |
| --- | --- |
| Modulino Movement (in the instrument) | Tilt moves the tool tip |
| Modulino Knob | Steering sensitivity; scrolls in menus |
| Modulino Buttons A / B / C | A: grab or release · B: pause/menu (long press cycles tools as a voice fallback) · C: switch between one-player and co-op |
| Modulino Distance (optional, stretch) | Hand height sets depth: lower your hand to grab, raise it to travel |
| Voice | Tool and room commands (see below) |

### Voice commands

We picked words that sound different from each other. Every recognised command is shown on screen so the player sees what the game heard.

| Command | Effect |
| --- | --- |
| `forceps` | Grab tool: picks up items |
| `swab` | Clears blood that blocks a corridor |
| `clamp` | Stops a bleeding timer |
| `scalpel` | Opens a sealed passage (stretch) |
| `light` | Lights up a dark part of the map for a few seconds (co-op) |
| `steady` | Precision mode for a few seconds: slower, finer movement |
| `pause` · `continue` · `new game` · `help` · `repeat` | Game flow |

### Levels

Each level is a PNG mask with a small JSON file:
- the mask has black walls, white corridors, and coloured item spots,
- the JSON holds the start point, the items, and the tool each item needs.

Collision detection is a pixel lookup in the mask, so anyone on the team can draw levels. Target: three levels for the demo.

## Architecture

```mermaid
flowchart LR
  subgraph MCU["UNO Q MCU (STM32U585)"]
    S["Sensor loop 100 Hz<br/>tilt filtering"]
    O["Horn + red LED"]
  end
  subgraph MPU["UNO Q Linux (QRB2210)"]
    G["Game loop + rendering<br/>30 fps cap"]
    V["Voice service<br/>VAD, speech-to-text, command match"]
    A["Sound player<br/>pre-rendered patient lines"]
  end
  MOD["Modulinos<br/>Movement · Buttons · Knob · Distance"] -- "Qwiic I2C" --> S
  S -- "input frames 50 Hz (Bridge)" --> G
  G -- "alarm (Bridge)" --> O
  H["Headset mic"] --> V
  V -- "command events" --> G
  G -- "game events" --> A
  A --> HP["Headset / speaker"]
  G -- "HDMI" --> D["Elecrow 7-inch display"]
```

The MCU does the timing-critical input and output. Linux runs the game, the display, and speech. Because the display is HDMI, rendering has to happen on Linux.

### Interfaces (agree on these first so we can work in parallel)

MCU and Linux, over the Bridge:

| Direction | Message | Content |
| --- | --- | --- |
| MCU → Linux | `input` (50 Hz) | `tilt_x`, `tilt_y` (filtered), `knob`, `buttons` (bit mask), `distance_mm` |
| Linux → MCU | `alarm` | Duration in ms: horn and red LED on together |
| Linux → MCU | `leds` | Button LED mask, used to show the active tool |

Inside Linux, between the voice service and the game:

| Direction | Event | Content |
| --- | --- | --- |
| Voice → game | `command` | Command word and confidence |
| Game → voice | `listen` | `on`/`off`: listening runs only during a round |
| Game → sound | `event` | `hit`, `item_out`, `win`, `lose`, `help`, ... → plays the matching patient line |

### D1 Toolchain

The workshop slides changed the picture. The organisers' speech examples (Whistle speech-to-text, "Hey Arduino" keyword spotting) and the Python side of the Bridge are **App Lab apps**. When an App Lab app starts, App Lab compiles and flashes **its own** sketch. That would overwrite a sketch flashed with PlatformIO.

| | Option A: App Lab app | Option B: PlatformIO + standalone Python |
| --- | --- | --- |
| MCU sketch | `sketch/` in the app, built by App Lab | `firmware/` (already builds and flashes) |
| Linux side | Python app in App Lab's container; Bridge library included | Our own Python environment; we write a client for the Bridge socket |
| Organiser examples | Usable directly | Have to be ported |
| Help from mentors | Yes | Hardly; the platform is unofficial |
| Workflow | Edit in VS Code, deploy with `arduino-app-cli` over adb (script to be written) | `firmware/tools/board.sh` |

**Recommendation:** Option A. It is the official path, the examples work in it as they are, and the Arduino mentors at the event can help. The architecture and interfaces above stay the same either way. ❓ Decide at the start of M0.

## Speech pipeline

1. **Mic:** headset, 16 kHz mono, read only while a round runs.
2. **Gate:** voice activity detection (Silero VAD or WebRTC VAD). Speech-to-text runs only on detected speech segments.
3. **Speech-to-text (❓ D2):** we test both options in M0 on 20 spoken commands with real hall noise, then pick one.
   - **Whistle** (Cactus Compute; 16.9 MB model; 7 languages). The workshop shows it running on the UNO Q's Linux side, and the slides link the project. It transcribes freely, and we match the text against the command list.
   - **Vosk small English** with its vocabulary restricted to our commands. Restricting the vocabulary makes recognition more robust, and the model is small.
4. **Response:** every recognised command appears on screen. Target: under 1 s from the end of a word to the tool change (to be measured).
5. **Text-to-speech:** Piper with an English voice. We render all patient lines to WAV once at setup, so the game only plays files and there is no speech synthesis during play.
6. **Privacy:** audio exists only in memory. It is never written to disk and never sent anywhere.

No LLM: the patient's lines are scripted. This saves the most energy and keeps response times short.

## Energy and environment

**What we do:**
- Speech-to-text runs only during a round, and only when VAD detects speech.
- A fixed command list allows a small model.
- Patient lines are pre-rendered; there is no text-to-speech during play.
- Rendering is capped at 30 fps. The map is pre-rendered, so only the moving parts are redrawn.
- The MCU filters the sensors and sends 50 frames per second, so Linux does not poll.
- **Idle mode:** after 60 s without input, the display goes to standby and the mic is off. A button press wakes everything up.
- **Build:** we make the case and the instrument from cardboard and leftover material, use no batteries, and publish everything as open source.

**What we measure** (method in [WIRING.md](WIRING.md#energy-measurement-with-the-peaktech)):
- Power in four states: idle, menu, round without speech, round with speech.
- Energy per round in Wh.
- The saving from VAD, compared with running speech-to-text all the time.
- CPU use per state, as a software measure that does not need the multimeter.

We show the measured values in the demo. Only measured numbers go into the pitch.

## Work split

| Person | Area | Done when |
| --- | --- | --- |
| 1 | **Voice**: headset audio, VAD, speech-to-text, command matching, pre-rendered patient lines | Spoken commands arrive as `command` events with the measured response time |
| 2 | **Game and display**: game loop, levels, collision, on-screen display (heart rate, tool, time), modes | Three levels playable with keyboard controls before the hardware is ready |
| 3 | **Hardware and MCU**: Modulino chain, sketch, horn and LED, instrument handle, case | `input` frames arrive at 50 Hz; `alarm` works |
| 4 | **Integration, energy, pitch**: Bridge interfaces, start scripts, idle mode, measurements, demo script | Single-command start; measured values in the README; two-minute demo rehearsed |

## Milestones

Event end: 14 November, 12:00. The exact build cutoff is not published; ask the organisers.

| Milestone | Target | Done when |
| --- | --- | --- |
| **M0 Risk tests** | 13 Nov, about 15:00 | Each person has proven their riskiest part on the real board: a spoken word is recognised from the headset; tilt values arrive on Linux; a window appears full-screen on the Elecrow; the horn and LED switch. D1 and D2 decided. |
| **M1 First playable** | 13 Nov, about 20:00 | One-player mode works for one level: tilt steers, a wall touch sounds the horn and lights the LED, and one voice command changes the tool |
| **M2 Feature complete** | 14 Nov, about 03:00 | All commands; patient lines; three levels; co-op; idle mode |
| **M3 Demo ready** | 14 Nov, about 09:00 | Measured values in hand; polish done; demo script rehearsed. After that, only bug fixes. |

## Risks and fallbacks

| Risk | Fallback |
| --- | --- |
| Speech recognition unreliable in hall noise | Headset mic close to the mouth; restricted vocabulary (Vosk); every command visible on screen; button fallback for tools |
| Bridge or Modulino library does not work with PlatformIO (Option B) | Switch to Option A |
| Python rendering too slow on the board | Lower resolution or fps; redraw only the parts that change |
| Hub cannot power the display and headset | Separate 5 V USB charger for the display |
| Horn needs more than 5 V or too much current | Driver with a MOSFET, or replace it with a 5 V buzzer (see [WIRING.md](WIRING.md#horn)) |
| Not enough time | Cut in this order: distance sensor, scalpel, co-op extras. One-player mode with three tools is the minimum version. |

## Questions for the organisers

- Judging criteria and their weights; exact build cutoff; demo format and length.
- Can we borrow a USB-C power meter? A multimeter alone cannot easily measure the whole setup (see [WIRING.md](WIRING.md#energy-measurement-with-the-peaktech)).
- Is training in the cloud (for example Edge Impulse) allowed during development, given that no voice data may leave the device during use?

## Planned repo layout

```
firmware/   MCU sketch (PlatformIO, exists) or sketch/ for App Lab (D1)
game/       Game loop, rendering, modes (Python, Linux side)
voice/      VAD, speech-to-text, command matching, sound player
levels/     Level masks (PNG) + JSON
docs/       Measured values, demo script, pitch
```

## References

- Workshop slides "Hands-On with Arduino UNO Q", 13 November 2026 (the local PDF in the old hackathon folder)
- [UNO Q datasheet](https://docs.arduino.cc/resources/datasheets/ABX00162-ABX00173-datasheet.pdf) · [UNO Q documentation](https://docs.arduino.cc/hardware/uno-q/)
- [Arduino_Modulino examples](https://github.com/arduino-libraries/Arduino_Modulino/tree/main/examples) (version 0.10.0 in the workshop)
- [Cactus Whistle](https://huggingface.co/Cactus-Compute/whistle) · [Vosk models](https://alphacephei.com/vosk/models) · [Piper](https://github.com/OHF-Voice/piper1-gpl) · [Silero VAD](https://github.com/snakers4/silero-vad)
- [Elecrow 7" IPS (wiki)](https://elecrow.com/wiki/7inch_IPS_HD_Touch_Screen-D.html)
