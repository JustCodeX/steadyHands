# Test runs

Evidence for the criteria check. One line per run, with date and who ran it.

## P2: 10 demo runs in a row without a restart

| # | Date | Level | Result | Notes |
| --- | --- | --- | --- | --- |

## P3: help, repeat, cancel (5 times each)

| Command | Tries | Recognised | Notes |
| --- | --- | --- | --- |
| help | | | |
| repeat | | | |
| cancel | | | |

## P5: misheard speech

| Spoken | Expected reaction | Observed |
| --- | --- | --- |
| unclear mumble | "Pardon?" on screen and spoken | |
| two unclear in a row | patient lists fitting commands | |
| unrelated sentence | ignored silently | |
| wrong tool then "cancel" | previous tool restored | |

## Voice commands in hall noise (20 commands)

| Command | Tries | Correct | Wrong | Missed |
| --- | --- | --- | --- | --- |

## Quiz answers in whole sentences (20 answers)

With `voice.answer_vocabulary = "both"` (the default). Run with `--config debug-asr.toml` to see what the recognisers heard; add words they mishear to the option's phrases in `app/assets/questions.json`. Try `"open"` and `"keywords"` only if `"both"` gives wrong verdicts or is too slow.

| Setting | Tries | Right verdict | Wrong verdict | Unclear ("Pardon?") | Not heard |
| --- | --- | --- | --- | --- | --- |
| both, Vosk | | | | | |
| both, Whistle (`answer_engine = "whistle"`) | | | | | |
| open | | | | | |
| keywords | | | | | |

| Case | Expected reaction | Observed |
| --- | --- | --- |
| right answer in a sentence | "Correct." and no penalty | |
| wrong answer | "Wrong.", the right answer is spoken, 5 s less, one stress arrow | |
| no answer for 8 s | "Too slow.", same penalty as a wrong answer | |
| unclear answer, then a clear one | "Pardon?", then the verdict | |
| "repeat" while a question is open | the question is spoken again | |
| an instrument word as the answer | counts as the answer; the instrument in hand does not change | |
| 20 plain commands afterwards | recognised as well as before the quiz was added | |

## Co-op hand-over

| Case | Expected reaction | Observed |
| --- | --- | --- |
| surgeon calls, assistant picks that instrument and presses C | instrument changes; counted as a correct call | |
| assistant presses C on another instrument | "That is the wrong instrument."; counted as a wrong call; the call stays open | |
| assistant presses C without a call | nothing changes; "No instrument was called" on screen | |
| assistant waits longer than 8 s | the call runs out; nothing changes | |

## Needle on the board (`app/tools/needle_eval.py`)

| Rung | Passed | Median (ms) | Worst (ms) | Memory added (MB) | Failed cases |
| --- | --- | --- | --- | --- | --- |
| 9L | | | | | |
| 12L | | | | | |
| 19L | | | | | |

| Case, with `--config cactus.toml` | Expected reaction | Observed |
| --- | --- | --- |
| answer that names the option ("the clamp") | verdict at once; the model is not asked | |
| answer in other words ("the thing you cut with") | right verdict after about a second | |
| answer that fits no option ("I have no idea") | "Pardon?" | |
| `cactus-compute` not installed, or a model file missing | one log line; the game runs with the keyword evaluator | |
