"""Chunker tests on synthetic segments only (no real transcript text)."""

import random
import re

import pytest

from src.kb.chunk import (
    CHARSPLIT_CONFIG,
    TIMEWINDOW_CONFIG,
    charsplit_chunks,
    format_timestamp,
    join_segments,
    load_promo_patterns,
    mid_segment,
    skip_reasons,
    speech_segments,
    timewindow_chunks,
    url_at,
)

PATTERNS = load_promo_patterns()
MAX_S = TIMEWINDOW_CONFIG["max_s"]
OVERLAP_S = TIMEWINDOW_CONFIG["overlap_s"]


def seg(start, end, text):
    return {"start": start, "end": end, "text": text, "clean_text": text, "changes": []}


def video(segments, video_id="ab-c_D12345", **overrides):
    return {
        "video_id": video_id,
        "channel_handle": "SynthChannel",
        "channel_name": "Synth Channel",
        "title": "Synthetic video",
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "upload_date": "20260101",
        "duration_seconds": 0,
        "is_short": False,
        "has_speech": True,
        "coaching_content": True,
        "description": "",
        "segments": segments,
        **overrides,
    }


def synthetic_segments(n=200, seed=0, empty_every=17):
    """Rolling-caption-like timing (end = start of the segment after next), with
    random pauses, a few empty segments, and words labelled s<k>w<i>."""
    rng = random.Random(seed)
    starts, t = [], 0.0
    for _ in range(n):
        starts.append(round(t, 2))
        t += rng.uniform(2.0, 4.0) + (rng.uniform(1.0, 6.0) if rng.random() < 0.1 else 0.0)
    segs = []
    for k, start in enumerate(starts):
        end = starts[k + 2] if k + 2 < n else start + 3.0
        text = "" if k % empty_every == empty_every - 1 else " ".join(
            f"s{k}w{i}" for i in range(rng.randint(3, 9))
        )
        segs.append(seg(start, end, text))
    return segs


METHODS = {
    "timewindow": lambda v: timewindow_chunks(v, patterns=PATTERNS),
    "charsplit": lambda v: charsplit_chunks(v, CHARSPLIT_CONFIG, patterns=PATTERNS),
}


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_every_nonempty_segment_is_in_a_chunk(method, seed):
    v = video(synthetic_segments(seed=seed))
    segs = speech_segments(v)
    text, offsets = join_segments(segs)
    chunks = METHODS[method](v)
    covered = set()
    for c in chunks:
        a, b = c["_span"]
        assert text[a:b] == c["text"]
        covered.update(range(a, b))
    for a, b in offsets:
        assert set(range(a, b)) <= covered
    assert all(s["clean_text"].strip() for s in segs)  # empties were dropped


def test_empty_segments_are_dropped():
    segs = [seg(0, 3, "s0w0 s0w1"), seg(3, 6, "   "), seg(6, 9, "s2w0")]
    [chunk] = timewindow_chunks(video(segs), patterns=PATTERNS)
    assert chunk["n_segments"] == 2
    assert chunk["text"] == "s0w0 s0w1 s2w0"


@pytest.mark.parametrize("seed", range(5))
def test_timewindow_never_over_max_unless_single_segment(seed):
    segs = synthetic_segments(n=400, seed=seed)
    segs.insert(150, seg(segs[149]["end"] + 1, segs[149]["end"] + 120, "s999w0 s999w1"))
    for s in segs[151:]:
        s["start"] += 125
        s["end"] += 125
    chunks = timewindow_chunks(video(segs), patterns=PATTERNS)
    for c in chunks:
        assert c["end"] - c["start"] <= MAX_S or c["n_segments"] == 1
    assert any(c["n_segments"] == 1 and c["end"] - c["start"] > MAX_S for c in chunks)


def test_timewindow_chunks_on_segment_boundaries():
    v = video(synthetic_segments(seed=3))
    _, offsets = join_segments(speech_segments(v))
    for c in timewindow_chunks(v, patterns=PATTERNS):
        assert mid_segment(c["_span"], offsets) == (False, False)


def test_timewindow_cuts_at_largest_pause():
    # 3 s segments every 3 s, except one 5 s silence before the segment at ~51 s.
    segs, t = [], 0.0
    for k in range(40):
        if k == 17:
            t += 5.0
        segs.append(seg(t, t + 3.0, f"s{k}w0 s{k}w1 s{k}w2"))
        t += 3.0
    first = timewindow_chunks(video(segs), patterns=PATTERNS)[0]
    assert first["end"] == segs[16]["end"]


def test_timewindow_overlap():
    segs = synthetic_segments(n=300, seed=4)
    start_of = {f"s{k}": s["start"] for k, s in enumerate(segs)}
    chunks = timewindow_chunks(video(segs), patterns=PATTERNS)
    assert len(chunks) > 3

    def labels(c):
        return {w.split("w")[0] for w in c["text"].split()}

    for prev, nxt in zip(chunks, chunks[1:]):
        shared = labels(prev) & labels(nxt)
        assert shared  # the next chunk repeats the tail of prev...
        assert nxt["text"].startswith(" ".join(w for w in prev["text"].split()
                                               if w.split("w")[0] in shared))
        # ...the segments starting in the last ~10 s, or else just the last segment
        assert len(shared) == 1 or min(start_of[s] for s in shared) >= prev["end"] - OVERLAP_S


def test_no_overlap_across_long_gap():
    segs = [seg(t, t + 3.0, f"s{t}w0") for t in range(0, 45, 3)]
    segs += [seg(t, t + 3.0, f"s{t}w0") for t in range(300, 345, 3)]
    chunks = timewindow_chunks(video(segs), patterns=PATTERNS)
    assert [c["start"] for c in chunks] == [0, 300]


@pytest.mark.parametrize("method", METHODS)
def test_ids_unique_and_stable(method):
    v = video(synthetic_segments(n=300, seed=5))
    ids = [c["chunk_id"] for c in METHODS[method](v)]
    assert len(ids) == len(set(ids))
    assert ids == [c["chunk_id"] for c in METHODS[method](v)]
    pattern = r"ab-c_D12345@\d+" + (r"#\d+" if method == "charsplit" else "")
    assert all(re.fullmatch(pattern, i) for i in ids)


def test_charsplit_ids_disambiguate_same_segment():
    long_text = " ".join(f"s0w{i}" for i in range(200))
    chunks = charsplit_chunks(video([seg(12.7, 80.0, long_text)]), patterns=PATTERNS)
    assert len(chunks) > 1
    assert [c["chunk_id"] for c in chunks] == [f"ab-c_D12345@12#{n}" for n in range(len(chunks))]


def test_timestamp_and_url():
    assert format_timestamp(0) == "00:00"
    assert format_timestamp(65.9) == "01:05"
    assert format_timestamp(3599) == "59:59"
    assert format_timestamp(3725.4) == "1:02:05"
    assert url_at("ab-c_D12345", 125.8) == "https://www.youtube.com/watch?v=ab-c_D12345&t=125s"
    segs = [seg(t, t + 3.0, f"s{t}w0 s{t}w1") for t in range(3700, 3800, 3)]
    for c in timewindow_chunks(video(segs), patterns=PATTERNS):
        assert c["url_t"] == f"https://www.youtube.com/watch?v=ab-c_D12345&t={int(c['start'])}s"
        assert c["timestamp"] == format_timestamp(c["start"])
        assert re.fullmatch(r"1:\d\d:\d\d", c["timestamp"])


@pytest.mark.parametrize("seed", [0, 6])
def test_charsplit_start_end_map_to_segments(seed):
    segs = speech_segments(video(synthetic_segments(seed=seed)))
    by_index = {int(re.match(r"s(\d+)w", s["clean_text"])[1]): s for s in segs}
    for c in charsplit_chunks(video(synthetic_segments(seed=seed)), patterns=PATTERNS):
        words = c["text"].split()
        first = by_index[int(re.match(r"s(\d+)w", words[0])[1])]
        last = by_index[int(re.match(r"s(\d+)w", words[-1])[1])]
        assert c["start"] == first["start"]
        assert c["end"] == last["end"]


def test_charsplit_mid_segment_detected():
    long_text = " ".join(f"s0w{i}" for i in range(200))
    v = video([seg(0, 60, long_text), seg(60, 63, "s1w0")])
    _, offsets = join_segments(speech_segments(v))
    flags = [mid_segment(c["_span"], offsets) for c in charsplit_chunks(v, patterns=PATTERNS)]
    assert flags[0] == (False, True)
    assert any(start_mid for start_mid, _ in flags[1:])


@pytest.mark.parametrize("method", METHODS)
def test_promo_flag_fires(method):
    segs = [seg(0, 3, "s0w0 s0w1 s0w2"), seg(3, 6, "go to tb strength.com and use code s1w0")]
    [c] = METHODS[method](video(segs))
    assert c["promo_candidate"] is True
    assert {"thp_site", "use_code"} <= set(c["promo_hits"])


def test_promo_flag_quiet_on_plain_text():
    [c] = timewindow_chunks(video([seg(0, 3, "s0w0 s0w1 s0w2")]), patterns=PATTERNS)
    assert c["promo_candidate"] is False
    assert c["promo_hits"] == []


def test_same_record_fields_for_every_method():
    v = video(synthetic_segments(seed=7))
    keys = {name: set(fn(v)[0]) for name, fn in METHODS.items()}
    assert keys["timewindow"] == keys["charsplit"]
    assert set(timewindow_chunks(v, patterns=PATTERNS)[0]["tags"]) == {
        "topics", "periodization_phase", "promo"
    }


@pytest.mark.parametrize(
    "overrides, reason",
    [
        ({"is_short": True}, "is_short"),
        ({"has_speech": False}, "no speech"),
        ({"coaching_content": False}, "not coaching content"),
        ({"segments": [seg(0, 3, " ")]}, "no non-empty segments"),
    ],
)
def test_skip_reasons(overrides, reason):
    overrides = {"segments": synthetic_segments(n=5), **overrides}
    assert reason in skip_reasons(video(**overrides))


def test_long_coaching_video_included():
    assert skip_reasons(video(synthetic_segments(n=5))) == []
