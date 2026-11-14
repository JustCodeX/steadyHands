# Arduino Project Hub: page text

The text for [projecthub.arduino.cc](https://projecthub.arduino.cc/), field by field, so the page can be filled in by copy and paste. Upload it from a team member's Arduino account ("New project"). Keep it in step with the repo.

---

## Title

Steady Hands: an offline voice-controlled surgeon trainer on the UNO Q

## Short description

Steer an instrument with your hand, call for instruments and order drugs with a dose by voice. Speech AI runs fully offline on the Arduino UNO Q.

## Cover image and gallery

- Cover: `pitch/media/demo-poster.jpg`
- Gallery: `pitch/media/alarm.png`, `pitch/media/readback.png`, `pitch/media/result.png`, `pitch/media/menu.png`
- Video: `pitch/media/demo.mp4` (45 s, upright), uploaded to YouTube or Vimeo and embedded

## Components and supplies

- 2 × Arduino UNO Q (4 GB)
- 1 × Arduino Modulino Buttons
- 1 × Arduino Modulino Knob
- 2 × Arduino Modulino Distance
- 1 × Elecrow 7" IPS display (HDMI)
- 1 × USB headset (microphone and speaker)
- 1 × USB-C hub with PD input, HDMI and USB-A, with a USB-C PD power supply
- 4 × Qwiic cables
- Cardboard or scrap material for the frame and the remote

## Apps and platforms

- PlatformIO (platform `lee-lab-skku/arduinoq`) for the MCU firmware
- Arduino_Modulino library
- Arduino Router Bridge (UNO Q)
- Python 3, pygame
- Vosk (small English model)
- Cactus Whistle and Needle 3 (Cactus Compute)
- Piper (text to speech, used once at setup)

## Tags

`uno-q`, `modulino`, `speech-recognition`, `offline-ai`, `edge-ai`, `tinyml`, `healthcare`, `education`, `game`

## Licence

MIT (our code). The models keep their own licences.

## Code

https://github.com/JustCodeX/steadyHands

## Story

### The problem

In an operating room the surgeon's hands are busy. Three things have to work at the same time: a steady hand in a narrow wound, clear calls for instruments, and orders to the anaesthesia nurse with a drug and a dose. Medical students practise these separately, if at all. Steady Hands trains all three at once, in one-minute rounds in the skills lab.

Hospitals are strict about voice data, so the trainer has to work without the cloud. Everything runs on the UNO Q: no audio leaves the board, and none is stored.

### How a round works

- **Steer.** You move a hand-held remote inside a small frame. Two Modulino Distance sensors measure how far it is from two walls, and the instrument on the screen follows. Only the change counts, so the frame never has to line up with the screen. Hold the freeze key to bring your hand back, like lifting a mouse off the pad. Touch a wall and it buzzes, the pulse goes up; three touches and the patient wakes up.
- **Call.** "Forceps!", "Clamp!", "Swab!", "Scalpel!": each target needs its own instrument. In co-op mode the assistant picks the called one with the Modulino Knob and hands it over by pressing it.
- **Order.** From level 2 on, oxygen saturation, depth of anaesthesia and blood pressure start to drift. The nurse raises the alarm ("Doctor, he is waking up."), you order a drug and an amount ("Propofol 50."), and she reads it back. Each tile shows a dose card, so the dose matters: too little helps only part of the way, too much overshoots into the opposite alarm.
- **Score.** Time, wall contacts, steadiness, orders right, on screen and spoken. Six levels.

### Hardware

Two UNO Q boards. The **game board** runs the game, the display, the headset, and carries the Modulino Buttons and Knob. The **remote** carries the two Modulino Distance sensors and sends 50 frames per second over UDP to the game board. On each board the STM32 MCU reads the Modulinos and pushes frames over the Router Bridge to the Linux side, so Linux never polls. Both boards run the same firmware source, told apart by one build flag.

Both Distance sensors ship with the same I2C address. The firmware moves whichever one it can reach to a free address, so the second can join afterwards.

### Two speech paths that never cross

- **Commands** ("Clamp!") go to Vosk small, restricted to our command phrases. A fixed grammar cannot hear "four steps" for "forceps", and it decides in under 0.1 s.
- **Orders with a dose** ("Propofol 50 and oxygen to 70.") go to Cactus Whistle for speech to text, then to Needle 3, a small tool-calling model, which returns `give_propofol(milligrams=50)` and `set_oxygen(percent=70)`. Needle is the published model cut to 12 of its 20 layers, with no fine-tuning.
- Without a drug name, Needle does not run. An amount that is not in the sentence is dropped. Without the Cactus models the game still runs by voice, with standard doses.
- The voices of the patient and the nurse are rendered once at setup with Piper, so there is no speech synthesis during play.

### Measured on the board

On the game board with the full game running, 14 November 2026:

- at most 1.4 GB of the 3.7 GB RAM in use while playing
- 127 MB for all three speech models on disk
- under 0.1 s from the end of a command to the decision
- about 1.9 s per order with a dose
- 40 of 42 test orders read right (drug and amount), no order made out of 14 sentences of plain talk

The test sentences were spoken by synthetic voices; tests with real medical students are next.

### Energy

No general LLM, models that run only when the voice activity detector hears speech, the smallest Needle rung that passed our tests, pre-rendered voices, a 30 fps cap and an idle mode. The power measurement for the Software Carbon Intensity per round is the next step: [technical documentation](https://github.com/JustCodeX/steadyHands/blob/main/docs/technical-documentation.md#environmental-impact-sci).

### What's next

Tests with medical students and real voices in a skills lab, fine-tuning only if those tests show misses, and more scenarios: each new drug is one more tool on the same monitor. Full roadmap: [ROADMAP.md](https://github.com/JustCodeX/steadyHands/blob/main/ROADMAP.md).

### Build it yourself

Everything is in the repo: wiring, firmware, the Linux app, the setup script that downloads the models, and the tests. Start with the [README](https://github.com/JustCodeX/steadyHands#quick-start).

Built by team Steady Hands at the Speech-to-Speech Hackathon, Nürnberg, 13–14 November 2026.
