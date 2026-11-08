# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""Public-client tests use synthetic homes, credentials and loopback only."""

import socket
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def isolated_client_test(monkeypatch, tmp_path_factory):
    home = tmp_path_factory.mktemp("client-home")
    for name in (
        "HOME",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
    ):
        monkeypatch.setenv(name, str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    for name in ("MEMSTRATA_CL1_TOKEN", "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"):
        monkeypatch.setenv(name, "false")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.setenv("CREWAI_TELEMETRY_DISABLED", "true")
    try:
        import appdirs
    except ImportError:
        pass
    else:
        # Windows appdirs uses SHGetFolderPath instead of HOME/APPDATA.
        # Framework import-time storage must stay in this synthetic directory.
        monkeypatch.setattr(
            appdirs, "user_data_dir", lambda *args, **kwargs: str(home / "framework-data")
        )
    try:
        import keyring
    except ImportError:
        pass
    else:
        values = {}
        fake = SimpleNamespace(
            get_password=lambda service, name: values.get((service, name)),
            set_password=lambda service, name, value: values.__setitem__((service, name), value),
            delete_password=lambda service, name: values.pop((service, name), None),
        )
        monkeypatch.setattr(keyring, "get_keyring", lambda: fake)
        for method in ("get_password", "set_password", "delete_password"):
            monkeypatch.setattr(keyring, method, getattr(fake, method))
    original_connect, original_resolve = socket.socket.connect, socket.getaddrinfo

    def connect(sock, address):
        if not isinstance(address, tuple) or address[0] not in {"127.0.0.1", "::1", "localhost"}:
            raise RuntimeError("Client test refused external network access")
        return original_connect(sock, address)

    def resolve(host, *args, **kwargs):
        if host not in {"127.0.0.1", "::1", "localhost", b"127.0.0.1", b"::1", b"localhost"}:
            raise RuntimeError("Client test refused external DNS")
        return original_resolve(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "getaddrinfo", resolve)
