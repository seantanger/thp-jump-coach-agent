import socket

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests must never call a model API: any socket connection fails loudly."""

    def guard(*args, **kwargs):
        raise RuntimeError("Network access is disabled in tests")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)


@pytest.fixture(autouse=True)
def no_default_verifiers(monkeypatch):
    """The real Verifier calls a model; tests that exercise it pass or patch in a stub."""
    monkeypatch.setattr("src.coach.qa.answer_verifier", lambda: None, raising=False)
    monkeypatch.setattr("src.planner.run.default_verifier", lambda: None, raising=False)
