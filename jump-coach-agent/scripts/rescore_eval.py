"""Re-mark the saved retrieval results against the current gold, without searching.

Usage:
    uv run python -m scripts.rescore_eval            # rescore results/retrieval_eval.json in place
    uv run python -m scripts.rescore_eval --review   # also rewrite questions_review.md

Each config in results/retrieval_eval.json keeps its saved top-10 per question
(chunk ID, video, start/end). This re-marks those chunks as hit / miss against
$THP_DATA_DIR/eval/questions.yaml and recomputes recall@1/5/10, MRR and video@5.
No search, no embeddings, no Ollama: use it after editing gold. A question whose
gold changes so much that the right chunk was never in the saved top 10 still
needs a fresh run of scripts.eval_retrieval.
"""

from __future__ import annotations

import argparse
import json
import time

from scripts.eval_retrieval import RESULTS_DIR, gold_label, to_markdown
from src.kb.evaluate import aggregate, in_scope, load_questions, review_markdown, score_question
from src.kb.paths import eval_dir, load_chunks


def rescore_config(config: dict, gold: dict[str, list[dict]]) -> dict:
    """Same config with hits, per-question scores and aggregates recomputed."""
    if config["status"] != "ok":
        return config
    per_question = []
    for p in config["per_question"]:
        s = score_question(p["top"], gold[p["id"]])
        per_question.append({
            **p,
            **{k: v for k, v in s.items() if k != "hits"},
            "top": [{**t, "hit": hit} for t, hit in zip(p["top"], s["hits"])],
        })
    return {**config, **{k: round(v, 4) for k, v in aggregate(per_question).items()}, "per_question": per_question}


def rescore(report: dict, questions: list[dict]) -> dict:
    gold = {q["id"]: q["gold"] for q in in_scope(questions)}
    configs = [rescore_config(c, gold) for c in report["configs"]]
    ok = [c for c in configs if c["status"] == "ok"]
    best = max(ok, key=lambda c: (c["recall@5"], c["mrr"])) if ok else None
    return {
        **report,
        "label": f"{gold_label(questions)}; rescored from the saved top-10 of the {report['searched_at']} search",
        "generated_at": time.strftime("%Y-%m-%d %H:%M"),
        "best": {"method": best["method"], "mode": best["mode"]} if best else None,
        "configs": configs,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", action="store_true", help="write questions_review.md")
    args = parser.parse_args()

    questions = load_questions(eval_dir() / "questions.yaml")
    if args.review:
        titles = {c["video_id"]: c["title"] for c in load_chunks("timewindow")}
        (eval_dir() / "questions_review.md").write_text(review_markdown(questions, titles))
        print(f"Wrote {eval_dir() / 'questions_review.md'}")

    path = RESULTS_DIR / "retrieval_eval.json"
    report = json.loads(path.read_text())
    report.setdefault("searched_at", report["generated_at"])  # reports from before rescoring existed
    report = rescore(report, questions)
    path.write_text(json.dumps(report, indent=1) + "\n")
    (RESULTS_DIR / "retrieval_eval.md").write_text(to_markdown(report, questions))
    for c in report["configs"]:
        if c["status"] == "ok":
            print(f"{c['method']}/{c['mode']}: recall@5 {c['recall@5']:.2f}, MRR {c['mrr']:.2f}")
    print(f"{report['label']}\nWrote {RESULTS_DIR / 'retrieval_eval.md'}")


if __name__ == "__main__":
    main()
