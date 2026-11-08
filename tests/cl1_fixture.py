# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""Public-contract synthetic receipt, with no product/engine imports."""

import hashlib
import json

import httpx

from memstrata_client.cl1 import CL1Client

TEXT = "The meeting is Friday."


def source_payload():
    sessions = [
        {
            "date": "2026-10-26",
            "turns": [
                {
                    "role": "source",
                    "speaker": "Notes",
                    "text": TEXT,
                    "legacy_role": "source",
                    "legacy_strip": False,
                }
            ],
        }
    ]
    canonical = json.dumps(
        {"sessions": sessions}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return {
        "contract": "memstrata/cl1-source/v1",
        "project_id": "project",
        "source_id": "note",
        "revision": 1,
        "source_sha256": hashlib.sha256(canonical).hexdigest(),
        "sessions": sessions,
        "metadata": {},
        "offset_basis": "turn_utf8",
        "canonicalization": "cl1-normalized-sessions/v1",
    }


def receipt():
    return {
        "contract": "memstrata/cl1-context/v1",
        "status": "ready",
        "project_id": "project",
        "requested_profile": "standard_8k",
        "effective_profile": "standard_8k",
        "tokenizer_id": "synthetic/v1",
        "evidence_token_count": 8,
        "evidence_token_ceiling": 8192,
        "retrieval_policy_version": "synthetic/v1",
        "baseline_policy_id": "synthetic/v1",
        "source_scope": "all_ready",
        "library_sources_searchable": 1,
        "candidate_source_count": 1,
        "assembled_context": TEXT,
        "fallback_used": False,
        "source_validation_passed": True,
        "completion_status": "complete",
        "answer_correctness": "NOT_MEASURED",
        "source_bindings": [{"source_id": "note", "revision": 1, "source_sha256": "a" * 64}],
        "documents": [
            {
                "quote": TEXT,
                "source_id": "note",
                "revision": 1,
                "session_index": 2,
                "turn_index": 3,
                "date": "2026-10-26",
                "role": "source",
                "speaker": "Notes",
                "start_byte": 0,
                "end_byte": len(TEXT),
                "packet_start_byte": 0,
                "packet_end_byte": len(TEXT),
                "source_sha256": "a" * 64,
            }
        ],
    }


def mock_client(calls):
    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=receipt())

    transport = httpx.MockTransport(handle)
    sync = httpx.Client(transport=transport)
    asynchronous = httpx.AsyncClient(transport=transport)
    client = CL1Client(
        "http://127.0.0.1:8000",
        project_id="project",
        token="cl1_synthetic",
        source_scope="all_ready",
        client=sync,
        async_client=asynchronous,
    )
    return client, sync, asynchronous
