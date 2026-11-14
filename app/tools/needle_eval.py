#!/usr/bin/env python3
"""Check Needle rungs against this game's own tools.

Rung quality does not grow steadily with depth and depends on the tools, so a
rung that passed someone else's cases says little about ours. The cases are
in tests/data/needle_cases.json: sentences without a command phrase (those
never reach the model) and the command word, or quiz option, each should
lead to (null: no tool).

Needle only decides the vitals-monitor treatments. Pass rule for a rung
(docs/needle-integration.md): at least 90 % of the treatment sentences right,
and at most one false trigger over the talk and old-command sentences.

Usage, in app/:  python tools/needle_eval.py models/needle3-9L.cact [more.cact ...] [--json] [--quiz]
Exit code: 0 if every rung given passed.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
from trainer.cactus_models.needle_evaluator import NeedleEvaluator  # noqa: E402
from trainer.cactus_models.needle_interpreter import NeedleInterpreter  # noqa: E402
from trainer.core.config import load  # noqa: E402
from trainer.game.actions import MODEL_ACTIONS  # noqa: E402
from trainer.quiz.question import QuestionBank  # noqa: E402

CASES_FILE = APP_DIR / "tests" / "data" / "needle_cases.json"
MIN_HIT_RATE = 0.9
MAX_FALSE_TRIGGERS = 1
TRIGGERS = [re.compile(t, re.IGNORECASE) for a in MODEL_ACTIONS for t in a.triggers]


def load_cases(path: Path = CASES_FILE) -> dict:
    with open(path) as f:
        return json.load(f)


def has_trigger_word(text: str) -> bool:
    return any(t.search(text) for t in TRIGGERS)


def _median(values: list[float]) -> float:
    values = sorted(values)
    return values[len(values) // 2] if values else 0.0


def run(weights: Path, cfg, cases: dict, bank: QuestionBank | None, trigger_gate: bool = True) -> dict:
    started = time.perf_counter()
    interpreter = NeedleInterpreter(cfg.treatments, weights, min_confidence=cfg.voice.needle_min_confidence, require_trigger=trigger_gate)
    load_s = time.perf_counter() - started
    rows, times = [], []
    for case in cases["commands"]:
        said, expected = case["said"], case["expected"]
        t = time.perf_counter()
        match = interpreter.interpret(said)
        elapsed = time.perf_counter() - t
        times.append(elapsed)
        got = match.word if match else None
        ran = not trigger_gate or has_trigger_word(said)  # the gate lets it through: the model ran
        rows.append({"kind": case["kind"], "said": said, "expected": expected, "got": got, "ok": got == expected,
                     "trigger_word": has_trigger_word(said), "model_ms": 1000 * elapsed if ran else None})
    peak_ram_mb = interpreter._agent.peak_ram_mb
    model_ms = [r["model_ms"] for r in rows if r.get("model_ms") is not None]
    first_call_ms = model_ms[0] if model_ms else 0.0  # includes the engine's warm-up
    model_ms = sorted(model_ms[1:])
    interpreter.unload()

    if bank is not None:
        evaluator = NeedleEvaluator(weights, cfg.voice.needle_min_confidence)
        for case in cases["answers"]:
            question = bank.get(case["question"])
            evaluator.prepare(question)
            t = time.perf_counter()
            got = evaluator.evaluate(question, case["said"]).choice
            times.append(time.perf_counter() - t)
            rows.append({"kind": "answer", "said": case["said"], "expected": case["expected"], "got": got, "ok": got == case["expected"], "trigger_word": None})
        evaluator.unload()

    tool_rows = [r for r in rows if r["kind"] == "treatment"]
    talk_rows = [r for r in rows if r["kind"] in ("talk", "status", "old_command")]
    per_word: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in tool_rows:
        per_word[r["expected"]][0] += r["ok"]
        per_word[r["expected"]][1] += 1
    hits = sum(r["ok"] for r in tool_rows)
    false_triggers = sum(not r["ok"] for r in talk_rows)
    plain = [r for r in tool_rows if not r["trigger_word"]]
    times.sort()
    return {
        "weights": weights.name,
        "trigger_gate": trigger_gate,
        "tool_hits": hits,
        "tool_cases": len(tool_rows),
        "hit_rate": round(hits / len(tool_rows), 3) if tool_rows else 0.0,
        "false_triggers": false_triggers,
        "talk_cases": len(talk_rows),
        "false_triggers_by_kind": {k: sum(not r["ok"] for r in talk_rows if r["kind"] == k) for k in ("talk", "status", "old_command")},
        "hits_without_trigger_word": f"{sum(r['ok'] for r in plain)}/{len(plain)}",
        "per_word": {w: f"{ok}/{n}" for w, (ok, n) in sorted(per_word.items())},
        "answers": f"{sum(r['ok'] for r in rows if r['kind'] == 'answer')}/{sum(r['kind'] == 'answer' for r in rows)}" if bank else None,
        "median_ms": round(1000 * _median(times)),
        "model_calls": len(model_ms) + (1 if first_call_ms else 0),
        "model_median_ms": round(_median(model_ms)) if model_ms else 0,
        "model_worst_ms": round(model_ms[-1]) if model_ms else 0,
        "first_call_ms": round(first_call_ms),
        "worst_ms": round(1000 * times[-1]) if times else 0,
        "load_s": round(load_s, 2),
        "peak_ram_mb": round(peak_ram_mb, 1),
        "passed": bool(tool_rows) and hits / len(tool_rows) >= MIN_HIT_RATE and false_triggers <= MAX_FALSE_TRIGGERS,
        "failed": [r for r in rows if not r["ok"]],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("weights", nargs="+", type=Path)
    p.add_argument("--config", help="TOML file with overrides")
    p.add_argument("--cases", type=Path, default=CASES_FILE)
    p.add_argument("--quiz", action="store_true", help="also judge the quiz answers (one model per question)")
    p.add_argument("--json", action="store_true")
    p.add_argument("--quiet", action="store_true", help="no list of failed cases")
    p.add_argument("--threads", type=int, default=None, help="engine threads (cactus.set_threads); default: the runtime's choice")
    p.add_argument("--no-trigger-gate", action="store_true", help="let every sentence reach the model, as without voice.needle_require_trigger")
    args = p.parse_args(argv)
    cfg = load(args.config)
    if args.threads is not None:
        from trainer.cactus_models.runtime import load_cactus

        load_cactus().set_threads(args.threads)
    cases = load_cases(args.cases)
    bank = QuestionBank.load(cfg.quiz.questions_file) if args.quiz else None
    results = [run(w, cfg, cases, bank, trigger_gate=not args.no_trigger_gate) for w in args.weights]
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            print(
                f"{r['weights']}{'' if r['trigger_gate'] else ' (no trigger gate)'}: {'PASS' if r['passed'] else 'fail'}  tools {r['tool_hits']}/{r['tool_cases']} ({100 * r['hit_rate']:.0f} %), "
                f"false triggers {r['false_triggers']}/{r['talk_cases']} {r['false_triggers_by_kind']}, without trigger word {r['hits_without_trigger_word']}"
                + (f", quiz {r['answers']}" if r["answers"] else "")
                + f" | model call median {r['model_median_ms']} ms, worst {r['model_worst_ms']} ms ({r['model_calls']} calls, first {r['first_call_ms']} ms), "
                f"all cases median {r['median_ms']} ms, load {r['load_s']} s, peak {r['peak_ram_mb']} MB"
            )
            print("   " + "  ".join(f"{w} {v}" for w, v in r["per_word"].items()))
            if not args.quiet:
                for f in r["failed"]:
                    print(f"   {f['kind']}: {f['said']!r} -> {f['got']} (expected {f['expected']})")
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
