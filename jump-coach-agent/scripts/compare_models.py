"""Run the same 5 jump-height prompts on each model and compare.

Usage:
    uv run python -m scripts.compare_models                 # models from COMPARE_MODELS
    uv run python -m scripts.compare_models anthropic:claude-sonnet-5-5 ollama:qwen3:4b

Per model it reports: tool-call success (the tool was called with exactly the
right flight times), correct result (the final answer states the right cm
value), and seconds per prompt. A warm-up call (model load / connection) is
run first and excluded from the per-prompt timing.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.coach.graph import build_graph
from src.llm import get_llm
from src.tools import jump_height_cm

RESULTS_PATH = Path(__file__).resolve().parent.parent / "results" / "compare_models.json"
TOLERANCE_CM = 0.2  # allows the 1-decimal rounding asked for in the coach prompt


@dataclass
class Case:
    prompt: str
    flight_times_s: list[float]
    expected_cm: float


def _gain(before: float, after: float) -> float:
    return round(jump_height_cm(after) - jump_height_cm(before), 2)


CASES = [
    Case("My flight time on a jump mat was 0.52 seconds. How high did I jump?",
         [0.52], jump_height_cm(0.52)),
    Case("My app measured 610 ms of air time on my vertical. What's my jump height in cm?",
         [0.61], jump_height_cm(0.61)),
    Case("Before training my flight time was 0.48 s; after 8 weeks it's 0.55 s. "
         "How many cm did my jump improve?",
         [0.48, 0.55], _gain(0.48, 0.55)),
    Case("I got 0.45 s of flight time. Is that jump above 30 cm? Give me the height.",
         [0.45], jump_height_cm(0.45)),
    Case("What jump height corresponds to a 0.7 second flight time?",
         [0.7], jump_height_cm(0.7)),
]


@dataclass
class Result:
    prompt: str
    expected_cm: float
    tool_args: list[float] = field(default_factory=list)
    tool_ok: bool = False
    extra_calls: int = 0
    correct: bool = False
    seconds: float = 0.0
    answer: str = ""
    error: str | None = None


def _numbers(text: str) -> list[float]:
    return [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", text)]


def run_case(graph, case: Case) -> Result:
    result = Result(prompt=case.prompt, expected_cm=case.expected_cm)
    start = time.perf_counter()
    try:
        state = graph.invoke({"messages": [HumanMessage(case.prompt)]},
                             {"recursion_limit": 10})
    except Exception as exc:  # report, don't crash the comparison
        result.seconds = time.perf_counter() - start
        result.error = f"{type(exc).__name__}: {exc}"
        return result
    result.seconds = time.perf_counter() - start

    messages = state["messages"]
    for msg in messages:
        if isinstance(msg, AIMessage):
            for call in msg.tool_calls:
                if call["name"] == "jump_height":
                    result.tool_args.append(float(call["args"].get("flight_time_s", "nan")))
    tool_errors = [m for m in messages if isinstance(m, ToolMessage) and m.status == "error"]
    # Success = every needed flight time used, no wrong args, no tool errors.
    # Repeating a correct call is counted separately as wasted calls.
    result.tool_ok = (
        {round(a, 3) for a in result.tool_args} == set(case.flight_times_s)
        and not tool_errors
    )
    result.extra_calls = max(0, len(result.tool_args) - len(case.flight_times_s))
    result.answer = messages[-1].text.strip()
    result.correct = any(abs(n - case.expected_cm) <= TOLERANCE_CM
                         for n in _numbers(result.answer))
    return result


def run_model(spec: str) -> dict:
    print(f"\n=== {spec} ===", flush=True)
    llm = get_llm("coach", model_spec=spec)
    t0 = time.perf_counter()
    llm.invoke("Reply with OK.")
    warmup = time.perf_counter() - t0
    print(f"warm-up: {warmup:.1f}s", flush=True)

    graph = build_graph(llm=llm)
    results = []
    for i, case in enumerate(CASES, 1):
        r = run_case(graph, case)
        results.append(r)
        print(f"[{i}] tool={'OK ' if r.tool_ok else 'FAIL'} args={r.tool_args} extra={r.extra_calls} "
              f"correct={'OK ' if r.correct else 'FAIL'} "
              f"(expected {r.expected_cm} cm) {r.seconds:.1f}s", flush=True)
        if r.error:
            print(f"    error: {r.error}", flush=True)
        else:
            print(f"    answer: {r.answer[:300]!r}", flush=True)

    n = len(results)
    return {
        "model": spec,
        "warmup_s": round(warmup, 1),
        "tool_success": sum(r.tool_ok for r in results),
        "extra_calls": sum(r.extra_calls for r in results),
        "correct": sum(r.correct for r in results),
        "n": n,
        "mean_s": round(sum(r.seconds for r in results) / n, 1),
        "max_s": round(max(r.seconds for r in results), 1),
        "cases": [asdict(r) | {"seconds": round(r.seconds, 1)} for r in results],
    }


def main(argv: list[str]) -> None:
    specs = argv or [s.strip() for s in os.getenv("COMPARE_MODELS", "").split(",") if s.strip()]
    if not specs:
        sys.exit("No models given. Pass specs as arguments or set COMPARE_MODELS in .env.")

    summaries = []
    for spec in specs:
        try:
            summaries.append(run_model(spec))
        except Exception as exc:  # e.g. bad key or model not pulled; keep the other models
            print(f"FAILED: {type(exc).__name__}: {exc}", flush=True)
            summaries.append({"model": spec, "error": f"{type(exc).__name__}: {exc}"})

    print("\n| model | tool-call success | redundant calls | correct result "
          "| mean s/prompt | max s | warm-up s |")
    print("|---|---|---|---|---|---|---|")
    for s in summaries:
        if "error" in s:
            print(f"| {s['model']} | failed to run: {s['error'][:80]} | | | | | |")
            continue
        print(f"| {s['model']} | {s['tool_success']}/{s['n']} | {s['extra_calls']} "
              f"| {s['correct']}/{s['n']} "
              f"| {s['mean_s']} | {s['max_s']} | {s['warmup_s']} |")

    RESULTS_PATH.parent.mkdir(exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(summaries, indent=2))
    print(f"\nFull results: {RESULTS_PATH}")


if __name__ == "__main__":
    main(sys.argv[1:])
