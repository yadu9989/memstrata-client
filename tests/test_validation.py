from __future__ import annotations

import copy

import pytest

from memstrata_client import ProtocolError, RuntimeFailure
from memstrata_client.validation import (
    PROTOCOL,
    parse_activation_response,
    parse_process_response,
    parse_status_response,
)


def valid_response() -> dict:
    return {
        "protocol": PROTOCOL,
        "request_id": "req-1",
        "status": "ok",
        "runtime": {"version": "1.0.0", "engine": "test"},
        "result": {
            "memory": [
                {
                    "memory_id": "m1",
                    "text": "value",
                    "kind": "fact",
                    "evidence_ids": ["e1"],
                }
            ],
            "claims": [
                {
                    "claim_id": "c1",
                    "text": "claim",
                    "status": "SUPPORTED",
                    "evidence_ids": ["e1"],
                }
            ],
            "evidence": [
                {
                    "evidence_id": "e1",
                    "kind": "quote",
                    "content": "value",
                    "source": "message:1",
                }
            ],
            "assurance": {
                "source_truth": "NOT_ASSERTED",
                "runtime_integrity": "SIGNED_ARTIFACT",
                "license_mode": "evaluation",
            },
        },
    }


def test_valid_response_parses() -> None:
    parsed = parse_process_response(valid_response(), "req-1")
    assert parsed.memory[0].evidence_ids == ("e1",)
    assert parsed.claims[0].status == "SUPPORTED"


@pytest.mark.parametrize(
    ("mutator", "match"),
    [
        (lambda x: x.update(protocol="future/v9"), "unsupported response protocol"),
        (lambda x: x.update(request_id="other"), "does not match"),
        (lambda x: x.update(extra=True), "unknown fields"),
        (
            lambda x: x["result"]["claims"][0].update(evidence_ids=["missing"]),
            "unknown evidence",
        ),
        (
            lambda x: x["result"]["memory"][0].update(evidence_ids=["missing"]),
            "unknown evidence",
        ),
        (
            lambda x: x["result"]["assurance"].update(source_truth="CERTIFIED_TRUE"),
            "source_truth=NOT_ASSERTED",
        ),
        (
            lambda x: x["result"]["evidence"].append(copy.deepcopy(x["result"]["evidence"][0])),
            "duplicate evidence_id",
        ),
        (
            lambda x: x["result"]["claims"][0].update(private_score=0.99),
            "unknown fields",
        ),
    ],
)
def test_adversarial_responses_fail(mutator, match: str) -> None:
    value = valid_response()
    mutator(value)
    with pytest.raises(ProtocolError, match=match):
        parse_process_response(value, "req-1")


def test_error_response_becomes_runtime_failure() -> None:
    value = {
        "protocol": PROTOCOL,
        "request_id": "req-1",
        "status": "error",
        "runtime": {"version": "1.0.0", "engine": "test"},
        "error": {"code": "LICENSE_EXPIRED", "message": "renew the entitlement"},
    }
    with pytest.raises(RuntimeFailure, match="LICENSE_EXPIRED"):
        parse_process_response(value, "req-1")


def test_error_cannot_smuggle_result() -> None:
    value = {
        "protocol": PROTOCOL,
        "request_id": "req-1",
        "status": "error",
        "runtime": {"version": "1.0.0", "engine": "test"},
        "error": {"code": "NO", "message": "no"},
        "result": {},
    }
    with pytest.raises(ProtocolError, match="must not contain result"):
        parse_process_response(value, "req-1")


def test_status_and_activation_are_strict() -> None:
    status = {
        "protocol": PROTOCOL,
        "request_id": "req-1",
        "status": "ok",
        "runtime": {"version": "1.0.0", "engine": "test"},
        "device": {"device_id": "device-1"},
        "license": {"status": "inactive", "reason": "LICENSE_MISSING"},
    }
    assert parse_status_response(status, "req-1")["device"]["device_id"] == "device-1"

    activation = {
        "protocol": PROTOCOL,
        "request_id": "req-1",
        "status": "ok",
        "runtime": {"version": "1.0.0", "engine": "test"},
        "activation": {
            "status": "active",
            "plan": "trial",
            "mode": "offline",
            "expires_at": 2_000_000_000,
        },
    }
    assert parse_activation_response(activation, "req-1")["activation"]["status"] == "active"


def test_control_response_rejects_smuggled_fields() -> None:
    status = {
        "protocol": PROTOCOL,
        "request_id": "req-1",
        "status": "ok",
        "runtime": {"version": "1.0.0", "engine": "test"},
        "device": {"device_id": "device-1", "raw_hardware": "leak"},
        "license": {"status": "inactive", "reason": "LICENSE_MISSING"},
    }
    with pytest.raises(ProtocolError, match="unknown fields"):
        parse_status_response(status, "req-1")
