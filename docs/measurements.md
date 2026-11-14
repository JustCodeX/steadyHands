# Measurements

Only measured numbers go here (date, setup, method). Source for the pitch and the criteria check in [PLAN.md](../PLAN.md#hackathon-criteria-check). Method: [WIRING.md](../WIRING.md#energy-measurement-with-the-peaktech); software values come from `app/logs/metrics.csv` (MetricsLogger).

Values marked *(increment 1)* were measured 13 November 2026 on the same board
with the earlier Whistle/framebuffer prototype. They carry over as bounds and
calibration data, not as numbers for this stack — re-measure where it matters.

## Board baseline

Measured 13 November 2026, idle over SSH (no app running).

| Property | Value |
| --- | --- |
| Board | Arduino UNO Q, serial 2510574293, device name `geil` |
| OS | Debian GNU/Linux 13 (trixie), kernel 7.0.0, aarch64, 4 cores |
| RAM | 3667 MB total · **3077 MB available** at idle |
| Disk | 9.8 GB root · **~2.7 GB free (72 % full)** with models + clips installed |
| Python | 3.13.5 — system install has no pip and no `audioop` (removed in 3.13) |
| Network | Wi-Fi `wlan0`, 192.168.1.155; DNS partly IPv6-only without a route → `curl -4` |

⚠ **Disk is the tighter budget, not RAM.** Vosk small + Piper voice + 219
rendered clips fit, but there is no room for several model candidates at once.

## Power and energy

| State | Voltage (V) | Current (A) | Power (W) | Date / setup | Notes |
| --- | --- | --- | --- | --- | --- |
| Idle (display off, mic off) | | | | | |
| Menu | | | | | |
| Round, nobody speaking | | | | | |
| Round, speaking | | | | | |

- Energy per round (mean power × round time): _ Wh
- Saving from VAD gating (round with speech-to-text always on vs. gated): _ %

## Latency (end of speech to command, from metrics.csv `command_latency_ms`)

| Tries | Median (ms) | Worst (ms) | Date / setup |
| --- | --- | --- | --- |
| | | | |

### Quiz answers: which recogniser setting *(laptop, synthetic voices)*

Measured 13 November 2026 on a laptop, not on the board: 492 answers spoken by
two macOS voices (Samantha, Daniel) in clean audio, covering the first two
phrases of every option of every question, each alone and inside two sentences
("I think it is the clamp", "that would be clamp I guess"). Each went through
the app's answer recogniser and `KeywordEvaluator`.

| `voice.answer_vocabulary` | Right option | Unclear ("Pardon?") | Wrong option | Decode time / audio time |
| --- | --- | --- | --- | --- |
| `open` | 414 (84 %) | 78 | 0 | 0.05 |
| `keywords` (per question) | 365 (74 %) | 127 | 0 | 0.02 |
| `both` (default) | 472 (96 %) | 20 | 0 | 0.08 |

The open vocabulary alone fails on the rare words ("clamp" → "plan", "swab" →
"swag", "four" → "for"); the phrase-restricted recogniser alone loses a word
in the middle of a sentence. Together they cover each other.

⚠ This says which setting to start with, nothing more. The voices are
synthetic, there is no room noise, and the six misheard words added to
`questions.json` afterwards ("swag", "suave", "scalable", "clan", "claimed",
"vain") came from these same recordings. The laptop is also several times
faster than the board, so `both` may decode slower than real time there:
check the answer latency below. The test with 20 answers spoken by a person on
the board ([tests.md](tests.md)) is the one that counts.

Quiz answers (end of speech to verdict, `answer_latency_ms`; answers are whole sentences, so segments are longer):

| Tries | Median (ms) | Worst (ms) | Date / setup |
| --- | --- | --- | --- |
| | | | |

*(increment 1)* End of speech → start of spoken answer: **301–861 ms** over the
day (microphone → STT → matcher → pre-rendered clip, model loaded once at
start). P6 requires 3–5 s, so even the worst case has ~4× headroom. Treat this
as the bound to beat; measure this stack's own numbers with 20 spoken commands.

### Vitals monitor with doses: Needle reads drug and amount

Measured 14 November 2026 with `app/tools/needle_eval.py` on
`tests/data/needle_cases.json` (42 orders and named drugs, 14 sentences of
talk). Board: JustuBoard, governor `schedutil`, the game running at the same
time with its own Needle worker.

| Rung | Where | Right (of 42) | False orders (of 14) | Model call median (ms) | Worst (ms) | Peak memory (MB) |
| --- | --- | --- | --- | --- | --- | --- |
| 12L (default) | Board | 40 | 0 | 1851 | 3615 | 115 |
| 9L | Board | 36 | 0 | 1228 | 2031 | 91 |
| 12L | Laptop (Intel i9) | 40 | 0 | 131 | 200 | 113 |

Memory on the board with 12L, menu, full app (14 Nov, 01:20 UTC):
MemAvailable 1911 MB; trainer process 380 MB RSS, Needle worker 118 MB RSS.

All rungs on the laptop: [needle-integration.md](needle-integration.md#measurements).

Whole voice path with synthetic voices (`tools/voice_drive.py`, 32 cases,
laptop): 24/32 right, 148 ms median from end of speech. The misses are
Whistle hearing "propofol" as other words (voice Daniel) and one amount
Needle did not read; see [needle-integration.md](needle-integration.md#whistle-and-the-drug-names-synthetic-voices-open-point).

### Vitals monitor, first version (treatments without amounts) *(synthetic voices)*

Measured 14 November 2026 with `app/tools/voice_drive.py`: 32 cases (16
sentences, macOS voices Samantha and Daniel) played into the app's
`VoiceService` without a microphone. End of speech = the segmenter closed
the segment. Details and the rung comparison: [needle-integration.md](needle-integration.md#measurements).

| Setup | Right | Median (ms) | Worst (ms) |
| --- | --- | --- | --- |
| Board (JustuBoard, `schedutil`, game running), `cactus.toml` (Whistle + Needle 9L) | 32/32 | 790 | 1860 |
| Board, defaults (no model) | 18/32 | 87 | 104 |
| Laptop (Intel i9), `cactus.toml` | 32/32 | 93 | 235 |

Needle 9L alone on the board: 1033 ms median, 1313 ms worst per model call
(41 calls), 90 MB peak, 1.95 s to load.

## Memory and CPU (from `free -m` and metrics.csv)

Measured 13 November 2026, full app running (Vosk + pygame renderer + 219
clips), median over the session; n = 195 (idle) / 23 (menu) samples.

| State | MemAvailable (MB) | Process RSS (MB) | CPU (%) |
| --- | --- | --- | --- |
| Idle | 2231 | 287 | 25 |
| Menu | 2139 | 277 | 48 |
| Round, nobody speaking | | | |
| Round, speaking | | | |
| Round, answering a quiz question (open-vocabulary recogniser) | | | |

With the Cactus models (`cactus.toml`), measured 14 November 2026 on
JustuBoard, menu, full app: MemAvailable 1959–1966 MB; trainer process
364–373 MB RSS (327 MB without the models, same boot); Needle worker process
89 MB RSS.

**C1 (at least 1 GB free): met so far** — minimum observed MemAvailable was
1349 MB, median above 2.1 GB.

Final set-up, 14 November 2026 (game board, debug panel and ASR logging off,
playing): **at most 1.4 GB of RAM in use** of 3.7 GB, team reading during play.

## Voice findings *(increment 1 — calibration data and known failure modes)*

### Room noise floor (for EnergyVad calibration)

Measured over 5 s of silence in the hackathon room, RMS per 30 ms frame,
JBL Tune 530C headset at 16 kHz:

| Percentile | RMS |
| --- | --- |
| P50 | 21 |
| P90 | 46 |
| P99 | 67 |
| max | 79 |

A gate threshold of **220** (~3× the measured silence peak) worked all day.
**Recalibrate in the real hall** — the demo floor will be louder.

### Whisper-family STT hallucinates on silence

Left listening to a quiet room, Whistle returned "Thank you." repeatedly and
once "Sous-titrage Société Radio-Canada". The Vosk grammar (21 phrases) cannot
produce arbitrary text, but it *can* still force noise onto its nearest
phrase — the energy gate in front of the recogniser remains load-bearing, and
it is also what keeps STT idle while nobody speaks (energy criterion).

### False command from ordinary room conversation

```
heard "Je ne sais pas si vous voyez, c'est ça" -> pause
```

French `pas` matched `pause` at **exactly 0.75** — the current default in
`app/trainer/voice/command_matcher.py`. What fixed it in increment 1:
threshold **0.82** plus a length guard (candidate within ±2 characters of the
command). Verified with ten minutes of German/French room conversation: no
false triggers, all six commands still matched at 1.00.

⚠ **The headset microphone picks up the whole room, not just the wearer.**
Surrounding conversation transcribed clearly throughout. Re-test the matcher
threshold in hall noise before the demo, especially for co-op.

### Audio device

The JBL Tune 530C does **not** support 16 kHz natively — `hw:0,0` falls back
to 48 kHz. Always open it as **`plughw:0,0`** so ALSA resamples.

## Display

Measured 13 November 2026, Elecrow 7" on the hub (HDMI over DP Alt Mode).

| Property | Value |
| --- | --- |
| Reported mode (EDID) | **1920×1080** — not the panel's native 1024×600 |
| Renderer | pygame on X (:0), sets 1024×600 fullscreen; X scales to 1080p |
| Avatar frame rate *(increment 1, Pillow on /dev/fb0 at full HD)* | ~25 fps |

⚠ The panel announces 1080p and downscales internally. Rendering at 1024×600
is correct, but **check text legibility from two metres** before trusting any
font size.

## Still to measure

- Power per state, energy per round (PeakTech, see [WIRING.md](../WIRING.md#energy-measurement-with-the-peaktech))
- Latency on this stack: 20 spoken commands → median/worst from `metrics.csv`
- Memory/CPU for the two in-round states, and with a quiz question open (second recogniser)
- Quiz answers: latency over 20 answers, and recognition of 20 spoken answers (see [tests.md](tests.md))
- Matcher threshold hardening test in hall noise (co-op false triggers)
