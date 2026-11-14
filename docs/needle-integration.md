# Whistle and Needle (Cactus) for the nurse's orders

Two optional models from Cactus Compute serve one mechanic: the **vitals monitor**. When a value goes wrong, the surgeon orders a drug and an amount from the nurse ("Propofol 40.", "Oxygen to 60 percent.", "Push 10 micrograms of adrenaline."). **Whistle** (speech-to-text) hears the order, **Needle** (tool calling) reads the drug and the amount: one of three tools, each with one integer parameter.

This is the part a keyword list cannot do: the number, its unit and its binding to the right drug, two orders in one sentence ("Give him 40 of propofol and turn the oxygen to 70."), corrections ("Propofol 20, no wait, 30."). The game rules are in [PLAN.md](../PLAN.md#vitals-monitor-and-the-nurse).

**Every older voice command stays on the Vosk grammar.** Instruments, `steady`, `light`, `cancel`, `repeat`, `help`, `pause`, `continue` and `new game` never go through Whistle or Needle, and the two paths never fire each other's words.

Status (14 Nov 2026): checked against the source of `cactus-compute` 4.2.0 and run on a laptop and on the board. Rung **12L** reads 40 of 42 test orders right and gives no order for 14 sentences of talk (laptop). No fine-tuning (postponed until real-speaker tests show it is needed).

## How a segment is decided

`trainer/voice/understanding.py` (`CommandUnderstanding`). Both recognisers hear the same speech segment.

1. **Short call with a command phrase** ("Clamp!", under 1.2 s): the Vosk grammar decides at once. Whistle never runs.
2. **Longer segment, or one the grammar did not catch:** Whistle transcribes it when it ends, biased towards the drug and unit words (`ORDER_WORDS`).
   - **No drug named:** never an order; the model does not run. The grammar's result stands as before. During an alarm (`InstructionWindow` from the engine) the nurse says "Pardon, doctor?", the second time how to order.
   - **A drug named:** Needle reads the orders (`NeedleOrders`). Each order is a `CommandEvent` with `amount`.
   - **A drug named without a usable amount** ("More propofol!"): the standard dose (`vitals.standard_doses`). It fits about half of the episodes.
3. **Without Whistle** (the default config, or a missing model), the drug names join the Vosk grammar: orders at the standard dose, so the game is playable by voice without any model (criterion T3), and with keys 5, 6, 7.

## Switching it on

1. On the board, in the app's venv: `pip install -r requirements-cactus.txt` (pinned to 4.2.0).
2. Once, while online: `python -m cactus fetch`. The runtime downloads its engine library on first use, and the app runs it with `HF_HUB_OFFLINE=1`. `WITH_CACTUS=1 setup/download_models.sh` does this and downloads `whistle.cact`.
3. Copy `needle3-12L.cact` into `app/models/` (built on a laptop, see [Building rungs](#building-rungs)).
4. `python -m trainer --config cactus.toml`, or set `STEADYHANDS_CONFIG=cactus.toml` for the autostart.

If the package or a file is missing, the app logs one line and runs as in step 3 of the list above.

## What was checked against the runtime

Read in the package source (`cactus/agent/text.py`, `whistle.py`, `_worker.py`, `tools.py`, `grounding.py`) and confirmed by `tests/test_cactus_real.py` (runs only with the package and the models):

| Assumption in the first version | Finding | Change |
| --- | --- | --- |
| `Cactus.run()` executes the tool and returns its confidence | `run()` executes the tools, then runs the model **a second time** on their results and returns that turn's envelope | `NeedleAgent` uses `complete()`, which returns `function_calls`, `suppressed_calls`, `confidence` and `validation` of the first turn without executing anything. Half the latency |
| Tools as Python functions with a runtime `Literal` | The runtime also takes JSON schemas directly | Tools are JSON schemas from `ActionCatalog`, with an integer parameter (min, max) |
| — | The runtime checks numbers against the text and lists invented ones in `validation.ungrounded` | `NeedleAgent.calls()` drops such calls: "Propofol." or "his sats look good now" give no order |
| — | Two calls to the same tool for a correction ("20, no wait, 30") | The last call per tool counts |
| Several agents in one process | Weights other than the published base run in a **worker process** of the runtime's own (one per agent) | `unload()` closes the worker; one Needle agent in the game |
| `confidence` is a number | `None` for weights without a confidence head (e.g. LoRA builds). Rungs from `cactus build --layers` keep the head | `None` counts as 1.0, with one log line |
| `transcribe(list_of_floats, ...)` | Takes a float32 array; returns `text`, `language`, and `words` with `probability`. Writes numbers as digits ("30 mg", "60%") | `WhistleRecognizer` passes the array |
| Telemetry and hub off | `CACTUS_TELEMETRY=0` is read per call; `HF_HUB_OFFLINE` must be set before `huggingface_hub` is imported | Unchanged: `load_cactus()` sets both before the import |
| — | Tool schemas take `triggers` (request regexes) | Each tool triggers on its drug's names; without a drug name the model is not run |
| — | Whistle often leaves off the final full stop, and Needle then missed the amount ("Push 10 micrograms of adrenaline") | `NeedleOrders` adds the full stop |

## Tools

`ActionCatalog(MODEL_ACTIONS)` in `trainer/game/actions.py`:

| Tool | Order word | Parameter | Range | Triggers |
| --- | --- | --- | --- | --- |
| `set_oxygen` | `oxygen` | `percent` | 21–100 | oxygen, O2, FiO2 |
| `give_propofol` | `propofol` | `milligrams` | 5–200 | propofol |
| `give_adrenaline` | `adrenaline` | `micrograms` | 5–100 | adrenaline, epinephrine |

## Measurements

### Orders (drug and amount), the current task

Test data: `app/tests/data/needle_cases.json`, written 14 Nov 2026 by one author (one style; real speakers decide). 36 orders with amounts (digits and some in words, units or not, two orders in one sentence, corrections), 6 drugs named without an amount, 14 sentences of talk without a drug, 4 sentences of talk that name a drug. Tool: `app/tools/needle_eval.py`. Pass rule: at least 90 % of orders and named drugs exactly right (every drug and every amount), at most one false order on talk.

Laptop (Intel i9-9880H, macOS):

| Rung | Right (of 42) | False orders (of 14) | Model call median / worst | Peak memory |
| --- | --- | --- | --- | --- |
| 4L | 26 (62 %) | 0 | 65 / 690 ms | 59 MB |
| 6L | 29 (69 %) | 0 | 76 / 271 ms | 65 MB |
| 8L | 36 (86 %) | 0 | 80 / 843 ms | 86 MB |
| 9L | 35 (83 %) | 0 | 95 / 178 ms | 89 MB |
| **12L** | **40 (95 %) PASS** | **0** | 131 / 200 ms | 113 MB |
| 16L | 38 (90 %) PASS | 0 | 179 / 667 ms | 141 MB |
| 20L (published) | 40 (95 %) PASS | 0 | 197 / 388 ms | 114 MB |

- 12L is the smallest rung that passes and the default. Its two misses: "FiO2 70." (no call on any rung) and one of the two-order sentences.
- Talk that names a drug ("Is the propofol ready?", "We gave 30 of propofol earlier.") becomes an order at the standard dose or with the amount, on every rung. That is the price of "a named drug without an amount gets the standard dose"; it is rare in a round.
- Board numbers: [measurements.md](measurements.md).

### Earlier task: guessing the treatment from symptoms (replaced)

Before the dosing mechanic, Needle had to map free sentences like "he can't breathe" to one of three treatments without parameters. With the published rungs that did not work well enough: without a trigger gate every rung called a tool for almost any talk (23–38 of 39 sentences), with the gate 10–11 of 12 status reports ("his sats look good now") still triggered, and depth hardly mattered (26–29 of 45 right, 9L to 20L, laptop and board). Reading an amount is a task the model does well; telling "dropping" from "fine" is not.

### Whistle and the drug names (synthetic voices, open point)

With the macOS voices, Whistle needs its keyword bias for "propofol": without keywords 0 of 10 sentences, with keywords 5 of 5 for the voice Samantha, but 0 of 5 for Daniel (British), and Karen, Moira, Rishi and Tessa also heard "probable", "proper full" and similar. "Oxygen" and "adrenaline" came through for all of them. Synthetic voices say little about people; the test with real speakers on the board decides whether "propofol" needs a second name.

### The whole voice path (`app/tools/voice_drive.py`, synthetic voices)

32 cases (16 sentences, voices Samantha and Daniel): calls, orders with amounts, two orders, a correction, drugs without an amount, talk with and without an alarm. Played into `VoiceService` with the app's own builders. Latest numbers: [measurements.md](measurements.md).

## Building rungs

A rung is the published checkpoint cut to N layers. `cactus build --layers N` does it; this command imports JAX (the package's `[train]` extra), inference does not. Nothing is trained.

```sh
# laptop, separate venv (Python 3.12). On an Intel Mac pin the last wheels that exist for it:
uv venv --python 3.12 .venv-train
uv pip install --python .venv-train/bin/python --only-binary sentencepiece,jaxlib,soxr \
  "cactus-compute[train]==4.2.0" "jax==0.4.38" "jaxlib==0.4.38" "flax>=0.10.2,<0.10.5" \
  "optax<0.2.5" "numpy<2.2" "sentencepiece<0.2.1"
CACTUS_TELEMETRY=0 .venv-train/bin/cactus download needle3.safetensors --out checkpoints   # 242 MB
CACTUS_TELEMETRY=0 .venv-train/bin/cactus build checkpoints/checkpoints/needle3.safetensors --layers 12 --out needle3-12L.cact
```

About 35 s per rung on the laptop. Output W4A8, so 16L (51 MB) is larger than the published 20L (35 MB, CQ2). 12L: 39 MB.

## If the rungs are to get better: fine-tuning (not done)

`cactus finetune data.jsonl` trains a LoRA adapter, `cactus build --lora adapter.safetensors --layers N` merges and cuts it. The Cactus blog reports 18 to 36 points more per depth. What it would need here: training orders in the runtime's JSONL format, apart from `needle_cases.json`; talk that names a drug as "no call"; a tuned rung has no confidence head (it reports `None`); then `needle_eval.py` on the board.

## Design rules

- **The drug must be named.** Speech without a drug name is never an order and costs no model run (C3).
- **Amounts only from the text.** An amount the model invents is dropped (the runtime's grounding check); then the standard dose applies.
- **A model that fails means the standard dose** for every drug named, never a guess at another drug.
- **Every text stands alone:** `reset()` before every call.
- **No network:** `load_cactus()` sets `CACTUS_TELEMETRY=0` and `HF_HUB_OFFLINE=1` before the import (C2, C4).
- **No transcripts outside `VoiceService`:** the log holds the order word, the amount and timing only.
- **The defaults need no model** (T3).

## Open points

- The test with people: 20 spoken orders on the board, with and without amounts, and 20 plain commands as a cross-check ([tests.md](tests.md)).
- Whether "propofol" needs a second spoken name (see above).
- Licences: Whistle is Apache-2.0 (model card), the `cactus-compute` package is Apache-2.0 (its metadata). Needle's model licence still needs checking.
- The CPU governor: board numbers are with `schedutil`; the team hand-over measured with `performance`.
