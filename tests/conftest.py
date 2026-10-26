import socket

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Tests must never call a model API: any socket connection fails loudly."""

    def guard(*args, **kwargs):
        raise RuntimeError("Network access is disabled in tests")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)
