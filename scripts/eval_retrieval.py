"""Score retrieval for every method x mode against the gold time ranges.

Usage:
    uv run python -m scripts.eval_retrieval            # all methods/modes that are ready
    uv run python -m scripts.eval_retrieval --review   # also write questions_review.md
    uv run python -m scripts.eval_retrieval --methods timewindow --modes bm25 hybrid
    uv run python -m scripts.eval_retrieval --prefer-recent 1.0   # also score newest-first re-ranking

Reads   $THP_DATA_DIR/eval/questions.yaml (private)
Writes  results/retrieval_eval.json and results/retrieval_eval.md (scores, chunk
        IDs and timestamps only; no transcript text)
        $THP_DATA_DIR/eval/questions_review.md with --review (private: has quotes)

Dense and hybrid run only for methods whose index is complete; the rest are
listed as skipped. Results are labelled preliminary while any question is
still status: unverified.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from src.kb.evaluate import (
    KS,
    aggregate,
    in_scope,
    load_questions,
    promo_share,
    review_markdown,
    score_question,
)
from src.kb.index import METHODS, index_status
from src.kb.paths import eval_dir, load_chunks
from src.kb.search import MODES, get_retriever

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
TOP_K = max(KS)
OLD_BEFORE = "2024"  # "old" = uploaded before this year (diagnostic for prefer_recent)


def evaluate_config(retriever, method: str, mode: str, questions: list[dict], prefer_recent: float = 0.0) -> dict:
    per_question, results_by_q, oos_top = [], [], []
    for q in questions:
        results = retriever.search(q["question"], k=TOP_K, mode=mode, prefer_recent=prefer_recent)
        if not q["gold"]:
            oos_top.append(results[0]["score"] if results else None)
            continue
        s = score_question(results, q["gold"])
        results_by_q.append(results)
        per_question.append({
            "id": q["id"],
            "topic": q["topic"],
            "difficulty": q["difficulty"],
            **{k: v for k, v in s.items() if k != "hits"},
            "top": [
                {"rank": r["rank"], "chunk_id": r["chunk_id"], "video_id": r["video_id"],
                 "timestamp": r["timestamp"], "start": r["start"], "end": r["end"],
                 "upload_date": r["upload_date"],
                 "score": round(r["score"], 4), "hit": hit, "promo": r["promo_candidate"]}
                for r, hit in zip(results, s["hits"])
            ],
        })
    in_top1 = [p["top"][0]["score"] for p in per_question if p["top"]]
    top5 = [r for results in results_by_q for r in results[:5]]
    return {
        "method": method,
        "mode": f"{mode}+recent{prefer_recent:g}" if prefer_recent else mode,
        "status": "ok",
        **{k: round(v, 4) for k, v in aggregate(per_question).items()},
        "promo_top5_pct": round(100 * promo_share(results_by_q), 1),
        "old_top5_pct": round(100 * sum(r["upload_date"][:4] < OLD_BEFORE for r in top5) / max(1, len(top5)), 1),
        "top1_score_mean": {
            "in_scope": round(sum(in_top1) / len(in_top1), 4) if in_top1 else None,
            "out_of_scope": round(sum(x for x in oos_top if x is not None) / max(1, len(oos_top)), 4),
        },
        "per_question": per_question,
    }


def to_markdown(report: dict, questions: list[dict]) -> str:
    text = {q["id"]: q["question"] for q in questions}
    lines = [
        "# Retrieval eval",
        "",
        f"**{report['label']}** ({report['generated_at']}). {report['n_in_scope']} in-scope questions "
        f"({report['n_out_of_scope']} out-of-scope excluded). A hit = a top-k chunk from a gold video "
        "overlapping a gold time range. recall@k = share of questions with at least one hit in the top k. "
        "video@5 = a gold video is in the top 5 (diagnostic: separates wrong-place-in-right-video from wrong-video misses).",
        "",
        f"| method | mode | recall@1 | recall@5 | recall@10 | MRR | video@5 | promo in top-5 | pre-{OLD_BEFORE} in top-5 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for c in report["configs"]:
        if c["status"] != "ok":
            lines.append(f"| `{c['method']}` | {c['mode']} | _{c['status']}_ | | | | | | |")
            continue
        lines.append(
            f"| `{c['method']}` | {c['mode']} | {c['recall@1']:.2f} | {c['recall@5']:.2f} "
            f"| {c['recall@10']:.2f} | {c['mrr']:.2f} | {c['video@5']:.2f} | {c['promo_top5_pct']:.1f}% "
            f"| {c['old_top5_pct']:.1f}% |"
        )
    best = report.get("best")
    if best:
        c = next(x for x in report["configs"] if x["method"] == best["method"] and x["mode"] == best["mode"])
        missed = [p for p in c["per_question"] if not p["recall@5"]]
        lines += ["", f"## Misses for the best config (`{best['method']}` / {best['mode']}, by recall@5 then MRR)", "",
                  f"{len(missed)} questions with no hit in the top 5.", "",
                  "| question | topic | first hit rank | top-3 chunks |", "|---|---|---:|---|"]
        for p in missed:
            top3 = ", ".join(f"`{t['chunk_id']}` ({t['timestamp']})" for t in p["top"][:3])
            lines.append(f"| {p['id']}: {text[p['id']]} | {p['topic']} | {p['first_hit_rank'] or '-'} | {top3} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--methods", nargs="*", default=list(METHODS))
    parser.add_argument("--modes", nargs="*", default=list(MODES))
    parser.add_argument("--review", action="store_true", help="write questions_review.md")
    parser.add_argument("--prefer-recent", type=float, default=0.0,
                        help="also score each mode with newest-first re-ranking at this weight")
    args = parser.parse_args()

    questions = load_questions(eval_dir() / "questions.yaml")
    scoped = in_scope(questions)
    if args.review:
        titles = {c["video_id"]: c["title"] for c in load_chunks("timewindow")}
        (eval_dir() / "questions_review.md").write_text(review_markdown(questions, titles))
        print(f"Wrote {eval_dir() / 'questions_review.md'}")

    configs = []
    for method in args.methods:
        have, want = index_status(method)
        retriever = get_retriever(method)
        for mode in args.modes:
            if mode != "bm25" and have < want:
                configs.append({"method": method, "mode": mode, "status": f"not indexed yet ({have}/{want})"})
                print(f"{method}/{mode}: skipped, index {have}/{want}")
                continue
            for weight in [0.0] + ([args.prefer_recent] if args.prefer_recent else []):
                t0 = time.perf_counter()
                result = evaluate_config(retriever, method, mode, questions, weight)
                configs.append(result)
                print(f"{method}/{result['mode']}: recall@5 {result['recall@5']:.2f}, MRR {result['mrr']:.2f} "
                      f"({time.perf_counter() - t0:.0f} s)")

    ok = [c for c in configs if c["status"] == "ok"]
    best = max(ok, key=lambda c: (c["recall@5"], c["mrr"])) if ok else None
    unverified = sum(q["status"] == "unverified" for q in questions)
    report = {
        "label": f"preliminary: gold unverified ({unverified}/{len(questions)} questions)" if unverified
        else "gold verified",
        "generated_at": time.strftime("%Y-%m-%d %H:%M"),
        "n_in_scope": len(scoped),
        "n_out_of_scope": len(questions) - len(scoped),
        "best": {"method": best["method"], "mode": best["mode"]} if best else None,
        "configs": configs,
    }
    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "retrieval_eval.json").write_text(json.dumps(report, indent=1) + "\n")
    (RESULTS_DIR / "retrieval_eval.md").write_text(to_markdown(report, questions))
    print(f"Wrote {RESULTS_DIR / 'retrieval_eval.md'}")


if __name__ == "__main__":
    main()
