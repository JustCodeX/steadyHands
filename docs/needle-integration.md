# Needle and Whistle (Cactus) in the voice pipeline

Two optional models from Cactus Compute can be switched on: **Needle**, a tool-calling model, and **Whistle**, a small speech-to-text model. This page says what each one does here, how to switch it on, what has been checked, and what still has to be measured on the board.

⚠ **The code was written against the runtime's API as described in the team's hand-over notes, and tested against a stand-in for the runtime. It has not yet run with the real `cactus-compute` package.** The first step on the board is the check in [First run on the board](#first-run-on-the-board).

## What each model does here

| Path | Default (no Cactus needed) | With Cactus |
| --- | --- | --- |
| Commands | Vosk restricted to the command phrases, then the keyword matcher | Unchanged by default. Optional: free speech and Needle ("something to stop the bleeding" → `clamp`) |
| Quiz answers: hearing | Vosk twice on the same audio: open vocabulary, and the open question's answer phrases | Optional: Whistle instead of the open-vocabulary Vosk |
| Quiz answers: judging | Keyword evaluator: which option's phrase is in the answer | **Needle for answers that name no option in so many words** ("the thing you cut with" → `scalpel`) |

Needle picks one function from a list and fills its arguments. It does not chat and it does not grade free text. A quiz answer fits that shape: the question's options are the allowed values of one tool, `answer(choice)`.

**Why Needle is not in the command path by default.** A plain "Clamp!" must change the instrument in well under a second, and the restricted vocabulary is what keeps commands reliable in hall noise. Needle needs about a second per call on the board and needs free speech to be of any use. So commands stay as they are, and Needle works where a sentence is expected anyway and one second is acceptable: the answer window of a quiz question.

## Switching it on

1. Install the runtime on the board (optional requirement):
   ```sh
   pip install -r requirements-cactus.txt
   ```
2. Put the model files into `app/models/` (git-ignored):
   - `whistle.cact`: `WITH_CACTUS=1 setup/download_models.sh` downloads it (17 MB).
   - `needle3-9L.cact`: a 9-layer rung of Needle 3. It is built on a laptop from the checkpoint with the training extras (`cactus build needle3.safetensors --layers 9 --out needle3-9L.cact`, 28 MB) and copied over.
3. Start with the example config:
   ```sh
   python -m trainer --config cactus.toml
   ```
   `cactus.toml` switches on Needle for quiz answers. Whistle and Needle for commands are commented out in it.

If the package or a file is missing, the app logs one line and runs with the default for that part.

## Where the code is

Everything that touches the runtime is in `app/trainer/cactus_models/`. Nothing else imports `cactus`.

| Piece | File | What it is |
| --- | --- | --- |
| `load_cactus` | `runtime.py` | The only import of the runtime, with telemetry and hub access switched off first |
| `NeedleAgent` | `needle_agent.py` | One model with a fixed set of tools: text in, at most one `ToolCall` out. Calls `reset()` before every text |
| `NeedleEvaluator` | `needle_evaluator.py` | `AnswerEvaluator`: keyword evaluator first, Needle only if the answer names no option. One agent per open question, built while the patient asks it |
| `NeedleInterpreter` | `needle_interpreter.py` | `CommandInterpreter`: a command phrase in the text wins outright, otherwise Needle decides |
| `WhistleRecognizer` | `whistle_recognizer.py` | `SpeechRecognizer`: transcribes a whole speech segment when it ends |
| `ActionCatalog` | `../game/actions.py` | The game's commands as tools, and the way back from a tool call to a command word |
| `build_interpreter`, `build_evaluator`, `build_answer_recognizer`, `build_recognizer` | `../voice/voice_service.py` | Pick the implementations from the config and fall back when one cannot be built |
| `tools/needle_eval.py` | | The check for the board (below) |

Config keys, all under `[voice]`: `evaluator`, `interpreter`, `command_vocabulary`, `recognizer`, `answer_engine`, `needle_weights`, `needle_min_confidence`, `whistle_weights`, `whistle_language`.

## Design rules

- **Keywords first, model second.** An answer or command that contains a known phrase never reaches the model. That keeps the common case fast and saves energy (criterion C3).
- **"No tool" is a valid answer.** Players talk to each other. Speech that is not a command returns nothing, and the game ignores it. With free speech the keyword matcher's fuzzy guess is not used ("last night" is close to "light"); the model decides.
- **Two options named means unclear.** If an answer names two options, the recognisers disagreed or the player did. Needle is not asked to guess; the player is asked again.
- **Every text stands alone.** `agent.reset()` runs before each call. Without it, old context makes the model refuse later texts.
- **A held-back call is no call.** The runtime does not execute a call below confidence 0.1, and our tools only record calls that are executed.
- **No network.** The runtime sends telemetry and asks the Hugging Face hub for a file on every transcription unless told otherwise. `load_cactus` sets `CACTUS_TELEMETRY=0` and `HF_HUB_OFFLINE=1` before the import (criteria C2 and C4).
- **No transcripts outside `VoiceService`.** Do not log the text given to a model.
- **The defaults need no model.** The minimum version works without a language model (criterion T3).

## First run on the board

```sh
cd app
python tools/needle_eval.py models/needle3-9L.cact
```

It runs 15 command sentences and 12 quiz answers that contain no known phrase (so they do reach the model) and prints how many came out right, the latency, the load time, the time to get ready for a new question, and the memory added. Give it several rungs to compare them.

**The rung has to be chosen again for this game.** In the hand-over the 9-layer rung was the best of 18 rungs for a smart-home tool with two lamps and five test sentences. Rung quality does not grow steadily with depth (rungs 14 to 18 were worse than rungs 9 to 13 there) and depends on the tools. Run 9L, 12L and 19L and keep the smallest one that passes.

Things the code assumes about the runtime, which this run confirms or disproves:

- `cactus.tool` accepts a function whose `Literal` annotation and docstring were set at run time (`choice_tool` in `needle_agent.py`).
- The agent executes the tool function it picks, and `run()` returns a dict with a top-level `confidence`.
- Several agents can live in one process (one for commands, one per open question), and building one for a new question is quick. If not, cache by option list or keep one agent and rebuild it.
- `cactus.transcribe` takes a list of floats, `language`, `keywords`, `word_timestamps` and `weights`, and returns `text` and, with word timestamps, `words` with a `probability` each.

## Numbers from the hand-over

Measured by a team member on another UNO Q, with the CPU governor set to `performance`. They show what to expect; they are not measurements of this app.

| Model | Speed | Memory | File |
| --- | --- | --- | --- |
| Needle 3, 9-layer rung | 1009 ms median per call, 97 tokens/s | 90 MB | 28 MB |
| Needle 3, base (20 layers) | 1659 ms median | 114 MB | 35 MB |
| Whistle | 0.13 × real time on a 15 s recording | 73 MB | 17 MB |

The hand-over compares the speech models by speed and memory only. It has no accuracy numbers, and it notes that Needle's confidence for the same sentence differs between laptop and board.

## Measure before making any of it the default

Record the numbers in `docs/measurements.md`, on the board, with the full app running.

| What | How | Limit |
| --- | --- | --- |
| Needle: right calls | `tools/needle_eval.py` | Every case |
| Answers: Whistle against Vosk | The same 20 spoken answers with `answer_engine = "vosk"` and `"whistle"` (table in `docs/tests.md`) | Whistle must be better to replace Vosk; no wrong verdicts |
| Whistle on silence | Leave a question open in a quiet room | No verdict, no "Pardon?" |
| Memory | `free -m` and process RSS from `logs/metrics.csv`, with and without `cactus.toml` | At least 1 GB available (C1) |
| Latency | `answer_latency_ms` and `command_latency_ms`, median and worst of 20 | 3–5 s required (P6) |
| Disk | `df -h /` after installing the package and the files | About 2.7 GB were free before |
| CPU | Per state from `metrics.csv` | For the energy numbers (C3) |

## Open points

- Licenses: Whistle is Apache-2.0 (model card). Needle's model license and the license of the `cactus-compute` runtime still need checking.
- The CPU governor resets to its default at every boot. The numbers above were measured with `performance`; decide whether the app's start script should set it, and measure the power cost.
- For commands in free speech, pass only the commands that make sense in the current game state (`GameEngine.available_commands()`, `ActionCatalog.schemas(allowed)`). `VoiceService` does not know the game state yet; let the engine publish the list as an event.
