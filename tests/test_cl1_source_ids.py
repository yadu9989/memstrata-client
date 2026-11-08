# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""Source IDs that are path segments ('.' and '..') are refused before any request."""

import httpx
import pytest

from memstrata_client.cl1 import CL1Client


@pytest.mark.parametrize("source_id", [".", ".."])
@pytest.mark.parametrize("operation", ["remove", "status", "fetch"])
def test_dot_segments_are_rejected_without_a_request(operation, source_id):
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json={})

    calls = {
        "remove": lambda c: c.remove_source(source_id, expected_revision=1),
        "status": lambda c: c.source_status(source_id),
        "fetch": lambda c: c.fetch_source(source_id),
    }
    with httpx.Client(transport=httpx.MockTransport(handler)) as wire:
        client = CL1Client(
            "http://127.0.0.1:9101",
            project_id="project",
            token="cl1_synthetic",
            source_scope="all_ready",
            client=wire,
        )
        with pytest.raises(ValueError):
            calls[operation](client)
    assert seen == []
