# Measurements

Measured values with date and setup. The [criteria check](../PLAN.md#hackathon-criteria-check)
links here once a row is verified.

## Board baseline

Measured 13 November 2026, 15:0x, over SSH on the board, idle (no app running).

| Property | Value |
| --- | --- |
| Board | Arduino UNO Q, serial 2510574293, device name `geil` |
| OS | Debian GNU/Linux 13 (trixie), kernel 7.0.0, aarch64 |
| CPU | 4 cores |
| RAM | 3667 MB total · 590 MB used · **3077 MB available** |
| Disk | 9.8 GB root · 6.5 GB used · **2.9 GB free (70 % full)** |
| Python | 3.13.5, system install has **no pip** and no packages |
| Network | Wi-Fi `wlan0`, 192.168.1.155, internet reachable over IPv4 |

**C1 (at least 1 GB free):** 3077 MB available at idle — ample headroom before
the game and speech-to-text are loaded. Re-measure per state during M0.

⚠ **Disk is the tighter budget, not RAM.** 2.9 GB free. Vosk small (~300 MB) and
Piper voices fit, but there is no room to keep several model candidates around.
Delete what we are not using.

## Audio gate (first step toward increment 1)

The UNO Q has no on-board microphone, so this had to be verified before any
voice work: a USB headset on the USB-C hub, visible to Linux as a capture device.

**Result: PASSED.**

| Check | Result |
| --- | --- |
| Capture device | `card 0: J530C [JBL Tune 530C], device 0: USB Audio` |
| Playback device | same card, confirmed by playing a recording back into the headset |
| 3 s recording at 16 kHz mono | RMS 542, peak 5382 = 16.4 % of full scale |
| Capture timing | 3.02 s wall clock for 3 s requested — no buffer loss |

Two findings that constrain how we write the audio code:

- **The headset does not do 16 kHz natively.** `arecord -D hw:0,0 -r 16000`
  falls back to 48 kHz and warns "try the plug plugin". Always address it as
  **`plughw:0,0`**, which resamples to 16 kHz in ALSA.
- **`audioop` is gone** in Python 3.13 (removed in 3.13). Level and frame
  maths go through numpy instead.

## Python environment on the board

The board image ships Python without pip, and installing `python3-venv` needs
sudo. Same workaround as `firmware/tools/board.sh setup`: unpack Debian's pip
wheel in user space and create a venv with it.

```sh
# on the board, no sudo needed
T=$(mktemp -d); cd "$T"
apt-get download python3-pip-whl
dpkg-deb -x python3-pip-whl_*.deb root
W=$(ls root/usr/share/python-wheels/pip-*.whl)
python3 -m venv --without-pip $HOME/trainer-venv
$HOME/trainer-venv/bin/python "$W/pip" install --no-index "$W"
```

| Item | Value |
| --- | --- |
| venv | `/home/arduino/trainer-venv`, pip 25.1.1 |
| numpy | 2.5.4, installed from PyPI in 80 s |

**Capture goes through `arecord` as a subprocess, not PortAudio.** `sounddevice`
and `pyaudio` need the PortAudio shared library, which would need `apt` and
therefore sudo. Reading raw frames from `arecord -t raw` into numpy avoids that
dependency entirely and is already proven to work:

```
samples 48000   capture 3.02 s (3 s requested)
RMS 727   Peak 6302 (19.2 %)
30 ms frames: 100, of those carrying energy: 11 (11 %)
```

The last line is the shape a VAD gate will take: per-frame energy over 30 ms
windows.

## Network

| Target | Result |
| --- | --- |
| `ping 8.8.8.8` | 140–368 ms, 0 % loss |
| `pypi.org/simple/<package>/` | HTTP 200 |
| `huggingface.co` | HTTP 200 |
| `pypi.org/simple/` (full index) | times out — it is a ~20 MB page, not a block |

⚠ DNS returns **IPv6 only** for some hosts and the board has no working IPv6
route. Use `curl -4` / force IPv4 in any download script.

## Speech-to-text: D2 decided

Measured 13 November 2026 on the board, venv `~/trainer-venv`.

**Decision: Whistle (Cactus Compute).** Not Vosk, not Moonshine.

| Candidate | Size | License | Runtime | Verdict |
| --- | --- | --- | --- | --- |
| **Whistle** (cactus-compute 4.2.0) | 16.9 MB | **Apache-2.0** | pure-Python wheel, `py3-none-any` | ✅ chosen |
| Moonshine tiny-de / base-de | 108 / 246 MB | cc-by-nc-sa-4.0 | torch + transformers | ✗ NonCommercial blocks C5/D5 |
| Vosk small | ~300 MB | — | — | not tested; Whistle won on all axes |

Moonshine was rejected on licence, not accuracy: **CC BY-NC-SA is not an open
source licence**, so it cannot ship with a published build (C5, D5), and
ShareAlike would reach into our own code. Whistle also avoids the torch stack
entirely, which matters because disk, not RAM, is our tight budget.

### Measured

| Metric | Value |
| --- | --- |
| Cold start (first call, loads the model) | 8.52 s |
| Warm transcription, 3 s clip | **0.63 s** |
| Language detection | automatic; German transcribed with no configuration |

**P6 is met with headroom**: the requirement was a reply within 3–5 s, our own
target under 1 s. Load the model once at app start — never per utterance.

The transcription was a real sentence off the test recording, so capture →
ALSA → numpy → Whistle is proven end to end.

### ⚠ Telemetry is on by default

```
cactus-compute collects anonymous usage counts (function name, version, OS)
to guide development; no prompts or outputs.
```

No audio and no transcripts leave the device, but it is still an outbound call,
and C2/C4 promise no network services and nothing leaving the device. Set
**`CACTUS_TELEMETRY=0`** in the app's own environment, not in a shell profile
someone can forget.

## Increment 1: spoken word -> spoken answer

Measured 13 November 2026 on the board. This is the hackathon's first
milestone (T5) and the thinnest vertical slice of the trainer: microphone ->
Whistle -> CommandMatcher -> pre-rendered patient line. No MCU, no display,
no game loop.

Run it with `python3 increment1.py` in `~/trainer-app` on the board.

| Metric | Value |
| --- | --- |
| Model load at start (warm page cache) | 1.3 s |
| End of speech -> patient answers | **301 ms** |
| Lines rendered by Piper (en_US-lessac-medium) | 13, 836 KB |
| Piper voice model | 63 MB, downloaded at setup, not in the repo |

**P6 is met with a wide margin**: required 3-5 s, our target under 1 s,
measured 0.30 s.

### The finding that mattered: "forceps" becomes "four steps"

The first run failed, and usefully so. Whistle transcribed the spoken command
`forceps` as **"Four steps."** The matcher rejected it at 0.57 and the patient
asked "Pardon?" - the error handling worked exactly as designed, but the
command was unusable.

The cause was in our matcher, not the recogniser: it compared single words
only, and `four` is far from `forceps`, while `foursteps` is close. Two fixes
in `trainer/voice/commands.py`:

- **Adjacent words are also compared joined together**, so a command split in
  two is still found.
- **An alias table** maps known mis-transcriptions to commands. These are
  measured on the board, not guessed. Extend it during hall testing.

After the fix the same utterance matched `forceps` at confidence 1.00.

**This is the thing to budget time for.** Every command word needs to be
spoken into the real headset and checked against what Whistle returns. Free
transcription plus fuzzy matching works, but only once the actual
mis-transcriptions are known. Rejections stay safe: "banana bread" (0.55) and
"The weather is nice today" (0.60) are still correctly ignored.

## Display and avatar

Measured 13 November 2026, Elecrow "7inch HD Display-D" on the USB-C hub.

| Property | Value |
| --- | --- |
| Connector | `card0-DP-1`, connected (HDMI over DisplayPort Alt Mode) |
| Reported mode | **1920x1080**, not the 1024x600 WIRING.md assumes |
| Framebuffer | `/dev/fb0`, 32 bpp, stride 7680, driver `msmdrmfb` |
| Avatar frame rate | **~25 fps** at full HD, drawn with Pillow |

⚠ **WIRING.md's resolution is wrong.** The panel announces 1920x1080 over
EDID. The avatar scales itself to whatever is reported, so it does not care,
but if the physical panel really is 1024x600 the monitor is downscaling
internally. Check text legibility from two metres before trusting any font
size.

### Rendering: framebuffer, not SDL, not X

The board boots into lightdm, whose greeter holds the DRM device, so nothing
else can take the display. `sudo systemctl stop lightdm` frees it - and that
is what we want anyway: the trainer should own the screen, not sit on top of
a desktop.

pygame then still refused: **its manylinux wheel bundles an SDL built without
KMSDRM**. Building one needs root. Instead the avatar draws with Pillow
straight into `/dev/fb0`, which belongs to the `video` group that the
`arduino` user is already in - so it needs **no root at all**. Only the rows
that changed are written, because a full 1920x1080 frame is 8.3 MB.

## Voice gating: two real failures, both fixed

Running the assistant with an open microphone in the hackathon room exposed
two problems that no amount of planning would have found.

### 1. Whistle hallucinates on silence

Left listening to a quiet room, it returned **"Thank you."** over and over,
and once `Sous-titrage Societe Radio-Canada` - both well-known artefacts of
Whisper-family models. Every one of them woke the assistant and made it say
"Pardon?".

Two defences, in `trainer/voice/vad.py` and `recognizer.py`:

- **An energy gate in front of the recogniser.** Speech-to-text never sees a
  segment without speech in it. This also saves energy, which is a judging
  criterion: the model does not run at all while nobody speaks.
- **A hallucination list** for what still gets through.

Measured noise floor in the room, over 5 s of silence:

| Percentile | RMS |
| --- | --- |
| P50 | 21 |
| P90 | 46 |
| P99 | 67 |
| max | 79 |

The gate threshold is **220**, roughly three times the measured peak of
silence. Recalibrate in the real hall - `trainer/voice/vad.py` takes it as a
constructor argument.

### 2. A false command from ordinary conversation

```
heard "Je ne sais pas si vous voyez, c'est ca" -> pause
```

The French `pas` matched `pause` at exactly 0.75, the old threshold, and
paused the game. In co-op, where the two players talk constantly, that is
unacceptable.

Fixed in `commands.py`: the threshold is now **0.82**, and a candidate whose
length differs from the command by more than two characters is not considered
at all. Verified afterwards with ten minutes of German and French
conversation in the room: **no false triggers**, while `forceps`, `swab`,
`clamp`, `scalpel`, `help` and `pause` all still match at 1.00.

⚠ **The headset picks up the room, not just the wearer.** Surrounding
conversation was transcribed clearly throughout. The plan assumed a
close-talking headset mic would solve hall noise; it does not on its own. The
rejection logic is what keeps it usable, so do not loosen it.

## Still to measure

- Power per state, energy per round (PeakTech, see [WIRING.md](../WIRING.md#energy-measurement-with-the-peaktech))
- Latency: end of speech → command, and → start of the patient's reply
- RAM per state with speech-to-text loaded (C1)
- D2 comparison: Whistle vs Vosk on 20 spoken commands in hall noise
