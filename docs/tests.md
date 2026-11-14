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

## Vitals monitor and the nurse

With `--config cactus.toml` (Whistle + Needle 9L) unless noted. Synthetic-voice
run for comparison: [needle-integration.md](needle-integration.md#measurements).

| Case | Expected reaction | Observed |
| --- | --- | --- |
| a value drifts, nothing said | alarm line and blinking tile; after 6 s the nurse repeats it with the value; critical for 4 s: "critical", one life lost | |
| right treatment by name ("Oxygen!") | read-back ("More oxygen."), value recovers in about 3 s, "stable again" | |
| right treatment in other words ("he can't breathe") | as above, after about a second | |
| wrong treatment | read-back, "That did not help", its side effect on the monitor, the value jumps worse | |
| treatment with no alarm open | read-back, "That was not needed", counted as wrong | |
| sentence without a treatment during an alarm | "Pardon, doctor?"; the second time she names oxygen, anaesthesia, adrenaline | |
| talk with no alarm open ("his sats look good now") | nothing | |
| plain commands during an alarm ("Clamp!") | the instrument changes; no treatment | |
| keys 5, 6, 7 | the three treatments | |
| without `cactus.toml` | treatments by name through the grammar; free sentences do nothing | |

| Spoken instructions on the board (20, people) | Tries | Right | Wrong treatment | Nothing / "Pardon?" | Median latency (ms) |
| --- | --- | --- | --- | --- | --- |
| by name | | | | | |
| in other words | | | | | |
| 20 plain commands as a cross-check | | | | | |

## Co-op hand-over

| Case | Expected reaction | Observed |
| --- | --- | --- |
| surgeon calls, assistant picks that instrument and presses C | instrument changes; counted as a correct call | |
| assistant presses C on another instrument | "That is the wrong instrument."; counted as a wrong call; the call stays open | |
| assistant presses C without a call | nothing changes; "No instrument was called" on screen | |
| assistant waits longer than 8 s | the call runs out; nothing changes | |

## Needle on the board (`app/tools/needle_eval.py`)

Treatments only (45 sentences), false triggers out of 51; trigger gate on.
14 November 2026, JustuBoard, `schedutil`, game running.

| Rung | Treatments right | False triggers (talk / status / older commands) | Model call median (ms) | Worst (ms) | Peak memory (MB) |
| --- | --- | --- | --- | --- | --- |
| 4L | 28 | 0 / 10 / 0 | 693 | 6490 | 61 |
| 6L | 26 | 0 / 10 / 0 | 699 | 8969 | 67 |
| 9L | 29 | 0 / 11 / 0 | 1033 | 1313 | 90 |
| 12L | 29 | 0 / 11 / 0 | 1242 | 1692 | 114 |

| Case | Expected reaction | Observed |
| --- | --- | --- |
| `cactus-compute` not installed, or a model file missing | one log line; treatments by name through the Vosk grammar | |
