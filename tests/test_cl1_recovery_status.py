# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""Offline check: list and remove report the server's HTTP status faithfully.

The server decides whether these operations are allowed. The client reports the
status unchanged: it must neither hide a refusal nor retry it, and must not copy the
response body or the credential into the exception.
"""

import asyncio

import httpx
import pytest

from memstrata_client.cl1 import CL1Client, CL1Error

TOKEN = "cl1_synthetic"
BODY = {"detail": "synthetic refusal text that must not be copied into the error"}


def _client(status, seen, *, asynchronous=False):
    def handler(request):
        seen.append((request.method, request.url.path))
        return httpx.Response(status, json=BODY)

    transport = httpx.MockTransport(handler)
    if asynchronous:
        wire = httpx.AsyncClient(transport=transport)
        kwargs = {"async_client": wire}
    else:
        wire = httpx.Client(transport=transport)
        kwargs = {"client": wire}
    client = CL1Client(
        "http://127.0.0.1:9101",
        project_id="project",
        token=TOKEN,
        source_scope="all_ready",
        **kwargs,
    )
    return client, wire


OPERATIONS = {
    "list": lambda c: c.list_sources(),
    "delete": lambda c: c.remove_source("note:1", expected_revision=1),
}
EXPECTED = {
    "list": ("GET", "/sources/cl1/v1"),
    "delete": ("DELETE", "/sources/cl1/v1/note:1"),
}


@pytest.mark.parametrize("status", [401, 402, 403, 404, 409])
@pytest.mark.parametrize("operation", sorted(OPERATIONS))
def test_sync_refusal_status_is_reported_once_without_leaking(operation, status):
    seen = []
    client, wire = _client(status, seen)
    with wire, pytest.raises(CL1Error) as caught:
        OPERATIONS[operation](client)
    assert caught.value.status_code == status
    assert seen == [EXPECTED[operation]]  # one request: no retry, no fallback endpoint
    text = f"{caught.value} {caught.value!r}"
    assert TOKEN not in text and BODY["detail"] not in text


@pytest.mark.parametrize("operation", ["list", "delete"])
def test_async_refusal_status_is_reported(operation):
    seen = []

    async def run():
        client, wire = _client(402, seen, asynchronous=True)
        async with wire:
            calls = {
                "list": client.alist_sources,
                "delete": lambda: client.aremove_source("note:1", expected_revision=1),
            }
            await calls[operation]()

    with pytest.raises(CL1Error) as caught:
        asyncio.run(run())
    assert caught.value.status_code == 402
    assert seen == [EXPECTED[operation]]
    assert TOKEN not in f"{caught.value} {caught.value!r}"
