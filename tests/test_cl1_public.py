# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from memstrata_client import MemStrata, __version__, cl1_credentials, mcp_cli, tool_schema
from memstrata_client.cl1 import CL1Client, CL1Error
from tests.cl1_fixture import receipt


def test_existing_top_level_api_and_version_remain_available():
    assert MemStrata is not None and __version__ == "0.2.0"


def test_context_is_scoped_and_credential_is_not_in_body_or_repr():
    seen = []

    def handler(request):
        seen.append(
            (request.url.path, request.headers["authorization"], json.loads(request.content))
        )
        return httpx.Response(200, json=receipt())

    with httpx.Client(transport=httpx.MockTransport(handler)) as wire:
        client = CL1Client(
            "http://127.0.0.1:8000",
            project_id="project",
            token="cl1_synthetic",
            source_scope="all_ready",
            client=wire,
        )
        packet = client.context("When?")
        assert packet.documents[0].session_index == 2 and packet.documents[0].turn_index == 3
        assert "cl1_synthetic" not in repr(client)
        result = tool_schema.create_context_function(client)("When?")
        assert (
            result["answer_correctness"] == "NOT_MEASURED"
            and result["host_delivery_verified"] is False
        )
    assert len(seen) == 2
    assert all(row[0] == "/context/cl1/v1" and row[1] == "Bearer cl1_synthetic" for row in seen)
    assert all(row[2]["source_scope"] == "all_ready" and "source_ids" not in row[2] for row in seen)


@pytest.mark.parametrize(
    "key,value",
    [
        ("fallback_used", True),
        ("source_validation_passed", False),
        ("source_scope", "selected"),
        ("evidence_token_count", 9000),
        ("completion_status", "partial"),
    ],
)
def test_refuses_incomplete_or_mismatched_receipts(key, value):
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={**receipt(), key: value})
        )
    ) as wire:
        client = CL1Client(
            "http://127.0.0.1:8000",
            project_id="project",
            token="cl1_synthetic",
            source_scope="all_ready",
            client=wire,
        )
        with pytest.raises(CL1Error):
            client.context("When?")


def test_key_reference_never_falls_back_or_logs_secrets(monkeypatch, capsys):
    monkeypatch.setenv("MEMSTRATA_CL1_TOKEN", "cl1_environment")
    monkeypatch.setattr(
        cl1_credentials, "_os_keyring", lambda: SimpleNamespace(get_password=lambda *args: None)
    )
    with pytest.raises(ValueError) as error:
        cl1_credentials.app_key("keychain:missing")
    assert "cl1_environment" not in str(error.value)
    assert cl1_credentials.app_key() == "cl1_environment"
    assert not capsys.readouterr().out


@pytest.mark.parametrize(
    "args,scope",
    [([], "all_ready"), (["--all-sources"], "all_ready"), (["--source-id", "note"], "selected")],
)
def test_launcher_has_scope_defaults_and_reference_only_credentials(args, scope, monkeypatch):
    pytest.importorskip("mcp")
    import memstrata_client.mcp as server

    calls = []
    monkeypatch.setattr(mcp_cli, "app_key", lambda ref: "cl1_synthetic")

    def create(client):
        assert client.source_scope == scope
        return SimpleNamespace(run=lambda **kwargs: calls.append(kwargs))

    monkeypatch.setattr(server, "create_server", create)
    assert mcp_cli.main(["--project", "project", "--key-ref", "keychain:tool"] + args) == 0
    assert calls == [{"transport": "stdio"}]
    with pytest.raises(SystemExit):
        mcp_cli.parser().parse_args(["--project", "p", "--token", "cl1_bad"])


def test_generic_schema_cannot_override_project_or_credentials():
    schema = tool_schema.function_schema()
    assert set(schema["parameters"]["properties"]) == {"question"}
    assert schema["parameters"]["additionalProperties"] is False


def test_accidentally_pasted_cli_secret_is_not_echoed(capsys):
    with pytest.raises(SystemExit):
        mcp_cli.parser().parse_args(["--project", "p", "--token", "cl1_canary_secret"])
    assert "cl1_canary_secret" not in capsys.readouterr().err


def test_real_langchain_sync_and_async_preserve_locators_without_scores():
    pytest.importorskip("langchain_core")
    from memstrata_client.langchain import CL1Retriever
    from tests.cl1_fixture import mock_client

    calls = []
    client, sync, asynchronous = mock_client(calls)

    async def run():
        try:
            retriever = CL1Retriever(client=client)
            for documents in (retriever.invoke("When?"), await retriever.ainvoke("When?")):
                assert documents[0].id == "note@1:s2:t3:0-22"
                assert documents[0].metadata["session_index"] == 2
                assert documents[0].metadata["answer_correctness"] == "NOT_MEASURED"
                assert "score" not in documents[0].metadata
            assert "cl1_synthetic" not in repr(retriever)
        finally:
            sync.close()
            await asynchronous.aclose()

    asyncio.run(run())
    assert len(calls) == 2
