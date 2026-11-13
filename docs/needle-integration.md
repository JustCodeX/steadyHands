# Adding Needle (tool-calling model) to the voice pipeline

For whoever wires the Needle model in, and for their coding assistant. It says where the model plugs in, what the game already provides, and what must be measured before the change is merged.

Needle picks one function from a list and fills its arguments. It does not chat and it does not grade free text. Both jobs we have for it are shaped that way:

| Job | Input | Tool call we expect |
| --- | --- | --- |
| Commands | "could you hand me something to stop the bleeding" | `select_instrument(instrument="clamp")` |
| Quiz answers | "I would take a clamp for that" | `answer(choice="clamp")`, where `choice` is an enum of that question's options |

## Where it plugs in

```
mic -> SignalProcessor -> EnergyVad/Segmenter -> SpeechRecognizer -> CommandInterpreter -> CommandEvent
                                                                     ^^^^^^^^^^^^^^^^^^
                                                                     Needle goes here
```

| Piece | File | What it is |
| --- | --- | --- |
| `CommandInterpreter` | `app/trainer/voice/interpreter.py` | The interface: `interpret(text, allowed) -> Match \| None`, `phrases()`, `unload()` |
| `CommandMatcher` | `app/trainer/voice/command_matcher.py` | The default implementation (phrase lookup, fuzzy fallback, no model) |
| `ActionCatalog` | `app/trainer/game/actions.py` | The game's actions as tool schemas, and the way back from a tool call to a command word |
| `build_interpreter` | `app/trainer/voice/voice_service.py` | Picks the implementation from `voice.interpreter` |
| `VoiceService.handle_segment` | `app/trainer/voice/voice_service.py` | Calls the interpreter once per speech segment |
| `AnswerEvaluator` | `app/trainer/quiz/evaluator.py` | The interface for quiz answers: `evaluate(question, text) -> Verdict(choice, score)` |
| `KeywordEvaluator` | `app/trainer/quiz/evaluator.py` | The default implementation (looks for the options' phrases, no model) |
| `Question`, `QuestionBank` | `app/trainer/quiz/question.py`, `app/assets/questions.json` | Each question has option ids with phrases, and one correct option |
| `build_evaluator` | `app/trainer/voice/voice_service.py` | Picks the implementation from `voice.evaluator` |
| `VoiceService.handle_answer` | `app/trainer/voice/voice_service.py` | Calls the evaluator while a question is open, and publishes only the verdict (`AnswerEvent`) |

The game runs on command words (`CommandEvent.word`, the keys of `DEFAULT_COMMANDS` in `app/trainer/core/config.py`). A tool call is turned into such a word, so `GameEngine.on_command` does not change.

## Steps

1. **New class** `NeedleInterpreter(CommandInterpreter)` in `app/trainer/voice/needle_interpreter.py`. Import the Needle package inside `__init__`, not at module level, as `VoskRecognizer` does with `vosk`. The app must still start on a machine without the package.

   ```python
   class NeedleInterpreter(CommandInterpreter):
       def __init__(self, commands, model_path, catalog=None):
           self._keywords = CommandMatcher(commands)      # cascade, see below
           self._catalog = catalog or ActionCatalog()
           self._model = None                             # loaded on first use

       def interpret(self, text, allowed=None):
           hit = self._keywords.interpret(text, allowed)
           if hit is not None and hit.score == 1.0:       # the phrase is in the text
               return hit
           call = self._call_model(text, self._catalog.schemas(allowed))
           if call is None:                               # the model chose no tool
               return None
           word = self._catalog.command_word(call.name, call.arguments)
           return Match(word=word, score=call.score) if word else None

       def phrases(self):
           return self._keywords.phrases()

       def unload(self):
           self._model = None
   ```

2. **Select it** in `build_interpreter`: replace the warning in the `"needle"` branch with the real constructor. Keep the fallback to `CommandMatcher` when loading fails, with a log line, as `build_recognizer` does for Vosk.

3. **Config** (`VoiceConfig` in `app/trainer/core/config.py`): add `needle_model: str` for the model path. To try it, in a TOML file:

   ```toml
   [voice]
   interpreter = "needle"
   command_vocabulary = "open"
   ```

4. **Model download**: add it to `app/setup/download_models.sh`. Models live in `app/models/`, which is git-ignored.

5. **Quiz answers**: a second class `NeedleEvaluator(AnswerEvaluator)`. Build one tool, `answer(choice)`, whose enum is `list(question.options)`, with the question text and each option's phrases in the description. Return `Verdict(choice, score)`, or `Verdict(None)` when the model chooses no tool: the game then asks the player to say it again. Select it in `build_evaluator` (`voice.evaluator = "needle"`). Spoken answers already use the open vocabulary (`voice.answer_vocabulary = "open"`), so nothing else changes. Share one loaded model between the interpreter and the evaluator.

6. **Tests** in `app/tests/`: a fake model that returns fixed tool calls, then check that a valid call becomes the right `CommandEvent`, that an unknown tool or argument gives no event, and that "no tool" stays silent. `tests/test_actions.py` and `tests/test_voice_pipeline.py` show the pattern (`FakeRecognizer`, `FakeAudio`).

## Design rules

**The recogniser must hear free speech.** By default Vosk is restricted to the command phrases (`voice.command_vocabulary = "restricted"`), so the interpreter only ever sees those phrases and Needle has nothing to do. With `"open"` the same Vosk model transcribes freely. The open vocabulary is less robust in hall noise; that is the price, and it needs measuring.

**Keyword match first, model second.** If the transcript contains a command phrase, use it and skip the model. That keeps the common case ("Clamp!") under one second and saves energy (criterion C3). Only run Needle on sentences without a direct hit.

**Pass only the tools that make sense now.** `GameEngine.available_commands()` lists the command words valid in the current state. `ActionCatalog.schemas(allowed)` drops every other action and every other enum value. A shorter tool list means a shorter prompt and fewer wrong calls. `VoiceService` does not know the game state yet and passes `allowed=None`; to supply it, let the engine publish the list as an event and keep the latest one in `VoiceService`. Services never call each other directly.

**"No tool" is a valid answer.** Players talk to each other, most of all in co-op. Speech that is not a command must return `None`, which the game ignores silently. Do not force a tool call.

**Confidence.** `VoiceService` takes `min(match.score, transcript.confidence)` and compares it with `voice.confidence_threshold` (0.6). Below it, the patient asks "Pardon?". If Needle gives no score, return 1.0 for a valid call and rely on the recogniser's confidence.

**Load late, unload when idle.** Load the model on the first call, not at start-up. `VoiceService.stop()` already calls `interpreter.unload()`.

**No transcripts outside `VoiceService`.** Events and logs carry command words and timings only (criteria C2 and C4). The one exception is the debug panel behind `voice.debug_asr`. Do not log the text you pass to the model.

**The keyword matcher stays the default.** The minimum version must work without a language model (criterion T3). Needle is an option switched on in the config, and the game must stay playable when it fails to load.

## Measure before merging

Record the numbers in `docs/measurements.md`, on the board, with the full app running.

| What | How | Limit |
| --- | --- | --- |
| Memory | `free -m` and process RSS (the app logs both to `app/logs/metrics.csv`), with and without Needle | At least 1 GB available (C1); the median was about 2.1 GB before Needle |
| Latency | End of speech to `CommandEvent`, median and worst of 20 sentences | 3–5 s required (P6); our own target for plain commands is under 1 s |
| Disk | `df -h /` after the download | About 2.7 GB were free before |
| Recognition | 20 plain commands and 20 free sentences in hall noise: correct, wrong, missed | Plain commands must not get worse than with the restricted vocabulary |
| CPU | Per state from `metrics.csv` | For the energy numbers (C3) |

## Rows in PLAN.md that change

| Row | Change |
| --- | --- |
| T3 | "No LLM in the code" becomes: the default configuration uses no language model; Needle is optional and limited to choosing one of our tool calls |
| C1 and the memory budget table | Add Needle's measured memory |
| C3 | Add the cascade (model only when no phrase matched) and the measured CPU cost |
| Licenses | Add Needle's license from its model card |
| Speech pipeline, step 4/5 | Mention the interpreter step |

## Open questions for the Needle owner

- Which Needle generation and size? Public write-ups mention 14 MB to 29 MB files and about 28 MB of memory per session. These come from the vendor and from second-hand articles, so check the official repository (`github.com/cactus-compute/needle`) and measure on the board.
- Does the Python package install on the board (Debian 13, aarch64, Python 3.13, no system `pip`; `app/setup/board_setup.sh` bootstraps pip into `app/.venv`)?
- Does it return a score or log-probability per call?
- How does it behave with an empty or one-word transcript?
