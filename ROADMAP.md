# Roadmap

Where Steady Hands goes after the hackathon (14 November 2026). The prototype runs end to end on the board; what is missing is evidence with real users, the energy numbers, and more training content. Each step has a "done when", so it can be checked.

## 1. Prove it with real users (next weeks)

| Step | Done when |
| --- | --- |
| **Real speakers instead of synthetic voices.** So far the spoken orders were tested with macOS voices only. Run [docs/tests.md](docs/tests.md) with medical students in a skills lab, with real room noise. | 20 spoken orders and 20 commands per speaker, results in [docs/measurements.md](docs/measurements.md) |
| **"Propofol" across accents.** With synthetic British and other voices, Whistle heard "probable" or "proper full". Decide from the real recordings whether the drug needs a second spoken name. | Hit rate for "propofol" per speaker measured; second name added only if it is below the other drugs |
| **Hall noise.** Harden the command threshold against false triggers from conversation nearby (co-op mode). | 20 commands in hall noise, false triggers counted |
| **Teaching value.** Ask lecturers in surgery and anaesthesia whether the round, the dose cards and the feedback match what they teach. | Feedback from at least one skills lab |

## 2. Measure and cut the energy (SCI)

The judging asks for the [Software Carbon Intensity](https://sci.greensoftware.foundation/). Our estimate from published figures is 0.07–0.12 g CO₂e per round ([calculation](docs/technical-documentation.md#environmental-impact-sci)); the power numbers behind it are not our own measurements yet.

| Step | Done when |
| --- | --- |
| **Power per state** (idle, menu, round without speech, round with speech) with a USB-C power meter on the hub input. | Table in [docs/measurements.md](docs/measurements.md#power-and-energy) filled |
| **SCI per training round from measured power**, replacing the estimate's power table. | One measured number in g CO₂e per round, with its inputs |
| **Saving from the VAD gate** (speech-to-text gated vs. always on). | Saving in % measured |
| **One board instead of two.** The remote is a full UNO Q that only measures two distances and sends them over Wi-Fi. Where the remote may have a cable, a long Qwiic cable to the game board would save one board, its power supply and its embodied emissions. | Same steering quality with one board; SCI of both set-ups compared |

## 3. More training content

| Step | Done when |
| --- | --- |
| **More drugs.** Every drug is one more tool for Needle on the same monitor (for example a muscle relaxant or an opioid), with its own dose card. | New tool in the `ActionCatalog`, a dose model, test sentences in `needle_cases.json` |
| **More scenarios and levels.** New wounds and crises; a level is a PNG mask and a JSON file ([levels/](levels/README.md)). | Each new level playable and in the test suite |
| **Progress over sessions.** Show a student how steadiness, time and orders improve across rounds, still without storing any audio. | Scores per session kept locally; no recordings, no transcripts |
| **German voice set.** Vosk, Whistle and Piper all exist for German; the game is English only today. | One full round playable in German |

## 4. Make it better only where the tests show it is needed

- **Fine-tune Needle only if the real-speaker tests show misses.** Today it is the published model cut to 12 of its 20 layers, with no training (40 of 42 test orders right). The fine-tuning recipe is in [docs/needle-integration.md](docs/needle-integration.md#if-the-rungs-are-to-get-better-fine-tuning-not-done).
- **A smaller rung** (9 layers: 1.2 s instead of 1.9 s per order, 36 of 42 right) only together with fine-tuning.

## 5. Open the build

| Step | Done when |
| --- | --- |
| Licences of every model and voice checked (Needle, Vosk model, Piper voice) | Table in [PLAN.md](PLAN.md#licenses) complete |
| Case and remote frame as printable or laser-cut files | Files in the repo, linked from the Project Hub page |
| Project Hub page kept in step with the repo | Text in [docs/project-hub.md](docs/project-hub.md) published |
