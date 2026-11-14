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

With `--config cactus.toml` (Whistle + Needle 12L) unless noted. Rules: [PLAN.md](../PLAN.md#vitals-monitor-and-the-nurse).

| Case | Expected reaction | Observed |
| --- | --- | --- |
| a value drifts, nothing said | alarm line and yellow tile; after 6 s the nurse repeats it with the value; critical for 4 s: "critical", one life lost | |
| the right dose read from the dose card ("Propofol 50" at BIS 75) | read-back "Propofol 50 milligrams.", the value returns to normal in about 3 s, "stable again" | |
| too little ("Propofol 20" at BIS 75) | read-back; the value settles short, "BIS still at 63."; a second order finishes it; counted right | |
| too much ("Propofol 120" at BIS 63) | read-back, "That was too much", then "He is too deep now", recovers after a few seconds; counted as overdose | |
| oxygen as a setting ("Oxygen to 70 percent") | FiO2 tile shows 70 %; saturation recovers if that covers the need; afterwards the nurse weans it back to 30 % | |
| drug without an amount ("More propofol!") or keys 5, 6, 7 | "Standard dose. Propofol 30 milligrams."; fits some episodes, falls short or overshoots in others | |
| two orders in one sentence ("Propofol 40 and oxygen to 70") | both read back, both applied | |
| a correction ("Propofol 20, no wait, 30") | only 30 mg given | |
| the wrong drug | read-back, "That did not help", its side effects, the value in trouble gets worse | |
| an order with no alarm open | read-back, "That was not needed", counted as wrong | |
| a sentence without a drug during an alarm | "Pardon, doctor?"; the second time "Order a drug and how much, like propofol 40." | |
| talk with no alarm open ("his sats look good now") | nothing | |
| plain commands during an alarm ("Clamp!") | the instrument changes; no order | |
| without `cactus.toml` | drug names through the grammar at the standard dose; amounts are not heard | |

| Spoken orders on the board (people) | Tries | Right drug and amount | Wrong amount | Wrong drug | Nothing / "Pardon, doctor?" | Median latency (ms) |
| --- | --- | --- | --- | --- | --- | --- |
| with an amount | | | | | | |
| drug only (standard dose) | | | | | | |
| 20 plain commands as a cross-check | | | | | | |

## Co-op hand-over

| Case | Expected reaction | Observed |
| --- | --- | --- |
| surgeon calls, assistant picks that instrument and presses C | instrument changes; counted as a correct call | |
| assistant presses C on another instrument | "That is the wrong instrument."; counted as a wrong call; the call stays open | |
| assistant presses C without a call | nothing changes; "No instrument was called" on screen | |
| assistant waits longer than 8 s | the call runs out; nothing changes | |

## Needle on the board (`app/tools/needle_eval.py`)

Orders (42 cases) and talk (14), trigger gate on. 14 November 2026, JustuBoard, `schedutil`, game running.

| Rung | Right (of 42) | False orders (of 14) | Model call median (ms) | Worst (ms) | Peak memory (MB) |
| --- | --- | --- | --- | --- | --- |
| 9L | 36 | 0 | 1228 | 2031 | 91 |
| 12L | 40 | 0 | 1851 | 3615 | 115 |

The first version (treatments guessed from symptoms, 45 sentences) is in [needle-integration.md](needle-integration.md#earlier-task-guessing-the-treatment-from-symptoms-replaced).

| Case | Expected reaction | Observed |
| --- | --- | --- |
| `cactus-compute` not installed, or a model file missing | one log line; drug names through the Vosk grammar at the standard dose | |
