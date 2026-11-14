# Whistle and Needle (Cactus) for the nurse's treatments

Two optional models from Cactus Compute serve one mechanic: the **vitals monitor**. When a value drifts, the surgeon tells the nurse what to give, in a free sentence ("he can't breathe, do something"). **Whistle** (speech-to-text) hears the sentence, **Needle** (tool calling) turns it into one of three treatments: `oxygen`, `anaesthesia`, `adrenaline`.

**Every older voice command stays on the Vosk grammar.** Instruments, `steady`, `light`, `cancel`, `repeat`, `help`, `pause`, `continue` and `new game` never go through Whistle or Needle, and the two paths never fire each other's words.

Status (14 Nov 2026): the adapters were checked against the source of `cactus-compute` 4.2.0 and run on a laptop and on the board. The pipeline works end to end. The published Needle rungs are **not good enough on their own** for free sentences (numbers below); a trigger-word gate and an alarm-only rule keep the game safe. Fine-tuning is the documented way to improve the rungs, and it is postponed until the team decides (it needs no change in the code: a tuned rung is another `.cact` file).

## How a segment is decided

`trainer/voice/understanding.py` (`CommandUnderstanding`). Both recognisers hear the same speech segment.

1. **Short call with a command phrase** ("Clamp!", under 1.2 s): the Vosk grammar decides at once. Whistle never runs.
2. **Longer segment, or one the grammar did not catch:** Whistle transcribes it when it ends.
   - A treatment named outright ("give him adrenaline") counts at any time.
   - **While an alarm is open** (`InstructionWindow` from the engine), Needle decides sentences that name no treatment, but only if one of the treatments' trigger words is in the sentence (`voice.needle_require_trigger`).
   - Otherwise the grammar's result stands, as before. During an alarm, a sentence without a treatment gets "Pardon, doctor?"; the second time, the nurse names what she can give.
3. **Without Whistle** (the default config, or a missing model), the treatment phrases join the Vosk grammar, so the game is playable by voice without any model (criterion T3), and with keys 5, 6, 7.

## Switching it on

1. On the board, in the app's venv: `pip install -r requirements-cactus.txt` (pinned to 4.2.0).
2. Once, while online: `python -m cactus fetch`. The runtime downloads its engine library on first use, and the app runs it with `HF_HUB_OFFLINE=1`. `WITH_CACTUS=1 setup/download_models.sh` does this and downloads `whistle.cact`.
3. Copy `needle3-9L.cact` into `app/models/` (built on a laptop, see [Building rungs](#building-rungs)).
4. `python -m trainer --config cactus.toml`, or set `STEADYHANDS_CONFIG=cactus.toml` for the autostart.

If the package or a file is missing, the app logs one line and runs as in step 3 of the list above.

## What was checked against the runtime

Read in the package source (`cactus/agent/text.py`, `whistle.py`, `_worker.py`, `tools.py`) and confirmed by `tests/test_cactus_real.py` (runs only with the package and the models):

| Assumption in the first version | Finding | Change |
| --- | --- | --- |
| `Cactus.run()` executes the tool and returns its confidence | `run()` executes the tools, then runs the model **a second time** on their results and returns that turn's envelope | `NeedleAgent` uses `complete()`, which returns `function_calls`, `suppressed_calls` and `confidence` of the first turn without executing anything. Half the latency |
| Tools as Python functions with a runtime `Literal` | Works, but the runtime also takes JSON schemas directly | Tools are JSON schemas from `ActionCatalog` |
| Several agents in one process | Weights other than the published base run in a **worker process** of the runtime's own (one per agent) | `unload()` closes the worker; one Needle agent in the game |
| `confidence` is a number | `None` for weights without a confidence head (e.g. LoRA builds). Rungs from `cactus build --layers` keep the head | `None` counts as 1.0, with one log line |
| `transcribe(list_of_floats, ...)` | Takes a float32 array directly; returns `text`, `language`, and `words` with `probability` | `WhistleRecognizer` passes the array |
| Telemetry and hub off | `CACTUS_TELEMETRY=0` is read per call; `HF_HUB_OFFLINE` must be set before `huggingface_hub` is imported | Unchanged: `load_cactus()` sets both before the import |
| — | Tool schemas take `triggers`: request regexes (documented, not explained) | Every treatment has triggers; they decide whether Needle picks the right tool (below) |

## Tools

`ActionCatalog(MODEL_ACTIONS)`: three tools without parameters, each with a one-line description and a trigger regex (`trainer/game/actions.py`). The runtime's docs advise five tools or fewer and plain names.

Whistle gets the treatment phrases and a list of symptom words as `keywords` (`SYMPTOM_WORDS`). Without them it wrote "saps" for "sats" and "waiting up" for "waking up" on synthetic speech.

## Measurements

Test data: `app/tests/data/needle_cases.json`, written 14 Nov 2026 by one author (they share a style; real speakers on the board are the test that counts). 45 treatment sentences without a treatment phrase (15 of them without any trigger word), 25 sentences of talk, 12 status reports with the same medical words as an alarm ("his sats look good now"), 14 older commands in free words. Tool: `app/tools/needle_eval.py`. Pass rule: at least 90 % of the treatment sentences right, and at most one false trigger.

### Tool layout (laptop, 20 sentences, before the full data set)

| Layout | Result |
| --- | --- |
| 3 treatment tools without triggers | Every rung picked the same tool for almost every sentence (20L: 7/20, 9L: 7/20) |
| One `treat_patient(treatment)` tool with an enum | 1–3/20 on every rung |
| Instrument tool added to the treatments | Clamp 0/8 and scalpel 0/8 on every rung; 17–24 of 25 talk sentences triggered something |
| 3 treatment tools **with triggers** | 15/15 treatment sentences on 20L, 16L, 12L and 9L |

### Published rungs on the full data set

Laptop (Intel i9-9880H, macOS), and the board (UNO Q, governor `schedutil`, the game running at the same time). Treatment = right out of 45; false = false triggers out of 51 (talk / status / older commands).

| Rung | File | Laptop, gate on | Laptop, no gate (39 talk + older) | Board, gate on | Board: model call median / worst | Board: peak memory |
| --- | --- | --- | --- | --- | --- | --- |
| 4L | 15 MB | 28, false 11 (0/11/0) | 31, false 23/39 | 28, false 10 (0/10/0) | 693 / 6490 ms | 61 MB |
| 6L | 17 MB | 26, false 11 | 30, false 34/39 | 26, false 10 | 699 / 8969 ms | 67 MB |
| 8L | 27 MB | 29, false 11 | 33, false 38/39 | | | |
| **9L** | 28 MB | **29, false 11** | 33, false 38/39 | **29, false 11 (0/11/0)** | **1033 / 1313 ms** | **90 MB** |
| 12L | 39 MB | 29, false 11 | 34, false 32/39 | 29, false 11 | 1242 / 1692 ms | 114 MB |
| 16L | 51 MB | 29, false 11 | 37, false 32/39 | | | |
| 20L (published) | 35 MB | 28, false 11 | 33, false 35/39 | | | |

- **No rung passes.** Without the gate, every rung calls a tool for almost any talk. The confidence of those calls is as high as that of right calls (16L: right 0.38–0.86, false 0.44–0.90), so no threshold separates them.
- With the gate, talk and older commands never trigger (0 of 39), but the model cannot tell "his sats are dropping" from "his sats look good now": 10–11 of 12 status reports trigger. Sentences without a trigger word never reach it (0 of 15).
- Depth hardly matters with the gate (26–29 of 45). **9L is used:** the same quality as 12L–20L, a steady latency on the board (4L and 6L had outliers of 6–9 s), and the rung the team measured before.
- What keeps the game safe: Needle only runs while an alarm is open, so a status report outside an alarm does nothing. During an alarm a false trigger is a wrong treatment, which the game treats like any wrong instruction.

### The whole voice path with synthetic speech (`app/tools/voice_drive.py`)

32 cases (16 sentences, two macOS voices): calls, named treatments, free treatment sentences with an alarm open, talk with and without an alarm, status outside an alarm. Played into `VoiceService` block by block, with the app's own builders.

| Setup | Right | End of speech → event, median / worst | Engines loaded |
| --- | --- | --- | --- |
| Laptop, `cactus.toml` (Whistle + Needle 9L) | 32/32 (30/32 before the symptom keywords) | 93 / 235 ms | 1.2 s |
| Laptop, defaults (no model) | 18/32: free treatment sentences are not understood | 10 / 12 ms | 0.6 s |
| **Board, `cactus.toml`** | **32/32** | **790 / 1860 ms** | 5.6 s |
| Board, defaults | 18/32 | 87 / 104 ms | 3.1 s |

"End of speech" is when the segmenter closed the segment (after 400 ms of silence for a call, 700 ms for a sentence). These are synthetic voices in clean audio; the test with people in the hall is in [tests.md](tests.md).

### Memory on the board

Full app with `cactus.toml`, menu (14 Nov 2026, 00:01 UTC): MemAvailable 1959–1966 MB; trainer process 364–373 MB RSS (327 MB without the Cactus models, same boot); Needle worker process 89 MB RSS. Disk after installing package, engine and five model files: 1.9 GB free.

## Building rungs

A rung is the published checkpoint cut to N layers. `cactus build --layers N` does it; this command imports JAX (the package's `[train]` extra), inference does not. Nothing is trained.

```sh
# laptop, separate venv (Python 3.12). On an Intel Mac pin the last wheels that exist for it:
uv venv --python 3.12 .venv-train
uv pip install --python .venv-train/bin/python --only-binary sentencepiece,jaxlib,soxr \
  "cactus-compute[train]==4.2.0" "jax==0.4.38" "jaxlib==0.4.38" "flax>=0.10.2,<0.10.5" \
  "optax<0.2.5" "numpy<2.2" "sentencepiece<0.2.1"
CACTUS_TELEMETRY=0 .venv-train/bin/cactus download needle3.safetensors --out checkpoints   # 242 MB
CACTUS_TELEMETRY=0 .venv-train/bin/cactus build checkpoints/checkpoints/needle3.safetensors --layers 9 --out needle3-9L.cact
```

About 35 s per rung on the laptop. Output W4A8, so 16L (51 MB) is larger than the published 20L (35 MB, CQ2).

## Next step if the rungs are to get better: fine-tuning (not done)

`cactus finetune data.jsonl` trains a LoRA adapter, `cactus build --lora adapter.safetensors --layers N` merges and cuts it. The Cactus blog reports 18 to 36 points more per depth. What it would need here:
- training sentences in the runtime's JSONL format, apart from `needle_cases.json` so that a tuned rung is not measured on its own training data; status reports belong in them as "no call";
- a tuned rung has no confidence head (it reports `None`);
- the measurement with `needle_eval.py`, gate on and off, on the board.

## Design rules

- **Names first, model second.** A treatment named outright never waits for the model.
- **"No tool" is a valid answer**, and a model that fails means no treatment (a wrong treatment harms the patient).
- **Needle only while an alarm is open**, and only with a trigger word in the sentence.
- **Every text stands alone:** `reset()` before every call.
- **No network:** `load_cactus()` sets `CACTUS_TELEMETRY=0` and `HF_HUB_OFFLINE=1` before the import (C2, C4).
- **No transcripts outside `VoiceService`:** the log holds the treatment word and timing only.
- **The defaults need no model** (T3).

## Open points

- The test with people: 20 spoken instructions on the board, free and by name, and 20 plain commands as a cross-check ([tests.md](tests.md)).
- Licences: Whistle is Apache-2.0 (model card), the `cactus-compute` package is Apache-2.0 (its metadata). Needle's model licence still needs checking.
- The CPU governor: the numbers above are with `schedutil`; the hand-over measured with `performance`.
