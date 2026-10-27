"""Index / search / eval tests on synthetic chunks only (no transcripts, no network)."""

import hashlib
import math
import re

import pytest
from langchain_core.embeddings import Embeddings

from src.kb.evaluate import aggregate, in_scope, is_hit, promo_share, score_question
from src.kb.index import build_index, chunk_metadata, filter_chunks, open_collection, plan
from src.kb.search import Retriever, rrf

SPEC = "fake:bag-of-words"


class FakeEmbeddings(Embeddings):
    """Deterministic hashed bag-of-words vectors; counts how many texts it embeds."""

    dim = 64

    def __init__(self):
        self.embedded = 0

    def _vec(self, text):
        v = [0.0] * self.dim
        for tok in re.findall(r"[a-z0-9]+", text.lower()):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts):
        self.embedded += len(texts)
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


def chunk(cid, text, video="vidA", start=0.0, end=60.0, promo=False):
    return {
        "chunk_id": cid, "method": "timewindow", "video_id": video,
        "channel_handle": "SynthChannel", "channel_name": "Synth Channel", "title": "Synthetic",
        "upload_date": "20260101", "start": start, "end": end,
        "url_t": f"https://www.youtube.com/watch?v={video}&t={int(start)}s", "timestamp": "00:00",
        "text": text, "word_count": len(text.split()), "n_segments": 3, "n_uncertain": 0,
        "promo_candidate": promo, "promo_hits": ["thp_site"] if promo else [],
        "tags": {"topics": [], "periodization_phase": None, "promo": None},
        "chunker_version": "timewindow-1-test",
    }


FILLER = " ".join(f"w{i}" for i in range(20))
CHUNKS = [
    chunk("vidA@0", f"alpha bravo charlie {FILLER}", "vidA", 0, 60),
    chunk("vidA@50", f"delta echo foxtrot {FILLER}", "vidA", 50, 110),
    chunk("vidB@0", f"alpha bravo signup site {FILLER}", "vidB", 0, 60, promo=True),
    chunk("vidB@50", f"golf hotel india {FILLER}", "vidB", 50, 110),
    chunk("vidC@0", "too short", "vidC", 0, 30),
    # padding so query terms are rare enough for BM25 (Okapi idf is 0 for a term in half the docs)
    *[chunk(f"vidD@{i}", f"kilo lima mike {FILLER}", "vidD", i, i + 60) for i in range(0, 300, 60)],
]


# --- eval: hit / overlap -------------------------------------------------------


def test_hit_requires_gold_video_and_overlap():
    gold = [{"video_id": "vidA", "start": 100, "end": 160}]
    assert is_hit({"video_id": "vidA", "start": 90, "end": 120}, gold)  # partial overlap
    assert is_hit({"video_id": "vidA", "start": 110, "end": 150}, gold)  # inside
    assert is_hit({"video_id": "vidA", "start": 0, "end": 300}, gold)  # contains
    assert not is_hit({"video_id": "vidA", "start": 40, "end": 100}, gold)  # touches start
    assert not is_hit({"video_id": "vidA", "start": 160, "end": 200}, gold)  # touches end
    assert not is_hit({"video_id": "vidB", "start": 110, "end": 150}, gold)  # other video


def test_score_question_ranks():
    gold = [{"video_id": "vidA", "start": 100, "end": 160}]
    results = [{"video_id": "vidB", "start": 0, "end": 60}, {"video_id": "vidA", "start": 0, "end": 60},
               {"video_id": "vidA", "start": 120, "end": 180}]
    s = score_question(results, gold)
    assert (s["recall@1"], s["recall@5"], s["recall@10"]) == (0.0, 1.0, 1.0)
    assert s["first_hit_rank"] == 3 and s["rr"] == pytest.approx(1 / 3)
    assert s["video@5"] == 1.0  # vidA at rank 2 counts for the looser diagnostic
    miss = score_question([{"video_id": "vidB", "start": 0, "end": 60}], gold)
    assert miss["rr"] == 0.0 and miss["first_hit_rank"] is None and miss["video@5"] == 0.0
    agg = aggregate([s, miss])
    assert agg["recall@5"] == 0.5 and agg["mrr"] == pytest.approx(1 / 6)


def test_out_of_scope_excluded_and_promo_share():
    qs = [{"id": "a", "gold": [{"video_id": "v", "start": 0, "end": 1}]}, {"id": "b", "gold": []}]
    assert [q["id"] for q in in_scope(qs)] == ["a"]
    results = [[{"promo_candidate": True}, {"promo_candidate": False}], [{"promo_candidate": False}]]
    assert promo_share(results, k=5) == pytest.approx(1 / 3)


# --- fusion ------------------------------------------------------------------------


def test_rrf_fusion():
    fused = rrf([["a", "b", "c"], ["b", "d"]], k=60)
    scores = dict(fused)
    assert fused[0][0] == "b"  # in both lists
    assert scores["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert scores["a"] == pytest.approx(1 / 61)
    assert scores["d"] == pytest.approx(1 / 62)
    # a (rank 1 once) and d (rank 2 once): higher score first; equal scores break on best rank, then id
    assert [i for i, _ in fused] == ["b", "a", "d", "c"]
    assert [i for i, _ in rrf([["x"], ["y"]])] == ["x", "y"]


# --- word-count filter + metadata ---------------------------------------------------


def test_word_count_filter_configurable():
    kept, skipped = filter_chunks(CHUNKS)
    assert [c["chunk_id"] for c in skipped] == ["vidC@0"]
    kept, skipped = filter_chunks(CHUNKS, min_words=24)
    assert {c["chunk_id"] for c in kept} == {"vidB@0"}  # the only chunk with 24+ words


def test_metadata_flattened_without_text():
    meta = chunk_metadata(CHUNKS[2])
    assert "text" not in meta and "tags" not in meta
    assert meta["promo_candidate"] is True and meta["promo_hits"] == "thp_site"
    assert all(isinstance(v, (str, int, float, bool)) for v in meta.values())


# --- resumable build -----------------------------------------------------------------


def test_build_index_resumes_and_prunes(tmp_path):
    emb = FakeEmbeddings()
    first = build_index("timewindow", CHUNKS, emb, SPEC, tmp_path, log=lambda s: None)
    assert first["embedded"] == 9 and first["skipped"] == 1 and emb.embedded == 9

    again = build_index("timewindow", CHUNKS, emb, SPEC, tmp_path, log=lambda s: None)
    assert again["embedded"] == 0 and emb.embedded == 9  # nothing re-embedded

    changed = [dict(CHUNKS[0], text=CHUNKS[0]["text"] + " zulu"), *CHUNKS[2:4]]
    third = build_index("timewindow", changed, emb, SPEC, tmp_path, log=lambda s: None)
    assert third["embedded"] == 1  # only the chunk whose text changed
    assert third["stale_removed"] == 6  # vidA@50 and the vidD chunks are no longer in the chunk file
    assert sorted(open_collection("timewindow", tmp_path).get()["ids"]) == ["vidA@0", "vidB@0", "vidB@50"]


def test_plan_reads_the_collection_in_pages(tmp_path):
    build_index("timewindow", CHUNKS, FakeEmbeddings(), SPEC, tmp_path, log=lambda s: None)
    collection = open_collection("timewindow", tmp_path)
    kept, _ = filter_chunks(CHUNKS)
    changed = [dict(kept[0], text=kept[0]["text"] + " zulu"), *kept[1:-1]]
    todo, stale = plan(collection, changed, page_size=2)  # 9 items over 5 pages
    assert [c["chunk_id"] for c in todo] == [kept[0]["chunk_id"]]
    assert stale == [kept[-1]["chunk_id"]]


def test_refuses_to_mix_embedding_models(tmp_path):
    build_index("timewindow", CHUNKS, FakeEmbeddings(), SPEC, tmp_path, log=lambda s: None)
    with pytest.raises(RuntimeError, match="built with"):
        open_collection("timewindow", tmp_path, "ollama:other-model")


# --- search + exclude_promo ------------------------------------------------------------


@pytest.fixture
def retriever(tmp_path):
    emb = FakeEmbeddings()
    build_index("timewindow", CHUNKS, emb, SPEC, tmp_path, log=lambda s: None)
    return Retriever("timewindow", chunks=CHUNKS, collection=open_collection("timewindow", tmp_path),
                     embeddings=emb, embedding_spec=SPEC)


@pytest.mark.parametrize("mode", ["dense", "bm25", "hybrid"])
def test_search_modes_and_exclude_promo(retriever, mode):
    results = retriever.search("alpha bravo", k=3, mode=mode)
    assert {"vidA@0", "vidB@0"} <= {r["chunk_id"] for r in results[:2]}
    assert [r["rank"] for r in results] == list(range(1, len(results) + 1))
    assert all("text" in r and "score" in r for r in results)
    assert "vidC@0" not in {r["chunk_id"] for r in results}  # filtered by word count

    clean = retriever.search("alpha bravo", k=3, mode=mode, exclude_promo=True)
    assert clean and not any(r["promo_candidate"] for r in clean)


def test_prefer_recent_lifts_newer_candidates():
    chunks = [dict(c, upload_date="20261001") if c["chunk_id"] == "vidB@0" else c for c in CHUNKS]
    r = Retriever("timewindow", chunks=chunks)  # bm25 only: no collection needed
    assert [x["chunk_id"] for x in r.search("alpha bravo", k=2, mode="bm25")] == ["vidA@0", "vidB@0"]
    recent = r.search("alpha bravo", k=2, mode="bm25", prefer_recent=2.0)
    assert [x["chunk_id"] for x in recent] == ["vidB@0", "vidA@0"]
    assert recent[0]["base_rank"] == 2 and [x["rank"] for x in recent] == [1, 2]


def test_bm25_drops_chunks_without_query_terms(retriever):
    assert [r["chunk_id"] for r in retriever.search("golf", k=5, mode="bm25")] == ["vidB@50"]


def test_unknown_mode_rejected(retriever):
    with pytest.raises(ValueError, match="mode"):
        retriever.search("x", mode="sparse")
