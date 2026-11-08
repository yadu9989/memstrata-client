# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
import hashlib
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("mcp")
from mcp.types import LATEST_PROTOCOL_VERSION
from starlette.testclient import TestClient

from memstrata_client.cl1 import CL1Document, CL1Error
from memstrata_client.mcp import PacketResources, create_server


class Client:
    def __init__(self, text):
        self.text = text
        self.revoked = False
        self.revision = 1

    def context(self, question, date=None):
        return SimpleNamespace(
            assembled_context=self.text,
            packet_sha256=hashlib.sha256(self.text.encode()).hexdigest(),
            source_bindings=({"source_id": "note", "revision": 1, "source_sha256": "a" * 64},),
            documents=(
                CL1Document(
                    quote=self.text[:5],
                    source_id="note",
                    revision=1,
                    date="today",
                    role="source",
                    speaker="note",
                    start_byte=0,
                    end_byte=len(self.text[:5].encode()),
                    packet_start_byte=0,
                    packet_end_byte=len(self.text[:5].encode()),
                    source_sha256="a" * 64,
                    session_index=2,
                    turn_index=1,
                ),
            ),
            evidence_token_count=len(self.text),
            tokenizer_id="fixture-char-count/v1",
            effective_profile="deep_24k",
        )

    def fetch_source(self, source_id, revision=None):
        if self.revoked or revision != self.revision:
            raise CL1Error("Source denied or changed", 403)
        return dict(
            source_id=source_id, source_sha256="a" * 64, revision=self.revision, text=self.text
        )

    def source_status(self, source_id):
        if self.revoked:
            raise CL1Error("Grant revoked", 403)
        return dict(source_id=source_id, ready=True)


def decode(response):
    assert response.status_code == 200, response.text
    if "application/json" in response.headers["content-type"]:
        return response.json()
    return json.loads(
        next(line[6:] for line in response.text.splitlines() if line.startswith("data: "))
    )


def call(client, id, method, params):
    return decode(
        client.post(
            "/mcp",
            json=dict(jsonrpc="2.0", id=id, method=method, params=params),
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
        )
    )


@pytest.mark.parametrize(
    "requested,expected",
    [
        ("2024-11-05", "2024-11-05"),
        ("2025-06-18", "2025-06-18"),
        (LATEST_PROTOCOL_VERSION, LATEST_PROTOCOL_VERSION),
        ("2999-01-01", LATEST_PROTOCOL_VERSION),
    ],
)
def test_native_protocol_negotiation_and_tool_names(requested, expected):
    server = create_server(Client("Small source"))
    with TestClient(server.streamable_http_app(), base_url="http://127.0.0.1:8000") as client:
        initialized = call(
            client,
            1,
            "initialize",
            dict(
                protocolVersion=requested,
                capabilities={},
                clientInfo={"name": "fixture", "version": "1"},
            ),
        )
        assert initialized["result"]["protocolVersion"] == expected
        tools = call(client, 2, "tools/list", {})["result"]["tools"]
        assert {tool["name"] for tool in tools} == {
            "cl1_get_context",
            "cl1_fetch_source",
            "cl1_source_status",
        }
        assert all(tool["annotations"]["readOnlyHint"] for tool in tools)
        assert "get_context" not in {tool["name"] for tool in tools}


def test_initialize_reports_product_version():
    from memstrata_client import __version__

    server = create_server(Client("Small source"))
    with TestClient(server.streamable_http_app(), base_url="http://127.0.0.1:8000") as client:
        initialized = call(
            client,
            1,
            "initialize",
            dict(
                protocolVersion="2025-11-25",
                capabilities={},
                clientInfo={"name": "fixture", "version": "1"},
            ),
        )
        info = initialized["result"]["serverInfo"]
        assert info["name"] == "MemStrata CL1 read v1"
        assert info["version"] == __version__
        assert info["version"] != "unknown"


def test_large_packet_resource_exact_bytes_and_revocation():
    source = Client("Unicode 雨 résumé. " * 2000)
    server = create_server(source)
    with TestClient(server.streamable_http_app(), base_url="http://127.0.0.1:8000") as client:
        call(
            client,
            1,
            "initialize",
            dict(
                protocolVersion="2025-11-25",
                capabilities={},
                clientInfo={"name": "fixture", "version": "1"},
            ),
        )
        result = call(
            client,
            2,
            "tools/call",
            dict(name="cl1_get_context", arguments={"question": "Find note"}),
        )["result"]
        assert not result.get("isError"), result
        data = result.get("structuredContent") or json.loads(result["content"][0]["text"])
        assert data["delivery_mode"] == "resource" and data["host_delivery_verified"] is False
        assert "assembled_context" not in data and "documents" not in data
        assert len(json.dumps(data, ensure_ascii=False)) < 8000
        received = call(client, 3, "resources/read", dict(uri=data["packet_resource"]))["result"][
            "contents"
        ][0]["text"]
        assert received.encode() == source.text.encode()
        assert hashlib.sha256(received.encode()).hexdigest() == data["packet_sha256"]
        metadata_raw = call(
            client, 4, "resources/read", dict(uri=data["packet_metadata_resource"])
        )["result"]["contents"][0]["text"]
        assert hashlib.sha256(metadata_raw.encode()).hexdigest() == data["packet_metadata_sha256"]
        metadata = json.loads(metadata_raw)
        assert (
            metadata["documents"][0]["session_index"] == 2
            and metadata["documents"][0]["turn_index"] == 1
        )
        assert metadata["offset_basis"] == "turn_utf8"
        assert metadata["packet_sha256"] == data["packet_sha256"]
        source.revoked = True
        denied = call(client, 5, "resources/read", dict(uri=data["packet_resource"]))
        assert "error" in denied and source.text not in json.dumps(denied)


def test_packet_cache_expiry_stale_revision_and_opaque_handle(monkeypatch):
    source = Client("A source")
    cache = PacketResources(source, ttl_seconds=1, capacity=1)
    handle = cache.retain(source.context("x")).split("/")[-1]
    with pytest.raises(CL1Error):
        cache.read("arbitrary-url-or-forged-handle")
    source.revision = 2
    with pytest.raises(CL1Error):
        cache.read(handle)
    assert not cache._entries
    source.revision = 1
    handle = cache.retain(source.context("x")).split("/")[-1]
    replacement = cache.retain(source.context("y")).split("/")[-1]
    with pytest.raises(CL1Error):
        cache.read(handle)
    cache._entries[replacement] = (0, *cache._entries[replacement][1:])
    with pytest.raises(CL1Error):
        cache.read(replacement)
    assert not cache._entries


@pytest.mark.parametrize("source_id", ["%2Fetc", "note%252Fother", "%2E%2E", "note%00", "%FF"])
def test_fastmcp_rejects_invalid_or_double_encoded_resource_ids(source_id):
    source = Client("source")
    source.fetch_source = lambda *args, **kwargs: pytest.fail("Invalid ID reached client")
    with TestClient(
        create_server(source).streamable_http_app(), base_url="http://127.0.0.1:8000"
    ) as client:
        result = call(client, 1, "resources/read", {"uri": f"memstrata-cl1://source/{source_id}/1"})
        assert "error" in result


def test_fastmcp_129_passes_escaped_template_parameter_literally(monkeypatch):
    import memstrata_client.mcp as adapter

    seen = []
    original = adapter._resource_source_id

    def capture(value):
        seen.append(value)
        return original(value)

    monkeypatch.setattr(adapter, "_resource_source_id", capture)
    with TestClient(
        create_server(Client("source")).streamable_http_app(), base_url="http://127.0.0.1:8000"
    ) as client:
        result = call(client, 1, "resources/read", {"uri": "memstrata-cl1://source/note%3Aid/1"})
        assert json.loads(result["result"]["contents"][0]["text"])["source_id"] == "note:id"
    assert seen == ["note%3Aid"]


def test_packet_limits_and_integrity_refuse_without_retrieval_replay():
    from memstrata_client.mcp import RESOURCE_BYTE_LIMIT

    source = Client("a" * (RESOURCE_BYTE_LIMIT + 1))
    cache = PacketResources(source)
    with pytest.raises(CL1Error, match="envelope"):
        cache.retain(source.context("x"))
    assert not cache._entries
    source.text = "small"
    packet = source.context("x")
    handle = cache.retain(packet).split("/")[-1]
    packet.assembled_context = "changed"
    with pytest.raises(CL1Error, match="integrity"):
        cache.read(handle)


def test_stdio_cli_round_trip_to_loopback_fake_cl1(tmp_path):
    import sys
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from pathlib import Path
    from threading import Thread

    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from pydantic import AnyUrl

    from tests.cl1_fixture import receipt, source_payload

    source = source_payload()
    packet = receipt()
    packet["source_scope"] = "selected"
    packet["documents"][0].update(session_index=0, turn_index=0)
    packet["source_bindings"][0]["source_sha256"] = source["source_sha256"]
    packet["documents"][0]["source_sha256"] = source["source_sha256"]
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, payload):
            raw = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            calls.append(("GET", self.path, self.headers.get("Authorization")))
            if self.path.startswith("/sources/cl1/v1/note?"):
                self.reply(source)
            else:
                self.send_error(404)

        def do_POST(self):
            calls.append(("POST", self.path, self.headers.get("Authorization")))
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/context/cl1/v1" and body["source_ids"] == ["note"]:
                self.reply(packet)
            else:
                self.send_error(404)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    async def round_trip():
        params = StdioServerParameters(
            command=sys.executable,
            args=[
                "-B",
                "-m",
                "memstrata_client.mcp_cli",
                "--project",
                "project",
                "--source-id",
                "note",
                "--url",
                f"http://127.0.0.1:{httpd.server_port}",
            ],
            cwd=str(Path(__file__).resolve().parents[1]),
            env={
                "MEMSTRATA_CL1_TOKEN": "cl1_fixture",
                "PYTHONIOENCODING": "utf-8",
                "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"),
                "HOME": str(tmp_path),
                "USERPROFILE": str(tmp_path),
                "APPDATA": str(tmp_path),
                "LOCALAPPDATA": str(tmp_path),
                "LANGSMITH_TRACING": "false",
                "OTEL_SDK_DISABLED": "true",
            },
        )
        assert "cl1_fixture" not in " ".join(params.args)
        with anyio.fail_after(25):
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    assert {t.name for t in listed.tools} == {
                        "cl1_get_context",
                        "cl1_fetch_source",
                        "cl1_source_status",
                    }
                    assert all(
                        t.annotations.readOnlyHint and not t.annotations.destructiveHint
                        for t in listed.tools
                    )
                    result = await session.call_tool("cl1_get_context", {"question": "What?"})
                    assert not result.isError
                    data = result.structuredContent or json.loads(result.content[0].text)
                    fetched = await session.read_resource(AnyUrl(data["packet_resource"]))
                    assert fetched.contents[0].text == packet["assembled_context"]
                    assert (
                        data["packet_sha256"]
                        == hashlib.sha256(packet["assembled_context"].encode()).hexdigest()
                    )

    try:
        anyio.run(round_trip)
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)
    assert not thread.is_alive()
    assert [method for method, _, _ in calls] == ["POST", "GET"]
    assert all(auth == "Bearer cl1_fixture" for _, _, auth in calls)
