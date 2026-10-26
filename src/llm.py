"""Chat model + embeddings factory. The ONLY module that knows about specific providers.

Each agent role reads its model from an env var named <ROLE>_MODEL, written as
"<provider>:<model>", e.g.

    COACH_MODEL=anthropic:claude-sonnet-5-5
    COACH_MODEL=ollama:qwen3:4b

Embeddings read EMBEDDING_MODEL the same way, e.g. ollama:nomic-embed-text.

Everything else in the repo calls get_llm(role) / get_embeddings() and stays
provider-agnostic.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.embeddings import init_embeddings
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

load_dotenv()

ROLES = ("coach", "planner", "verifier", "safety", "router")

DEFAULT_TIMEOUT_S = 60.0
# Ollama runs CPU-only on the dev machine; a single turn can take minutes.
DEFAULT_OLLAMA_TIMEOUT_S = 600.0


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value else default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def model_spec_for(role: str) -> str:
    """Return the "<provider>:<model>" string configured for a role."""
    role = role.lower()
    if role not in ROLES:
        raise ValueError(f"Unknown role {role!r}; expected one of {ROLES}")
    spec = os.getenv(f"{role.upper()}_MODEL") or os.getenv("DEFAULT_MODEL")
    if not spec:
        raise RuntimeError(
            f"No model configured for role {role!r}. "
            f"Set {role.upper()}_MODEL (or DEFAULT_MODEL) in .env."
        )
    return spec


def provider_of(spec: str) -> str:
    provider, sep, model = spec.partition(":")
    if not sep or not model:
        raise ValueError(f"Model spec {spec!r} must look like '<provider>:<model>'")
    return provider.lower()


def get_llm(role: str = "coach", model_spec: str | None = None) -> BaseChatModel:
    """Build the chat model for an agent role.

    model_spec overrides the role's env var (used by scripts/compare_models.py
    to run the same role on several models).
    """
    spec = model_spec or model_spec_for(role)
    provider = provider_of(spec)
    kwargs: dict = {}
    # Only sent when set: Sonnet 5.5 / Fable 5 reject non-default temperatures.
    if os.getenv("LLM_TEMPERATURE"):
        kwargs["temperature"] = _env_float("LLM_TEMPERATURE", 1.0)

    if provider == "ollama":
        timeout = _env_float("OLLAMA_TIMEOUT_S", DEFAULT_OLLAMA_TIMEOUT_S)
        kwargs["client_kwargs"] = {"timeout": timeout}
        kwargs["base_url"] = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        # The qwen3:4b build is thinking-only: think=false is ignored and the
        # reasoning leaks into content. reasoning=True moves it out of content
        # (into additional_kwargs["reasoning_content"]). Set false for models
        # without thinking support.
        kwargs["reasoning"] = _env_bool("OLLAMA_REASONING", True)
    else:
        kwargs["timeout"] = _env_float("LLM_TIMEOUT_S", DEFAULT_TIMEOUT_S)
        kwargs["max_retries"] = 2

    return init_chat_model(spec, **kwargs)


def get_embeddings(model_spec: str | None = None) -> Embeddings:
    """Build the embedding model from EMBEDDING_MODEL (or an explicit spec)."""
    spec = model_spec or os.getenv("EMBEDDING_MODEL")
    if not spec:
        raise RuntimeError("No embedding model configured. Set EMBEDDING_MODEL in .env.")
    provider = provider_of(spec)
    kwargs: dict = {}
    if provider == "ollama":
        timeout = _env_float("OLLAMA_TIMEOUT_S", DEFAULT_OLLAMA_TIMEOUT_S)
        kwargs["client_kwargs"] = {"timeout": timeout}
        kwargs["base_url"] = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    return init_embeddings(spec, **kwargs)
