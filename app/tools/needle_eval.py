#!/usr/bin/env python3
"""Check a Needle rung against this game's own tools, on the board.

Rung quality does not grow steadily with depth and depends on the tools, so a
rung that passed someone else's cases says little about ours. Every case is a
sentence without a command phrase (those never reach the model) and the
command, or quiz option, it should lead to. None means: no tool.

Usage, in app/:  python tools/needle_eval.py models/needle3-9L.cact [more.cact ...] [--json]
Exit code: 0 if every rung given passed every case.
"""
from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from trainer.cactus_models.needle_evaluator import NeedleEvaluator  # noqa: E402
from trainer.cactus_models.needle_interpreter import NeedleInterpreter  # noqa: E402
from trainer.core.config import load  # noqa: E402
from trainer.quiz.question import QuestionBank  # noqa: E402

# (what the player says, the command word it should become)
COMMAND_CASES: list[tuple[str, str | None]] = [
    ("i need something to stop the bleeding", "clamp"),
    ("hand me the thing to grab that splinter", "forceps"),
    ("wipe the blood away please", "swab"),
    ("give me the blade", "scalpel"),
    ("it is too dark in here i can not see", "light"),
    ("my hand is shaking slow it down", "steady"),
    ("no that was the wrong one take it back", "cancel"),
    ("what did you just say", "repeat"),
    ("what can i say to you", "help"),
    ("hold on i need a break", "pause"),
    ("okay lets carry on", "continue"),
    ("lets begin another round", "new game"),
    ("did you watch the match last night", None),
    ("i am so hungry right now", None),
    ("that was close", None),
]

# (question id, what the player says, the option it should become)
ANSWER_CASES: list[tuple[str, str, str | None]] = [
    ("bleeding_vessel", "the one that squeezes the vessel shut", "clamp"),
    ("remove_splinter", "the one you pick small things up with", "forceps"),
    ("clear_view", "something that soaks it up", "swab"),
    ("first_cut", "the sharp blade", "scalpel"),
    ("fast_pulse", "that is far too fast", "no"),
    ("glove_touch", "i would change it first", "no"),
    ("count_swabs", "of course always", "yes"),
    ("call_back", "they say it back to confirm", "yes"),
    ("away_from_heart", "the ones with the pulse in them", "arteries"),
    ("oxygen", "the one we breathe in", "oxygen"),
    ("bleeding_vessel", "i have no idea", None),
    ("fast_pulse", "can you say that again please", None),
]


def run(weights: Path, cfg, bank: QuestionBank) -> dict:
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    started = time.perf_counter()
    interpreter = NeedleInterpreter(cfg.commands, weights, min_confidence=cfg.voice.needle_min_confidence)
    load_s = time.perf_counter() - started
    evaluator = NeedleEvaluator(weights, cfg.voice.needle_min_confidence)
    rows, times = [], []
    for said, expected in COMMAND_CASES:
        t = time.perf_counter()
        match = interpreter.interpret(said)
        times.append(time.perf_counter() - t)
        got = match.word if match else None
        rows.append({"kind": "command", "said": said, "expected": expected, "got": got, "ok": got == expected})
    prepare_times = []
    for question_id, said, expected in ANSWER_CASES:
        question = bank.get(question_id)
        t = time.perf_counter()
        evaluator.prepare(question)
        prepare_times.append(time.perf_counter() - t)
        t = time.perf_counter()
        got = evaluator.evaluate(question, said).choice
        times.append(time.perf_counter() - t)
        rows.append({"kind": "answer", "said": said, "expected": expected, "got": got, "ok": got == expected})
    times.sort()
    rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "weights": weights.name,
        "passed": sum(r["ok"] for r in rows),
        "cases": len(rows),
        "median_ms": round(1000 * times[len(times) // 2]),
        "worst_ms": round(1000 * times[-1]),
        "load_s": round(load_s, 2),
        "prepare_question_worst_ms": round(1000 * max(prepare_times)),
        "rss_added_mb": round((rss_after - rss_before) / 1024),  # ru_maxrss is in kB on Linux
        "failed": [r for r in rows if not r["ok"]],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("weights", nargs="+", type=Path)
    p.add_argument("--config", help="TOML file with overrides")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    cfg = load(args.config)
    bank = QuestionBank.load(cfg.quiz.questions_file)
    results = [run(w, cfg, bank) for w in args.weights]
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(
                f"{r['weights']}: {r['passed']}/{r['cases']} passed, median {r['median_ms']} ms, worst {r['worst_ms']} ms, "
                f"load {r['load_s']} s, new question {r['prepare_question_worst_ms']} ms, +{r['rss_added_mb']} MB"
            )
            for f in r["failed"]:
                print(f"   {f['kind']}: {f['said']!r} -> {f['got']} (expected {f['expected']})")
    return 0 if all(r["passed"] == r["cases"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
