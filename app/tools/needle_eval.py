#!/usr/bin/env python3
"""Check Needle rungs against the nurse's orders: the drug and the amount.

Rung quality does not grow steadily with depth and depends on the tools, so
a rung that passed someone else's cases says little about ours. The cases are
in tests/data/needle_cases.json: orders with a drug and an amount, drugs
named without one (standard dose), and talk that must give no order.

Pass rule for a rung (docs/needle-integration.md): at least 90 % of the
order and named cases exactly right (every drug and every amount), and at
most one false order on the talk cases. Talk that names a drug
("is the propofol ready?") is reported apart: by design it becomes a
standard dose.

Usage, in app/:  python tools/needle_eval.py models/needle3-9L.cact [more.cact ...] [--json] [--quiz]
Exit code: 0 if every rung given passed.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
from trainer.cactus_models.needle_evaluator import NeedleEvaluator  # noqa: E402
from trainer.cactus_models.needle_orders import NeedleOrders  # noqa: E402
from trainer.core.config import load  # noqa: E402
from trainer.quiz.question import QuestionBank  # noqa: E402

CASES_FILE = APP_DIR / "tests" / "data" / "needle_cases.json"
MIN_HIT_RATE = 0.9
MAX_FALSE_ORDERS = 1


def load_cases(path: Path = CASES_FILE) -> dict:
    with open(path) as f:
        return json.load(f)


def _median(values: list[float]) -> float:
    values = sorted(values)
    return values[len(values) // 2] if values else 0.0


def same(got: list[tuple[str, float | None]], expected: list[list]) -> bool:
    return sorted(got, key=str) == sorted(((w, None if a is None else float(a)) for w, a in expected), key=str)


def run(weights: Path, cfg, cases: dict, bank: QuestionBank | None, trigger_gate: bool = True) -> dict:
    started = time.perf_counter()
    orders = NeedleOrders(cfg.treatments, weights, min_confidence=cfg.voice.needle_min_confidence, require_trigger=trigger_gate)
    load_s = time.perf_counter() - started
    rows, model_ms = [], []
    for case in cases["orders"]:
        ran = not trigger_gate or orders.triggered(case["said"])
        t = time.perf_counter()
        got = [(m.word, m.amount) for m in orders.orders(case["said"])]
        elapsed = 1000 * (time.perf_counter() - t)
        if ran:
            model_ms.append(elapsed)
        rows.append({"kind": case["kind"], "said": case["said"], "expected": case["expected"], "got": got, "ok": same(got, case["expected"])})
    peak_ram_mb = orders.agent.peak_ram_mb
    orders.unload()
    first_ms = model_ms[0] if model_ms else 0.0  # includes the engine's warm-up
    model_ms = sorted(model_ms[1:])

    answers = None
    if bank is not None:
        evaluator = NeedleEvaluator(weights, cfg.voice.needle_min_confidence)
        ok = 0
        for case in cases["answers"]:
            question = bank.get(case["question"])
            evaluator.prepare(question)
            ok += evaluator.evaluate(question, case["said"]).choice == case["expected"]
        evaluator.unload()
        answers = f"{ok}/{len(cases['answers'])}"

    def count(kind: str) -> tuple[int, int]:
        sel = [r for r in rows if r["kind"] == kind]
        return sum(r["ok"] for r in sel), len(sel)

    hits = sum(r["ok"] for r in rows if r["kind"] in ("order", "named"))
    total = sum(r["kind"] in ("order", "named") for r in rows)
    talk_ok, talk_n = count("talk")
    false_orders = talk_n - talk_ok
    return {
        "weights": weights.name,
        "trigger_gate": trigger_gate,
        "hits": hits,
        "cases": total,
        "hit_rate": round(hits / total, 3) if total else 0.0,
        "orders": "%d/%d" % count("order"),
        "named": "%d/%d" % count("named"),
        "false_orders": false_orders,
        "talk_cases": talk_n,
        "named_talk_without_order": "%d/%d" % count("named_talk"),
        "answers": answers,
        "model_calls": len(model_ms) + (1 if first_ms else 0),
        "model_median_ms": round(_median(model_ms)),
        "model_worst_ms": round(model_ms[-1]) if model_ms else 0,
        "first_call_ms": round(first_ms),
        "load_s": round(load_s, 2),
        "peak_ram_mb": round(peak_ram_mb, 1),
        "passed": bool(total) and hits / total >= MIN_HIT_RATE and false_orders <= MAX_FALSE_ORDERS,
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
    p.add_argument("--no-trigger-gate", action="store_true", help="let every sentence reach the model")
    p.add_argument("--threads", type=int, default=None, help="engine threads (cactus.set_threads); default: the runtime's choice")
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
                f"{r['weights']}{'' if r['trigger_gate'] else ' (no trigger gate)'}: {'PASS' if r['passed'] else 'fail'}  "
                f"{r['hits']}/{r['cases']} right ({100 * r['hit_rate']:.0f} %; orders {r['orders']}, named {r['named']}), "
                f"false orders {r['false_orders']}/{r['talk_cases']}, drug-named talk without order {r['named_talk_without_order']}"
                + (f", quiz {r['answers']}" if r["answers"] else "")
                + f" | model call median {r['model_median_ms']} ms, worst {r['model_worst_ms']} ms ({r['model_calls']} calls, first {r['first_call_ms']} ms), "
                f"load {r['load_s']} s, peak {r['peak_ram_mb']} MB"
            )
            if not args.quiet:
                for f in r["failed"]:
                    print(f"   {f['kind']}: {f['said']!r} -> {f['got']} (expected {f['expected']})")
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
