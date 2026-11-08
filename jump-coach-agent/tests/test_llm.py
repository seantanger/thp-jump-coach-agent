from unittest.mock import MagicMock, patch

import pytest
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama

from src import llm
from src.llm import ROLES, get_llm, model_spec_for

MODEL_VARS = ["DEFAULT_MODEL", *(f"{r.upper()}_MODEL" for r in ROLES)]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Ignore whatever is in the developer's .env."""
    for var in [*MODEL_VARS, "LLM_TIMEOUT_S", "OLLAMA_TIMEOUT_S", "OLLAMA_REASONING",
                "OLLAMA_BASE_URL", "LLM_TEMPERATURE"]:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def fake_init():
    with patch.object(llm, "init_chat_model", return_value=MagicMock()) as mock:
        yield mock


def test_anthropic_spec(monkeypatch, fake_init):
    monkeypatch.setenv("COACH_MODEL", "anthropic:claude-sonnet-5-5")
    get_llm("coach")
    spec, kwargs = fake_init.call_args.args[0], fake_init.call_args.kwargs
    assert spec == "anthropic:claude-sonnet-5-5"
    assert kwargs["timeout"] == 60
    assert "client_kwargs" not in kwargs


def test_ollama_spec_gets_long_timeout(monkeypatch, fake_init):
    monkeypatch.setenv("COACH_MODEL", "ollama:qwen3:4b")
    get_llm("coach")
    spec, kwargs = fake_init.call_args.args[0], fake_init.call_args.kwargs
    assert spec == "ollama:qwen3:4b"
    assert kwargs["client_kwargs"]["timeout"] >= 300
    assert kwargs["reasoning"] is True  # keeps qwen3 thinking out of content
    assert "timeout" not in kwargs


def test_ollama_timeout_configurable(monkeypatch, fake_init):
    monkeypatch.setenv("COACH_MODEL", "ollama:qwen3:4b")
    monkeypatch.setenv("OLLAMA_TIMEOUT_S", "900")
    get_llm("coach")
    assert fake_init.call_args.kwargs["client_kwargs"]["timeout"] == 900


def test_roles_switch_independently(monkeypatch, fake_init):
    monkeypatch.setenv("COACH_MODEL", "anthropic:claude-sonnet-5-5")
    monkeypatch.setenv("VERIFIER_MODEL", "ollama:qwen3:4b")
    get_llm("coach")
    get_llm("verifier")
    assert [c.args[0] for c in fake_init.call_args_list] == [
        "anthropic:claude-sonnet-5-5",
        "ollama:qwen3:4b",
    ]


def test_default_model_fallback(monkeypatch):
    monkeypatch.setenv("DEFAULT_MODEL", "ollama:qwen3:4b")
    assert model_spec_for("verifier") == "ollama:qwen3:4b"


def test_explicit_spec_overrides_env(monkeypatch, fake_init):
    monkeypatch.setenv("COACH_MODEL", "anthropic:claude-sonnet-5-5")
    get_llm("coach", model_spec="ollama:qwen3:4b")
    assert fake_init.call_args.args[0] == "ollama:qwen3:4b"


def test_missing_config_raises():
    with pytest.raises(RuntimeError, match="COACH_MODEL"):
        get_llm("coach")


def test_unknown_role_raises():
    with pytest.raises(ValueError, match="Unknown role"):
        model_spec_for("janitor")


def test_malformed_spec_raises(monkeypatch):
    monkeypatch.setenv("COACH_MODEL", "qwen3")
    with pytest.raises(ValueError, match="provider"):
        get_llm("coach")


def test_real_classes_built_without_network(monkeypatch):
    """Construct the real provider classes (no request is made on construction)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-real")
    monkeypatch.setenv("COACH_MODEL", "anthropic:claude-sonnet-5-5")
    monkeypatch.setenv("VERIFIER_MODEL", "ollama:qwen3:4b")

    claude = get_llm("coach")
    local = get_llm("verifier")

    assert isinstance(claude, ChatAnthropic)
    assert claude.model == "claude-sonnet-5-5"
    assert isinstance(local, ChatOllama)
    assert local.model == "qwen3:4b"
    assert local.client_kwargs["timeout"] >= 300


def test_temperature_only_sent_when_configured(monkeypatch, fake_init):
    monkeypatch.setenv("COACH_MODEL", "anthropic:claude-sonnet-5-5")
    get_llm("coach")
    assert "temperature" not in fake_init.call_args.kwargs
    monkeypatch.setenv("LLM_TEMPERATURE", "0.3")
    get_llm("coach")
    assert fake_init.call_args.kwargs["temperature"] == 0.3


def test_embeddings_ollama(monkeypatch):
    from langchain_ollama import OllamaEmbeddings

    from src.llm import get_embeddings

    monkeypatch.setenv("EMBEDDING_MODEL", "ollama:nomic-embed-text")
    emb = get_embeddings()
    assert isinstance(emb, OllamaEmbeddings)
    assert emb.model == "nomic-embed-text"
    assert emb.client_kwargs["timeout"] >= 300


def test_embeddings_explicit_spec_and_missing_config(monkeypatch):
    from src.llm import get_embeddings

    monkeypatch.delenv("EMBEDDING_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="EMBEDDING_MODEL"):
        get_embeddings()
    with patch.object(llm, "init_embeddings", return_value=MagicMock()) as fake:
        get_embeddings("ollama:nomic-embed-text")
    assert fake.call_args.args[0] == "ollama:nomic-embed-text"


def test_embedding_prefixes():
    from src.llm import embedding_prefixes

    assert embedding_prefixes("ollama:nomic-embed-text") == ("search_document: ", "search_query: ")
    assert embedding_prefixes("openai:text-embedding-3-small") == ("", "")
