"""Persistent Chroma index per chunking method, in $THP_DATA_DIR/index/<method>/.

Each chunk is embedded as "<doc prefix>title: <title>\\n<text>" with
get_embeddings(). Metadata is every chunk field except text/tags, flattened
(promo_hits -> comma-joined string), plus text_sha1 so a chunk whose text
changed under the same ID is re-embedded.

build_index() is resumable: IDs already in the collection with the same text
hash are skipped, and IDs no longer in the chunk file are deleted.
"""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable
from pathlib import Path

import chromadb
from chromadb.config import Settings
from langchain_core.embeddings import Embeddings

from src.kb.paths import index_dir, load_chunks
from src.llm import embedding_prefixes, get_embeddings

METHODS = ("timewindow", "charsplit_matched", "charsplit_350")  # build order

INDEX_CONFIG = {
    "min_words": 15,  # chunks with fewer words are not indexed (dense or BM25)
    "batch_size": 32,
    "max_retries": 3,
}

EXCLUDED_FIELDS = ("text", "tags")


def document_text(chunk: dict) -> str:
    """What gets embedded (after the model's doc prefix) and BM25-tokenised."""
    return f"title: {chunk['title']}\n{chunk['text']}"


def text_sha1(chunk: dict) -> str:
    return hashlib.sha1(document_text(chunk).encode()).hexdigest()


def filter_chunks(chunks: list[dict], min_words: int = INDEX_CONFIG["min_words"]) -> tuple[list[dict], list[dict]]:
    """(kept, skipped): chunks under min_words are skipped."""
    kept = [c for c in chunks if c["word_count"] >= min_words]
    skipped = [c for c in chunks if c["word_count"] < min_words]
    return kept, skipped


def chunk_metadata(chunk: dict) -> dict:
    meta = {}
    for key, value in chunk.items():
        if key in EXCLUDED_FIELDS or key.startswith("_"):
            continue
        meta[key] = ",".join(value) if isinstance(value, list) else value
    meta["text_sha1"] = text_sha1(chunk)
    return meta


def open_collection(method: str, path: Path | None = None, embedding_spec: str = "") -> chromadb.Collection:
    """The method's collection (created if missing). Refuses to mix embedding models."""
    path = path or index_dir() / method
    client = chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))
    if method in {c.name for c in client.list_collections()}:
        collection = client.get_collection(method, embedding_function=None)
    else:
        collection = client.create_collection(
            method,
            embedding_function=None,
            configuration={"hnsw": {"space": "cosine"}},
            metadata={"embedding_model": embedding_spec or "unknown"},
        )
    built_with = (collection.metadata or {}).get("embedding_model", "")
    if embedding_spec and built_with and built_with != embedding_spec:
        raise RuntimeError(
            f"{path} was built with {built_with!r}, not {embedding_spec!r}; use a fresh index dir."
        )
    return collection


def plan(collection: chromadb.Collection, chunks: list[dict]) -> tuple[list[dict], list[str]]:
    """(chunks to embed, stale IDs to delete) given what the collection holds."""
    existing = collection.get(include=["metadatas"])
    have = {i: (m or {}).get("text_sha1") for i, m in zip(existing["ids"], existing["metadatas"])}
    wanted = {c["chunk_id"] for c in chunks}
    todo = [c for c in chunks if have.get(c["chunk_id"]) != text_sha1(c)]
    stale = [i for i in have if i not in wanted]
    return todo, stale


def _embed_with_retry(embeddings: Embeddings, texts: list[str], retries: int, log) -> list[list[float]]:
    for attempt in range(1, retries + 1):
        try:
            return embeddings.embed_documents(texts)
        except Exception as exc:  # Ollama timeouts / restarts: retry, then give up (resumable)
            if attempt == retries:
                raise
            log(f"  embed failed ({type(exc).__name__}: {exc}); retry {attempt}/{retries - 1}")
            time.sleep(5 * attempt)


def build_index(
    method: str,
    chunks: list[dict] | None = None,
    embeddings: Embeddings | None = None,
    embedding_spec: str | None = None,
    path: Path | None = None,
    config: dict = INDEX_CONFIG,
    log: Callable[[str], None] = print,
) -> dict:
    """Embed the method's (filtered) chunks into its collection. Returns counts."""
    spec = embedding_spec or os.getenv("EMBEDDING_MODEL", "")
    if embeddings is None:
        embeddings = get_embeddings(spec or None)
    doc_prefix, _ = embedding_prefixes(spec)
    chunks = load_chunks(method) if chunks is None else chunks
    kept, skipped = filter_chunks(chunks, config["min_words"])
    collection = open_collection(method, path, spec)
    todo, stale = plan(collection, kept)
    if stale:
        collection.delete(ids=stale)
    log(f"[{method}] {len(kept)} chunks to index ({len(skipped)} under {config['min_words']} words skipped), "
        f"{len(kept) - len(todo)} already embedded, {len(todo)} to embed, {len(stale)} stale removed")

    t0, done, bs = time.perf_counter(), 0, config["batch_size"]
    for k in range(0, len(todo), bs):
        batch = todo[k : k + bs]
        vectors = _embed_with_retry(
            embeddings, [doc_prefix + document_text(c) for c in batch], config["max_retries"], log
        )
        collection.upsert(
            ids=[c["chunk_id"] for c in batch],
            embeddings=vectors,
            metadatas=[chunk_metadata(c) for c in batch],
        )
        done += len(batch)
        if (k // bs) % 10 == 0 or done == len(todo):
            elapsed = time.perf_counter() - t0
            rate = done / elapsed if elapsed else 0.0
            eta = (len(todo) - done) / rate if rate else 0.0
            log(f"[{method}] {done}/{len(todo)} embedded, {rate:.2f} chunks/s, "
                f"ETA {eta / 60:.0f} min ({time.strftime('%H:%M:%S')})")
    return {"method": method, "kept": len(kept), "skipped": len(skipped), "embedded": done,
            "stale_removed": len(stale), "total_in_collection": collection.count()}


def index_status(method: str, path: Path | None = None) -> tuple[int, int]:
    """(vectors in the collection, chunks that should be there)."""
    kept, _ = filter_chunks(load_chunks(method))
    path = path or index_dir() / method
    if not path.exists():
        return 0, len(kept)
    return open_collection(method, path).count(), len(kept)
