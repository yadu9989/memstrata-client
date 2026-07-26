from __future__ import annotations

import sys

import pytest

from memstrata_client import MemStrata, ProtocolError
from memstrata_client.models import Message, normalize_messages, normalize_options


def mock_command() -> tuple[str, ...]:
    return (sys.executable, "-m", "memstrata_client.mock_runtime")


def test_mock_runtime_end_to_end() -> None:
    result = MemStrata(mock_command()).process(
        [
            {"role": "system", "content": "Use the supplied evidence."},
            {"role": "user", "content": "Project Atlas moved to Toronto."},
        ]
    )
    assert result.memory[0].text == "Project Atlas moved to Toronto."
    assert result.claims[0].evidence_ids == (result.evidence[0].evidence_id,)
    assert result.assurance.source_truth == "NOT_ASSERTED"
    assert result.engine == "synthetic-mock"


def test_status_and_activation_have_bound_request_ids() -> None:
    client = MemStrata(mock_command())
    status = client.status()
    activation = client.activate({"schema": "synthetic-test-license/v1"})
    assert status["license"]["status"] == "mock"
    assert activation["activation"]["status"] == "mock"


@pytest.mark.parametrize("role", ["developer", "", None, 5])
def test_invalid_roles_fail_before_runtime(role: object) -> None:
    with pytest.raises(ProtocolError, match="message.role"):
        normalize_messages([{"role": role, "content": "x"}])


def test_unknown_message_field_fails() -> None:
    with pytest.raises(ProtocolError, match="unknown fields"):
        normalize_messages([{"role": "user", "content": "x", "private": "leak"}])


def test_empty_and_oversized_message_sets_fail() -> None:
    with pytest.raises(ProtocolError):
        normalize_messages([])
    with pytest.raises(ProtocolError):
        normalize_messages([Message("user", "x")] * 513)


def test_options_accept_scalars_only() -> None:
    assert dict(normalize_options({"limit": 5, "strict": True})) == {
        "limit": 5,
        "strict": True,
    }
    with pytest.raises(ProtocolError, match="JSON scalar"):
        normalize_options({"nested": {"not": "allowed"}})
