from __future__ import annotations

import json
import sys
from dataclasses import dataclass

import pytest

from memstrata_client.adapters import from_langchain, from_role_content
from memstrata_client.config import ClientConfig, load_config, save_config
from memstrata_client.errors import ConfigurationError, ProtocolError


def test_config_round_trip(tmp_path) -> None:
    path = tmp_path / "client.json"
    expected = ClientConfig((sys.executable, "-m", "memstrata_client.mock_runtime"), 3.5)
    assert save_config(expected, path) == path
    assert load_config(path) == expected


def test_config_rejects_unknown_fields(tmp_path) -> None:
    path = tmp_path / "client.json"
    path.write_text(
        json.dumps(
            {
                "schema": "memstrata.client-config/v1",
                "runtime_command": [sys.executable],
                "timeout_seconds": 1,
                "license_key": "must-not-be-stored",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="unsupported shape"):
        load_config(path)


def test_role_content_adapter() -> None:
    assert from_role_content([{"role": "user", "content": "hello"}])[0].content == "hello"


@dataclass
class FakeLangChainMessage:
    type: str
    content: str
    name: str | None = None


def test_langchain_adapter_without_dependency() -> None:
    values = from_langchain(
        [
            FakeLangChainMessage("human", "question"),
            FakeLangChainMessage("ai", "answer"),
        ]
    )
    assert [item.role for item in values] == ["user", "assistant"]


def test_langchain_adapter_fails_unknown_shape() -> None:
    with pytest.raises(ProtocolError):
        from_langchain([FakeLangChainMessage("function", "call")])
