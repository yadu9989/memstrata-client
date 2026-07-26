"""Synthetic runtime for integration testing; it contains no memory logic."""

from __future__ import annotations

import hashlib
import json
import sys
from typing import Any

from memstrata_client.validation import PROTOCOL


def _response(request: dict[str, Any]) -> dict[str, Any]:
    request_id = request.get("request_id", "invalid")
    base = {
        "protocol": PROTOCOL,
        "request_id": request_id,
        "runtime": {"version": "0.1.0-mock", "engine": "synthetic-mock"},
    }
    operation = request.get("operation")
    if operation == "status":
        return {
            **base,
            "status": "ok",
            "device": {"device_id": "synthetic-mock-device"},
            "license": {"status": "mock", "mode": "test"},
        }
    if operation == "activate":
        return {
            **base,
            "status": "ok",
            "activation": {"status": "mock", "mode": "test"},
        }
    if operation != "process":
        return {
            **base,
            "status": "error",
            "error": {"code": "UNSUPPORTED_OPERATION", "message": "operation is unsupported"},
        }
    messages = request.get("messages")
    if not isinstance(messages, list) or not messages:
        return {
            **base,
            "status": "error",
            "error": {"code": "INVALID_REQUEST", "message": "messages are required"},
        }
    content = str(messages[-1].get("content", ""))
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    evidence_id = f"ev-{digest[:16]}"
    return {
        **base,
        "status": "ok",
        "result": {
            "memory": [
                {
                    "memory_id": f"mem-{digest[:16]}",
                    "text": content,
                    "kind": "synthetic_echo",
                    "evidence_ids": [evidence_id],
                }
            ],
            "claims": [
                {
                    "claim_id": f"claim-{digest[:16]}",
                    "text": "The synthetic runtime echoed the final input message.",
                    "status": "SUPPORTED",
                    "evidence_ids": [evidence_id],
                }
            ],
            "evidence": [
                {
                    "evidence_id": evidence_id,
                    "kind": "input_message",
                    "content": content,
                    "source": "request.messages[-1]",
                }
            ],
            "assurance": {
                "source_truth": "NOT_ASSERTED",
                "runtime_integrity": "UNSIGNED_TEST_RUNTIME",
                "license_mode": "test",
            },
        },
    }


def main() -> int:
    line = sys.stdin.buffer.readline()
    if not line or sys.stdin.buffer.readline():
        return 2
    try:
        request = json.loads(line)
        response = _response(request)
    except Exception:
        return 2
    sys.stdout.write(json.dumps(response, separators=(",", ":"), sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
