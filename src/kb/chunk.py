"""Chunk cleaned transcripts for retrieval. One function per method.

    timewindow_chunks(video)   main method: ~60 s windows on caption-segment
                               boundaries, cut at the largest pause, ~10 s overlap
    charsplit_chunks(video)    course baseline: RecursiveCharacterTextSplitter
                               over the video's joined text

Both return records with the same fields (see _record) so retrieval can be
compared fairly. Each record also carries a private "_span" (char offsets of the
chunk in the video's joined text, see join_segments); writers drop "_" keys.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import re
import statistics
from pathlib import Path

import yaml
from langchain_text_splitters import RecursiveCharacterTextSplitter

ROOT = Path(__file__).resolve().parent.parent.parent
PROMO_PATTERNS_PATH = ROOT / "config" / "promo_patterns.yaml"

CHUNKER_VERSION = "1"

TIMEWINDOW_CONFIG = {
    "target_s": 60.0,  # preferred chunk span
    "min_s": 30.0,  # cuts are only considered once a chunk spans this long
    "max_s": 90.0,  # never exceeded unless a single segment is longer
    "overlap_s": 10.0,  # repeat segments starting in the last ~10 s of a chunk
    "pause_tie_s": 0.25,  # pauses this close to the largest count as ties -> nearest target wins
}

# Course settings (mod-5-seed). The size-matched variant is computed by
# scripts/build_chunks.py and keeps the same overlap ratio.
CHARSPLIT_CONFIG = {"chunk_size": 350, "chunk_overlap": 50}


# --- eligibility / segments -------------------------------------------------


def skip_reasons(video: dict) -> list[str]:
    """Why a video is excluded; empty list means it is included."""
    reasons = []
    if video.get("is_short") is not False:
        reasons.append("is_short")
    if not video.get("has_speech"):
        reasons.append("no speech")
    if not video.get("coaching_content"):
        reasons.append("not coaching content")
    if not reasons and not speech_segments(video):
        reasons.append("no non-empty segments")
    return reasons


def speech_segments(video: dict) -> list[dict]:
    """Segments with non-empty clean_text, in time order, text stripped."""
    segs = []
    for seg in video.get("segments", []):
        text = (seg.get("clean_text") or "").strip()
        if text:
            segs.append({**seg, "clean_text": text})
    return sorted(segs, key=lambda s: s["start"])


def join_segments(segs: list[dict]) -> tuple[str, list[tuple[int, int]]]:
    """Join clean_text with single spaces. Returns (text, [(char_start, char_end)])
    per segment, end exclusive. Shared by both methods so spans are comparable."""
    offsets, pos = [], 0
    for seg in segs:
        offsets.append((pos, pos + len(seg["clean_text"])))
        pos += len(seg["clean_text"]) + 1
    return " ".join(s["clean_text"] for s in segs), offsets


def estimate_pauses(segs: list[dict]) -> list[float]:
    """pauses[k] = estimated silence (s) before segs[k]; pauses[0] = 0.

    YouTube auto-captions are "rolling": a segment's end is usually the start of
    the segment after next, so start[k] - end[k-1] is almost always negative.
    Instead estimate how long segs[k-1] took to say (its words x the video's
    median seconds per word) and treat the rest of the onset gap as pause. A
    real gap (start[k] > end[k-1]) wins if larger.
    """
    words = [len(s["clean_text"].split()) for s in segs]
    rates = [
        (segs[k + 1]["start"] - segs[k]["start"]) / words[k]
        for k in range(len(segs) - 1)
        if words[k]
    ]
    spw = statistics.median(rates) if rates else 0.0
    pauses = [0.0]
    for k in range(1, len(segs)):
        onset_excess = segs[k]["start"] - segs[k - 1]["start"] - words[k - 1] * spw
        real_gap = segs[k]["start"] - segs[k - 1]["end"]
        pauses.append(max(onset_excess, real_gap))
    return pauses


# --- promo flag ---------------------------------------------------------------


def load_promo_patterns(path: Path = PROMO_PATTERNS_PATH) -> list[tuple[str, re.Pattern]]:
    data = yaml.safe_load(Path(path).read_text())
    return [(p["id"], re.compile(p["regex"], re.IGNORECASE)) for p in data["patterns"]]


def promo_hits(text: str, patterns: list[tuple[str, re.Pattern]]) -> list[str]:
    """Ids of the promo patterns found in text (flag only; nothing is dropped)."""
    return [pid for pid, rx in patterns if rx.search(text)]


# --- record helpers -------------------------------------------------------------


def format_timestamp(seconds: float) -> str:
    """mm:ss under an hour, else h:mm:ss."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def url_at(video_id: str, start: float) -> str:
    return f"https://www.youtube.com/watch?v={video_id}&t={int(start)}s"


def config_version(method: str, config: dict) -> str:
    """e.g. "timewindow-1-3f2a9c1b": bumps whenever code version or settings change."""
    digest = hashlib.sha1(json.dumps(config, sort_keys=True).encode()).hexdigest()[:8]
    return f"{method}-{CHUNKER_VERSION}-{digest}"


def _record(
    video: dict,
    method: str,
    chunk_id: str,
    segs: list[dict],
    text: str,
    start: float,
    end: float,
    span: tuple[int, int],
    patterns: list[tuple[str, re.Pattern]],
    version: str,
) -> dict:
    hits = promo_hits(text, patterns)
    return {
        "chunk_id": chunk_id,
        "method": method,
        "video_id": video["video_id"],
        "channel_handle": video["channel_handle"],
        "channel_name": video["channel_name"],
        "title": video["title"],
        "upload_date": video["upload_date"],
        "start": start,
        "end": end,
        "url_t": url_at(video["video_id"], start),
        "timestamp": format_timestamp(start),
        "text": text,
        "word_count": len(text.split()),
        "n_segments": len(segs),
        "n_uncertain": sum(
            1 for seg in segs for ch in seg.get("changes", []) if ch.get("uncertain")
        ),
        "promo_candidate": bool(hits),
        "promo_hits": hits,
        "tags": {"topics": [], "periodization_phase": None, "promo": None},
        "chunker_version": version,
        "_span": span,
    }


# --- method 1: timewindow --------------------------------------------------------


def _window_end(segs: list[dict], pauses: list[float], i: int, cfg: dict) -> int:
    """Index of the last segment of the chunk starting at segs[i]."""
    n, t0 = len(segs), segs[i]["start"]
    if segs[-1]["end"] - t0 <= cfg["max_s"]:
        return n - 1  # the rest of the video fits in one chunk

    candidates, j = [], i
    while j < n and segs[j]["end"] - t0 <= cfg["max_s"]:
        if segs[j]["end"] - t0 >= cfg["min_s"]:
            candidates.append(j)
        j += 1
    last_fit = j - 1
    if last_fit < i:
        return i  # a single segment longer than max_s
    if not candidates:
        return last_fit  # a long gap ahead forces an early cut

    # Avoid leaving a tail shorter than min_s, when possible.
    candidates = [
        c for c in candidates if segs[-1]["end"] - segs[c + 1]["start"] >= cfg["min_s"]
    ] or candidates
    best = max(pauses[c + 1] for c in candidates)
    ties = [c for c in candidates if pauses[c + 1] >= best - cfg["pause_tie_s"]]
    return min(ties, key=lambda c: (abs(segs[c]["end"] - t0 - cfg["target_s"]), c))


def _next_start(segs: list[dict], i: int, j: int, cfg: dict) -> int:
    """First segment of the next chunk: the segments starting in the last
    overlap_s of chunk i..j are repeated, or at least the last segment (with
    rolling captions its end absorbs the pause after it, so nothing may start
    in the last overlap_s). No overlap after a chunk shorter than min_s (it was
    cut short by a gap or is a single long segment)."""
    if j == i or segs[j]["end"] - segs[i]["start"] < cfg["min_s"]:
        return j + 1
    cutoff = segs[j]["end"] - cfg["overlap_s"]
    for k in range(i + 1, j + 1):
        if segs[k]["start"] >= cutoff:
            return k
    return j


def timewindow_spans(segs: list[dict], config: dict = TIMEWINDOW_CONFIG) -> list[tuple[int, int]]:
    """(first, last) segment indices, inclusive, for each chunk."""
    pauses = estimate_pauses(segs)
    windows: list[tuple[int, int]] = []
    i, prev_j = 0, -1
    while i < len(segs):
        j = _window_end(segs, pauses, i, config)
        if j <= prev_j:  # the overlap can't reach any new segment (gap ahead)
            i = prev_j + 1
            continue
        windows.append((i, j))
        if j == len(segs) - 1:
            break
        prev_j, i = j, _next_start(segs, i, j, config)
    return windows


def timewindow_chunks(
    video: dict,
    config: dict = TIMEWINDOW_CONFIG,
    patterns: list[tuple[str, re.Pattern]] | None = None,
) -> list[dict]:
    patterns = load_promo_patterns() if patterns is None else patterns
    segs = speech_segments(video)
    _, offsets = join_segments(segs)
    version = config_version("timewindow", config)
    chunks = []
    for i, j in timewindow_spans(segs, config):
        part = segs[i : j + 1]
        start = segs[i]["start"]
        chunks.append(
            _record(
                video,
                "timewindow",
                f"{video['video_id']}@{int(start)}",
                part,
                " ".join(s["clean_text"] for s in part),
                start,
                segs[j]["end"],
                (offsets[i][0], offsets[j][1]),
                patterns,
                version,
            )
        )
    return chunks


# --- method 2: charsplit (course baseline) ---------------------------------------


def charsplit_chunks(
    video: dict,
    config: dict = CHARSPLIT_CONFIG,
    method: str = "charsplit_350",
    patterns: list[tuple[str, re.Pattern]] | None = None,
) -> list[dict]:
    """Join the clean_text segments with spaces, split with
    RecursiveCharacterTextSplitter, and map each chunk's first/last char back to
    the segment holding it for start/end."""
    patterns = load_promo_patterns() if patterns is None else patterns
    segs = speech_segments(video)
    text, offsets = join_segments(segs)
    seg_starts = [a for a, _ in offsets]
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config["chunk_size"],
        chunk_overlap=config["chunk_overlap"],
        add_start_index=True,
    )
    version = config_version(method, config)
    chunks, per_second = [], {}
    for doc in splitter.create_documents([text]):
        a = doc.metadata["start_index"]
        b = a + len(doc.page_content)
        if text[a:b] != doc.page_content:
            raise AssertionError(f"start_index mismatch in {video['video_id']} at {a}")
        first = bisect.bisect_right(seg_starts, a) - 1
        last = bisect.bisect_right(seg_starts, b - 1) - 1
        start = segs[first]["start"]
        n = per_second.get(int(start), 0)
        per_second[int(start)] = n + 1
        chunks.append(
            _record(
                video,
                method,
                f"{video['video_id']}@{int(start)}#{n}",
                segs[first : last + 1],
                doc.page_content,
                start,
                segs[last]["end"],
                (a, b),
                patterns,
                version,
            )
        )
    return chunks


# --- shared diagnostics ----------------------------------------------------------


def mid_segment(span: tuple[int, int], offsets: list[tuple[int, int]]) -> tuple[bool, bool]:
    """(starts mid-segment, ends mid-segment) for a chunk's char span."""
    seg_starts = {a for a, _ in offsets}
    seg_ends = {b for _, b in offsets}
    return span[0] not in seg_starts, span[1] not in seg_ends
