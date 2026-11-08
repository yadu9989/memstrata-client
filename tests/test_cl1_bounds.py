# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""Non-task calls read a bounded response and survive pathological JSON."""

import asyncio

import httpx
import pytest

from memstrata_client import cl1
from memstrata_client.cl1 import CL1Client, CL1Error

ONE_MIB = 1024 * 1024
# The documented limits, pinned here on purpose: the tests must not follow the code under test.
CONTEXT_CAP = 8 * ONE_MIB
SOURCE_CAP = 32 * ONE_MIB


def make(handler, *, asynchronous=False):
    transport = httpx.MockTransport(handler)
    kwargs = (
        {"async_client": httpx.AsyncClient(transport=transport)}
        if asynchronous
        else {"client": httpx.Client(transport=transport)}
    )
    return CL1Client(
        "http://127.0.0.1:9101",
        project_id="project",
        token="cl1_synthetic",
        source_scope="all_ready",
        **kwargs,
    )


def chunks(count, *, consumed):
    for _ in range(count):
        consumed.append(1)
        yield b" " * ONE_MIB


async def achunks(count, *, consumed):
    for _ in range(count):
        consumed.append(1)
        yield b" " * ONE_MIB


CALLS = {
    "context": (lambda c: c.context("When?"), CONTEXT_CAP),
    "list": (lambda c: c.list_sources(), SOURCE_CAP),
    "status": (lambda c: c.source_status("note"), SOURCE_CAP),
    "fetch": (lambda c: c.fetch_source("note"), SOURCE_CAP),
}


@pytest.mark.parametrize("name", sorted(CALLS))
def test_oversized_streamed_body_is_refused_and_not_read_to_the_end(name):
    call, maximum = CALLS[name]
    consumed = []
    needed = maximum // ONE_MIB + 4  # a little over the cap, far less than "unbounded"
    client = make(
        lambda request: httpx.Response(200, content=chunks(needed + 50, consumed=consumed))
    )
    with pytest.raises(CL1Error, match="bounded envelope"):
        call(client)
    assert len(consumed) <= needed + 1  # the reader stopped shortly after the cap


@pytest.mark.parametrize("name", sorted(CALLS))
def test_oversized_declared_length_is_refused_before_reading(name):
    call, maximum = CALLS[name]
    client = make(
        lambda request: httpx.Response(
            200, headers={"content-length": str(maximum + 1)}, content=b"{}"
        )
    )
    with pytest.raises(CL1Error, match="bounded envelope"):
        call(client)


@pytest.mark.parametrize("status", [200, 500])
@pytest.mark.parametrize("name", sorted(CALLS))
def test_deeply_nested_json_is_a_clean_error(name, status):
    call, _ = CALLS[name]
    client = make(lambda request: httpx.Response(status, content=b"[" * 200_000))
    with pytest.raises(CL1Error):
        call(client)


def test_async_calls_are_bounded_too():
    async def run():
        for call, maximum in [
            (lambda c: c.acontext("When?"), CONTEXT_CAP),
            (lambda c: c.alist_sources(), SOURCE_CAP),
        ]:
            consumed = []
            needed = maximum // ONE_MIB + 4
            client = make(
                lambda request: httpx.Response(
                    200, content=achunks(needed + 50, consumed=consumed)
                ),
                asynchronous=True,
            )
            with pytest.raises(CL1Error, match="bounded envelope"):
                await call(client)
            assert len(consumed) <= needed + 1  # stopped shortly after the cap

    asyncio.run(run())


def test_normal_sized_responses_still_work():
    client = make(
        lambda request: httpx.Response(
            200,
            json={
                "contract": "memstrata/cl1-source-list/v1",
                "project_id": "project",
                "sources": [],
                "next_cursor": None,
            },
        )
    )
    assert client.list_sources()["sources"] == []


def test_the_limits_are_the_documented_ones():
    assert cl1._MAX_CONTEXT_BYTES == CONTEXT_CAP and cl1._MAX_SOURCE_BYTES == SOURCE_CAP
