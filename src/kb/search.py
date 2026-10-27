"""Search one chunking method's index: dense (Chroma), BM25, or hybrid (RRF).

    search("knee hurts when I land", k=5, method="timewindow", mode="hybrid")

Returns chunk records (the JSONL fields) plus "score", "rank" and, for
hybrid, "dense_rank" / "bm25_rank". Dense and BM25 cover the same chunks:
the method's chunk file after the index's word-count filter. promo_candidate
chunks are included unless exclude_promo=True.

prefer_recent=w (> 0) re-ranks the top-50 by fusing the relevance ranking with
a newest-first ranking of the same candidates (weight w on the date ranking);
"base_rank" is the chunk's rank before that.
"""

from __future__ import annotations

import re
from functools import lru_cache

from langchain_core.embeddings import Embeddings
from rank_bm25 import BM25Okapi

from src.kb.index import INDEX_CONFIG, document_text, filter_chunks, open_collection
from src.kb.paths import load_chunks
from src.llm import embedding_prefixes, get_embeddings

MODES = ("dense", "bm25", "hybrid")
RRF_K = 60
FUSION_DEPTH = 50  # hybrid fuses the dense and BM25 top-50

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def rrf(rankings: list[list[str]], k: int = RRF_K, weights: list[float] | None = None) -> list[tuple[str, float]]:
    """Reciprocal rank fusion: score(id) = sum over rankings of w / (k + rank),
    rank starting at 1, w = 1 unless weights are given. Ties break on best
    single rank, then id (deterministic)."""
    scores: dict[str, float] = {}
    best: dict[str, int] = {}
    for ranking, w in zip(rankings, weights or [1.0] * len(rankings)):
        for rank, item in enumerate(ranking, 1):
            scores[item] = scores.get(item, 0.0) + w / (k + rank)
            best[item] = min(best.get(item, rank), rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], best[kv[0]], kv[0]))


class Retriever:
    """Dense + BM25 search over one method's chunks."""

    def __init__(
        self,
        method: str,
        chunks: list[dict] | None = None,
        collection=None,
        embeddings: Embeddings | None = None,
        embedding_spec: str | None = None,
        min_words: int = INDEX_CONFIG["min_words"],
    ):
        self.method = method
        chunks = load_chunks(method) if chunks is None else chunks
        self.chunks, _ = filter_chunks(chunks, min_words)
        self.by_id = {c["chunk_id"]: c for c in self.chunks}
        self._collection = collection
        self._embeddings = embeddings
        self._embedding_spec = embedding_spec
        self._bm25: BM25Okapi | None = None

    # -- dense ------------------------------------------------------------
    @property
    def collection(self):
        if self._collection is None:
            self._collection = open_collection(self.method)
        return self._collection

    @property
    def embeddings(self) -> Embeddings:
        if self._embeddings is None:
            self._embeddings = get_embeddings(self._embedding_spec)
        return self._embeddings

    def dense(self, query: str, n: int, exclude_promo: bool = False) -> list[tuple[str, float]]:
        """(chunk_id, cosine similarity), best first."""
        _, query_prefix = embedding_prefixes(self._embedding_spec)
        vector = self.embeddings.embed_query(query_prefix + query)
        result = self.collection.query(
            query_embeddings=[vector],
            n_results=n,
            where={"promo_candidate": False} if exclude_promo else None,
            include=["distances"],
        )
        return [
            (cid, 1.0 - dist)
            for cid, dist in zip(result["ids"][0], result["distances"][0])
            if cid in self.by_id
        ]

    # -- bm25 -------------------------------------------------------------
    @property
    def bm25(self) -> BM25Okapi:
        if self._bm25 is None:
            self._bm25 = BM25Okapi([tokenize(document_text(c)) for c in self.chunks])
        return self._bm25

    def keyword(self, query: str, n: int, exclude_promo: bool = False) -> list[tuple[str, float]]:
        """(chunk_id, BM25 score), best first; chunks sharing no query term are dropped."""
        scores = self.bm25.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
        out = []
        for i in order:
            if scores[i] <= 0 or len(out) == n:
                break
            chunk = self.chunks[i]
            if exclude_promo and chunk["promo_candidate"]:
                continue
            out.append((chunk["chunk_id"], float(scores[i])))
        return out

    # -- public -----------------------------------------------------------
    def search(self, query: str, k: int = 5, mode: str = "dense", exclude_promo: bool = False,
               prefer_recent: float = 0.0) -> list[dict]:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, not {mode!r}")
        if prefer_recent > 0:
            base = self.search(query, max(k, FUSION_DEPTH), mode, exclude_promo)
            ids = [r["chunk_id"] for r in base]
            newest = sorted(ids, key=lambda cid: (self.by_id[cid]["upload_date"], cid), reverse=True)
            base_rank = {cid: r for r, cid in enumerate(ids, 1)}
            return [
                {**self.by_id[cid], "score": score, "rank": rank, "base_rank": base_rank[cid]}
                for rank, (cid, score) in enumerate(rrf([ids, newest], weights=[1.0, prefer_recent])[:k], 1)
            ]
        if mode == "dense":
            hits = self.dense(query, k, exclude_promo)
            extra = [{} for _ in hits]
        elif mode == "bm25":
            hits = self.keyword(query, k, exclude_promo)
            extra = [{} for _ in hits]
        else:
            dense = [cid for cid, _ in self.dense(query, FUSION_DEPTH, exclude_promo)]
            sparse = [cid for cid, _ in self.keyword(query, FUSION_DEPTH, exclude_promo)]
            hits = rrf([dense, sparse])[:k]
            dense_rank = {cid: r for r, cid in enumerate(dense, 1)}
            bm25_rank = {cid: r for r, cid in enumerate(sparse, 1)}
            extra = [{"dense_rank": dense_rank.get(cid), "bm25_rank": bm25_rank.get(cid)} for cid, _ in hits]
        return [
            {**self.by_id[cid], "score": score, "rank": rank, **more}
            for rank, ((cid, score), more) in enumerate(zip(hits, extra), 1)
        ]


@lru_cache(maxsize=None)
def get_retriever(method: str) -> Retriever:
    return Retriever(method)


def search(
    query: str,
    k: int = 5,
    method: str = "timewindow",
    mode: str = "dense",
    exclude_promo: bool = False,
    prefer_recent: float = 0.0,
) -> list[dict]:
    return get_retriever(method).search(query, k=k, mode=mode, exclude_promo=exclude_promo,
                                        prefer_recent=prefer_recent)
