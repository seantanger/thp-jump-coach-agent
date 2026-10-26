"""Chunk the cleaned transcripts with every method and write a report.

Usage:
    uv run python -m scripts.build_chunks

Reads   $THP_DATA_DIR/clean/<channel_handle>/<video_id>.json  (read only)
Writes  $THP_DATA_DIR/chunks/{timewindow,charsplit_350,charsplit_matched}.jsonl
        $THP_DATA_DIR/chunks/report.md

The transcripts are private: output stays under $THP_DATA_DIR/chunks, never in
this repo. Same input + settings give the same files and chunk IDs.
"""

from __future__ import annotations

import json
import random
import statistics
from collections import Counter
from pathlib import Path

from src.kb.chunk import (
    CHARSPLIT_CONFIG,
    TIMEWINDOW_CONFIG,
    charsplit_chunks,
    join_segments,
    load_promo_patterns,
    mid_segment,
    skip_reasons,
    speech_segments,
    timewindow_chunks,
)
from src.kb.paths import chunks_dir, data_dir

METHODS = ("timewindow", "charsplit_350", "charsplit_matched")
SAMPLE_SEED = 42
SAMPLE_SIZE = 15
MATCH_TOLERANCE = 0.02  # stop the size search within 2% of timewindow's median length
TIMING_MARKER = "<!-- embedding timing: written by scripts/time_embeddings.py -->"


def load_videos(clean_dir: Path) -> list[tuple[str, dict]]:
    """(relative path, video) for every transcript, in sorted path order."""
    return [
        (str(path.relative_to(clean_dir)), json.loads(path.read_text()))
        for path in sorted(clean_dir.glob("*/*.json"))
    ]


def write_jsonl(path: Path, records: list[dict]) -> None:
    ids = [r["chunk_id"] for r in records]
    if len(ids) != len(set(ids)):
        dupes = [i for i, n in Counter(ids).items() if n > 1][:5]
        raise AssertionError(f"duplicate chunk_ids in {path.name}: {dupes}")
    with path.open("w") as f:
        for r in records:
            f.write(json.dumps({k: v for k, v in r.items() if not k.startswith("_")}) + "\n")


def percentiles(values: list[float]) -> dict[str, float]:
    """min / p10 / median / p90 / max with linear interpolation."""
    xs = sorted(values)

    def q(p: float) -> float:
        pos = p * (len(xs) - 1)
        lo = int(pos)
        hi = min(lo + 1, len(xs) - 1)
        return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)

    return {"min": xs[0], "p10": q(0.1), "median": q(0.5), "p90": q(0.9), "max": xs[-1]}


def matched_charsplit_config(videos: list[dict], target_chars: float, patterns) -> dict:
    """chunk_size whose median chunk length is within MATCH_TOLERANCE of
    target_chars, keeping the course's overlap ratio (50/350)."""
    ratio = CHARSPLIT_CONFIG["chunk_overlap"] / CHARSPLIT_CONFIG["chunk_size"]
    size = round(target_chars)
    for _ in range(8):
        cfg = {"chunk_size": size, "chunk_overlap": round(size * ratio)}
        lengths = [
            len(c["text"])
            for v in videos
            for c in charsplit_chunks(v, cfg, "charsplit_matched", patterns)
        ]
        median = statistics.median(lengths)
        print(f"  chunk_size={size}: median {median:.0f} chars (target {target_chars:.0f})")
        if abs(median - target_chars) / target_chars <= MATCH_TOLERANCE:
            break
        size = round(size * target_chars / median)
    return cfg


def _fmt(stats: dict[str, float], digits: int = 0) -> str:
    return " / ".join(f"{v:.{digits}f}" for v in stats.values())


def build_report(
    outputs: dict[str, list[dict]],
    offsets_by_video: dict[str, list[tuple[int, int]]],
    configs: dict[str, dict],
    included: int,
    skipped: list[tuple[str, dict, list[str]]],
) -> str:
    lines = [
        "# Chunk report",
        "",
        f"Included videos: **{included}** (long, has_speech, coaching_content). "
        f"Skipped: **{len(skipped)}** (listed below). Every method chunks the same "
        "included videos and writes the same record fields.",
        "",
        "## Settings",
        "",
    ]
    for method in METHODS:
        lines.append(f"- `{method}`: `{json.dumps(configs[method])}` "
                     f"(chunker_version `{outputs[method][0]['chunker_version']}`)")
    lines += [
        "",
        "## Per method",
        "",
        "Distributions are min / p10 / median / p90 / max. Duration = end - start (s).",
        "",
        "| method | chunks | words | chars | duration s | start mid-segment | end mid-segment |",
        "|---|---:|---|---|---|---:|---:|",
    ]
    for method in METHODS:
        recs = outputs[method]
        mids = [mid_segment(r["_span"], offsets_by_video[r["video_id"]]) for r in recs]
        lines.append(
            f"| `{method}` | {len(recs)} "
            f"| {_fmt(percentiles([r['word_count'] for r in recs]))} "
            f"| {_fmt(percentiles([len(r['text']) for r in recs]))} "
            f"| {_fmt(percentiles([r['end'] - r['start'] for r in recs]), 1)} "
            f"| {sum(a for a, _ in mids)} | {sum(b for _, b in mids)} |"
        )

    channels = sorted({r["channel_handle"] for r in outputs["timewindow"]})
    lines += ["", "### Chunks per channel", "", "| method | " + " | ".join(channels) + " |",
              "|---|" + "---:|" * len(channels)]
    for method in METHODS:
        counts = Counter(r["channel_handle"] for r in outputs[method])
        lines.append(f"| `{method}` | " + " | ".join(str(counts[c]) for c in channels) + " |")

    tw = outputs["timewindow"]
    promo = [r for r in tw if r["promo_candidate"]]
    hit_counts = Counter(h for r in promo for h in r["promo_hits"])
    lines += [
        "",
        "## timewindow details",
        "",
        f"### promo_candidate: {len(promo)} of {len(tw)} chunks "
        f"({100 * len(promo) / len(tw):.1f}%)",
        "",
        "Hits per pattern (a chunk can hit several): "
        + ", ".join(f"`{k}` {v}" for k, v in hit_counts.most_common()),
        "",
        f"### Skipped videos ({len(skipped)})",
        "",
        "| file | title | reason |",
        "|---|---|---|",
    ]
    for rel, video, reasons in skipped:
        title = video.get("title", "").replace("|", "\\|")
        lines.append(f"| `{rel}` | {title} | {', '.join(reasons)} |")

    rng = random.Random(SAMPLE_SEED)
    lines += ["", f"### {SAMPLE_SIZE} random chunks (seed {SAMPLE_SEED}) for spot-checking", ""]
    for n, r in enumerate(rng.sample(tw, SAMPLE_SIZE), 1):
        lines += [
            f"**{n}. {r['channel_name']} / \"{r['title']}\" / {r['timestamp']}** "
            f"(`{r['chunk_id']}`, {r['end'] - r['start']:.0f} s, {r['word_count']} words, "
            f"{r['n_segments']} segments{', promo: ' + ', '.join(r['promo_hits']) if r['promo_hits'] else ''})",
            "",
            f"<{r['url_t']}>",
            "",
            f"> {r['text']}",
            "",
        ]
    lines += [TIMING_MARKER, "", "_Run `uv run python -m scripts.time_embeddings` to fill this in._", ""]
    return "\n".join(lines)


def main() -> None:
    root = data_dir()
    clean_dir, out_dir = root / "clean", chunks_dir()
    out_dir.mkdir(exist_ok=True)
    patterns = load_promo_patterns()

    included, skipped = [], []
    for rel, video in load_videos(clean_dir):
        reasons = skip_reasons(video)
        (skipped.append((rel, video, reasons)) if reasons else included.append(video))
    print(f"{len(included)} videos included, {len(skipped)} skipped")

    outputs = {"timewindow": [c for v in included for c in timewindow_chunks(v, patterns=patterns)]}
    target = statistics.median(len(c["text"]) for c in outputs["timewindow"])
    print(f"timewindow: {len(outputs['timewindow'])} chunks, median {target:.0f} chars")

    print("Searching charsplit_matched settings:")
    matched = matched_charsplit_config(included, target, patterns)
    configs = {"timewindow": TIMEWINDOW_CONFIG, "charsplit_350": CHARSPLIT_CONFIG,
               "charsplit_matched": matched}
    for method in ("charsplit_350", "charsplit_matched"):
        outputs[method] = [
            c for v in included for c in charsplit_chunks(v, configs[method], method, patterns)
        ]
        print(f"{method}: {len(outputs[method])} chunks")

    for method in METHODS:
        write_jsonl(out_dir / f"{method}.jsonl", outputs[method])

    offsets = {v["video_id"]: join_segments(speech_segments(v))[1] for v in included}
    report = build_report(outputs, offsets, configs, len(included), skipped)
    (out_dir / "report.md").write_text(report)
    print(f"Wrote {', '.join(f'{m}.jsonl' for m in METHODS)} and report.md to {out_dir}")


if __name__ == "__main__":
    main()
