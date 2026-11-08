# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.

import httpx
import pytest

from memstrata_client import ConfigurationError, MemStrataClient, local
from memstrata_client.cl1 import CL1Client
from memstrata_client.mnemo import build_envelope


def test_runtime_down_gives_start_command_without_reading_vault(monkeypatch):
    def down(self, url):
        raise httpx.ConnectError("unavailable")

    monkeypatch.setattr(httpx.Client, "get", down)
    monkeypatch.setattr(local, "app_key", lambda _ref: pytest.fail("Unexpected vault read"))
    with pytest.raises(ConfigurationError, match="memstrata-conversational assistant"):
        MemStrataClient()


def test_default_client_uses_only_the_enrolled_local_reference(monkeypatch):
    seen = []

    def health(self, url):
        seen.append(url)
        return httpx.Response(200, request=httpx.Request("GET", url),
                              json={"status": "alive", "product_version": "0.8.1"})

    def token(ref):
        seen.append(ref)
        return "cl1_synthetic"

    monkeypatch.setattr(httpx.Client, "get", health)
    monkeypatch.setattr(local, "app_key", token)
    client = MemStrataClient()
    assert client.project_id == "personal" and client.source_scope == "all_ready"
    assert seen == ["http://127.0.0.1:9101/health", "keychain:default-local-sdk"]


def test_management_methods_remain_outside_the_public_cut():
    assert not any(hasattr(CL1Client, name) for name in (
        "put_task", "create_managed_copy", "export_sources", "import_sources",
        "start_backfill_job", "job_status",
    ))


def test_embedded_mnemo_envelope_uses_the_public_schema():
    built = build_envelope({
        "schema": "mnemo/v0",
        "project_id": "synthetic",
        "producer": "test/1",
        "items": [{"kind": "episode", "text": "Synthetic Cedar review."}],
    })
    assert built["schema"] == "mnemo/v0"
    assert built["items"][0]["text"] == "Synthetic Cedar review."


def test_local_mnemo_transport_builds_no_https_handler(monkeypatch):
    from urllib.request import OpenerDirector, Request

    from memstrata_client.mnemo import envelope

    seen = []

    def open_without_tls(self, request, timeout):
        seen.extend(type(handler).__name__ for handler in self.handlers)
        assert request.full_url == "http://127.0.0.1:9101/ingest/v0"
        assert timeout == 1
        return object()

    monkeypatch.setattr(OpenerDirector, "open", open_without_tls)
    envelope._open_request(Request("http://127.0.0.1:9101/ingest/v0"), timeout=1)
    assert "HTTPHandler" in seen and "HTTPSHandler" not in seen
    assert "ProxyHandler" not in seen and "_NoRedirect" in seen
