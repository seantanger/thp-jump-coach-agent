"""Locations of the private data, all under $THP_DATA_DIR (never inside this repo)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def data_dir() -> Path:
    load_dotenv()
    raw = os.getenv("THP_DATA_DIR")
    if not raw:
        sys.exit("Set THP_DATA_DIR (e.g. ~/git/thp-ai/data) in .env or the environment.")
    return Path(raw).expanduser().resolve()


def chunks_dir() -> Path:
    return data_dir() / "chunks"


def index_dir() -> Path:
    return data_dir() / "index"


def eval_dir() -> Path:
    return data_dir() / "eval"


def read_jsonl(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f]


def load_chunks(method: str) -> list[dict]:
    return read_jsonl(chunks_dir() / f"{method}.jsonl")


def traces_dir() -> Path:
    return data_dir() / "traces"
