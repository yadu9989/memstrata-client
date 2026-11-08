# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""Documented limits are enforced exactly at their boundary, and values stay immutable.

The limits below are pinned as literals on purpose: a test that reads the limit from the
code under test would follow a mistaken change instead of catching it.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import os
import sys

import pytest

from memstrata_client import ProtocolError, RuntimeFailure
from memstrata_client.config import (
    ClientConfig,
    ConfigurationError,
    default_config_path,
    load_config,
    save_config,
)
from memstrata_client.mcp_cli import parser
from memstrata_client.models import (
    Assurance,
    Claim,
    Evidence,
    MemoryItem,
    Message,
    ProcessResult,
    normalize_messages,
    normalize_options,
)
from memstrata_client.transport import SubprocessTransport, validate_runtime_path
from memstrata_client.validation import (
    PROTOCOL,
    parse_activation_response,
    parse_process_response,
    parse_status_response,
)
from tests.test_validation import valid_response

MIB = 1024 * 1024


# ---------------------------------------------------------------- models


def test_message_content_limit_is_exact_and_rejects_empty_or_non_text():
    assert Message.from_value({"role": "user", "content": "x" * 1_000_000}).content
    with pytest.raises(ProtocolError, match="exceeds 1000000"):
        Message.from_value({"role": "user", "content": "x" * 1_000_001})
    for bad in ("", 5, None, b"x"):
        with pytest.raises(ProtocolError, match="non-empty string"):
            Message.from_value({"role": "user", "content": bad})


def test_message_name_limit_is_exact_and_name_is_omitted_when_absent():
    assert Message.from_value({"role": "user", "content": "x", "name": "n" * 128}).name
    with pytest.raises(ProtocolError, match="exceeds 128"):
        Message.from_value({"role": "user", "content": "x", "name": "n" * 129})
    assert "name" not in Message("user", "x").to_dict()
    assert Message("user", "x", "ann").to_dict()["name"] == "ann"


def test_message_count_and_total_size_limits_are_exact():
    assert len(normalize_messages([{"role": "user", "content": "x"}] * 512)) == 512
    with pytest.raises(ProtocolError, match="1..512"):
        normalize_messages([{"role": "user", "content": "x"}] * 513)
    with pytest.raises(ProtocolError, match="1..512"):
        normalize_messages([])
    four_million = [{"role": "user", "content": "x" * 1_000_000}] * 4
    assert len(normalize_messages(four_million)) == 4
    with pytest.raises(ProtocolError, match="total message content exceeds 4000000"):
        normalize_messages([*four_million, {"role": "user", "content": "x"}])


@pytest.mark.parametrize("bad", ["abc", b"abc", 5, None, {"role": "user", "content": "x"}])
def test_messages_must_be_a_sequence(bad):
    with pytest.raises(ProtocolError, match="messages must be a sequence"):
        normalize_messages(bad)


def test_option_limits_are_exact():
    assert len(normalize_options({f"k{i}": i for i in range(64)})) == 64
    with pytest.raises(ProtocolError, match="at most 64 keys"):
        normalize_options({f"k{i}": i for i in range(65)})
    with pytest.raises(ProtocolError, match="at most 64 keys"):
        normalize_options(["not", "a", "mapping"])
    assert normalize_options({"k" * 128: 1})
    for bad_key in ("", "k" * 129, 5):
        with pytest.raises(ProtocolError, match="option keys must be non-empty strings"):
            normalize_options({bad_key: 1})
    with pytest.raises(ProtocolError, match="JSON scalar"):
        normalize_options({"k": [1]})


def test_public_values_are_immutable_and_do_not_leak_raw_in_repr():
    assurance = Assurance("NOT_ASSERTED", "SIGNED_ARTIFACT", "evaluation")
    result = ProcessResult((), (), (), assurance, "r", "v", "e", {"raw-marker": 1})
    for value, attribute in [
        (Message("user", "x"), "role"),
        (Evidence("e", "k", "c"), "content"),
        (Claim("c", "t", "s", ()), "text"),
        (MemoryItem("m", "t", "k", ()), "text"),
        (assurance, "source_truth"),
        (result, "engine"),
        (ClientConfig(("x",)), "timeout_seconds"),
    ]:
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(value, attribute, "changed")
    assert "raw-marker" not in repr(result)


# ------------------------------------------------------------ validation


def _parse(value):
    return parse_process_response(value, "req-1")


def test_evidence_text_limit_is_exact_and_empty_or_non_text_is_refused():
    ok = valid_response()
    ok["result"]["evidence"][0]["content"] = "x" * 1_000_000
    assert _parse(ok).evidence[0].content
    for bad, match in [("x" * 1_000_001, "exceeds 1000000"), ("", "non-empty"), (5, "non-empty")]:
        value = valid_response()
        value["result"]["evidence"][0]["content"] = bad
        with pytest.raises(ProtocolError, match=match):
            _parse(value)


def test_section_and_identifier_list_limits_are_exact():
    at_limit = valid_response()
    at_limit["result"]["memory"] = [
        {"memory_id": f"m{i}", "text": "t", "kind": "k", "evidence_ids": ["e1"]}
        for i in range(10_000)
    ]
    assert len(_parse(at_limit).memory) == 10_000
    over = copy.deepcopy(at_limit)
    over["result"]["memory"].append(copy.deepcopy(over["result"]["memory"][0]))
    with pytest.raises(ProtocolError, match="at most 10000 entries"):
        _parse(over)
    for bad in ("e1", {"e1": 1}, 5):
        value = valid_response()
        value["result"]["memory"] = bad
        with pytest.raises(ProtocolError, match="must be a list with at most"):
            _parse(value)

    many = valid_response()
    many["result"]["evidence"] = [
        {"evidence_id": f"e{i}", "kind": "quote", "content": "c"} for i in range(10_000)
    ]
    many["result"]["memory"][0]["evidence_ids"] = [f"e{i}" for i in range(10_000)]
    many["result"]["claims"][0]["evidence_ids"] = ["e0"]
    assert len(_parse(many).memory[0].evidence_ids) == 10_000
    many["result"]["memory"][0]["evidence_ids"].append("e10000")
    with pytest.raises(ProtocolError, match="identifier list"):
        _parse(many)
    for bad in ("e1", 5):
        value = valid_response()
        value["result"]["memory"][0]["evidence_ids"] = bad
        with pytest.raises(ProtocolError, match="identifier list"):
            _parse(value)


def test_evidence_source_is_optional_but_validated_when_present():
    value = valid_response()
    del value["result"]["evidence"][0]["source"]
    assert _parse(value).evidence[0].source is None
    for bad in (5, "", "s" * 4097):
        value = valid_response()
        value["result"]["evidence"][0]["source"] = bad
        with pytest.raises(ProtocolError):
            _parse(value)


def _status(license_value):
    return {
        "protocol": PROTOCOL,
        "request_id": "req-1",
        "status": "ok",
        "runtime": {"version": "1.0.0", "engine": "test"},
        "device": {"device_id": "device-1"},
        "license": license_value,
    }


@pytest.mark.parametrize("field", ["expires_at", "serial"])
def test_license_numbers_must_be_real_integers(field):
    good = {"status": "active", "plan": "p", "mode": "m", "expires_at": 2_000_000_000, "serial": 7}
    assert parse_status_response(_status(good), "req-1")["license"][field]
    for bad in (True, False, "5", 1.5, None):
        with pytest.raises(ProtocolError, match=f"license.{field} must be an integer"):
            parse_status_response(_status({**good, field: bad}), "req-1")


def test_activation_expiry_must_be_a_real_integer():
    def activation(expires_at):
        return {
            "protocol": PROTOCOL,
            "request_id": "req-1",
            "status": "ok",
            "runtime": {"version": "1.0.0", "engine": "test"},
            "activation": {"status": "active", "plan": "p", "mode": "m", "expires_at": expires_at},
        }

    assert parse_activation_response(activation(5), "req-1")
    for bad in (True, "5", 1.5):
        with pytest.raises(ProtocolError, match="activation.expires_at must be an integer"):
            parse_activation_response(activation(bad), "req-1")


# ---------------------------------------------------------------- config


class _FakeOS:
    """Only the two attributes default_config_path reads; pathlib keeps the real os.name."""

    def __init__(self, name):
        self.name = name
        self.environ = os.environ


def test_config_location_depends_on_platform_and_environment(monkeypatch, tmp_path):
    from memstrata_client import config as config_module

    monkeypatch.delenv("MEMSTRATA_CLIENT_CONFIG", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(config_module, "os", _FakeOS("posix"))
    assert default_config_path() == tmp_path / "xdg" / "memstrata" / "client.json"
    monkeypatch.setattr(config_module, "os", _FakeOS("nt"))
    assert default_config_path() == tmp_path / "appdata" / "MemStrata" / "client.json"
    monkeypatch.delenv("APPDATA")
    assert default_config_path() == tmp_path / "xdg" / "memstrata" / "client.json"
    monkeypatch.setenv("MEMSTRATA_CLIENT_CONFIG", str(tmp_path / "override.json"))
    assert default_config_path() == tmp_path / "override.json"


def test_save_creates_missing_parents_is_repeatable_and_sorted(tmp_path):
    target = tmp_path / "a" / "b" / "client.json"
    config = ClientConfig((sys.executable,), 5.0)
    assert save_config(config, target) == target
    assert save_config(config, target) == target  # an existing directory is fine
    text = target.read_text(encoding="utf-8")
    keys = [k for k in json.loads(text)]
    assert keys == sorted(keys) and text.index("runtime_command") < text.index("schema")
    assert load_config(target) == config


def _write(tmp_path, **changes):
    value = {
        "schema": "memstrata.client-config/v1",
        "runtime_command": [sys.executable],
        "timeout_seconds": 5,
    }
    value.update(changes)
    path = tmp_path / "client.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "command", ["python", [], [""], [5], [sys.executable, ""], [sys.executable, 5]]
)
def test_config_command_must_be_a_non_empty_string_list(tmp_path, command):
    with pytest.raises(ConfigurationError, match="non-empty string list"):
        load_config(_write(tmp_path, runtime_command=command))


@pytest.mark.parametrize("timeout", [0, -1, 0.0, True, False, "5", None])
def test_config_timeout_must_be_a_positive_number(tmp_path, timeout):
    with pytest.raises(ConfigurationError, match="timeout_seconds must be positive"):
        load_config(_write(tmp_path, timeout_seconds=timeout))


def test_config_accepts_a_small_positive_timeout(tmp_path):
    assert load_config(_write(tmp_path, timeout_seconds=0.5)).timeout_seconds == 0.5


# ------------------------------------------------------------- transport


def _runtime(code):
    return (sys.executable, "-c", code)


def test_transport_constructor_rejects_bad_arguments():
    for command in ([], ["x", ""], ["x", 5], [5]):
        with pytest.raises(ValueError, match="non-empty strings"):
            SubprocessTransport(command)
    with pytest.raises(ValueError, match="timeout must be positive"):
        SubprocessTransport(["x"], timeout=0)
    with pytest.raises(ValueError, match="max_response_bytes must be positive"):
        SubprocessTransport(["x"], max_response_bytes=0)


def test_request_is_compact_sorted_utf8_json_on_one_line():
    code = (
        "import sys, json; line = sys.stdin.buffer.readline();"
        "print(json.dumps({'line': line.decode('utf-8')}))"
    )
    response = SubprocessTransport(_runtime(code)).execute({"b": "café", "a": 1})
    assert response["line"] == '{"a":1,"b":"café"}\n'


def test_request_size_limit_is_exact():
    code = "import sys, json; print(json.dumps({'n': len(sys.stdin.buffer.read())}))"
    transport = SubprocessTransport(_runtime(code), timeout=60)
    limit = 8 * MIB
    assert transport.execute({"k": "x" * (limit - 9)})["n"] == limit
    with pytest.raises(ProtocolError, match="request exceeds"):
        transport.execute({"k": "x" * (limit - 8)})


def test_response_size_limit_is_exact():
    def runtime(extra):
        return _runtime(
            "import sys; sys.stdin.readline();"
            f"sys.stdout.buffer.write(('{{\"p\":\"' + 'x' * {extra} + '\"}}\\n').encode())"
        )

    limit = 100
    assert SubprocessTransport(runtime(limit - 9), max_response_bytes=limit).execute({})
    with pytest.raises(ProtocolError, match="exceeds"):
        SubprocessTransport(runtime(limit - 8), max_response_bytes=limit).execute({})


def test_stderr_limit_is_exact_and_content_is_never_surfaced():
    def runtime(size):
        return _runtime(
            "import sys; sys.stdin.readline(); sys.stderr.write('e' * "
            f"{size}); sys.stdout.write('{{}}\\n')"
        )

    assert SubprocessTransport(runtime(64 * 1024)).execute({}) == {}
    with pytest.raises(RuntimeFailure, match="diagnostics exceeded") as caught:
        SubprocessTransport(runtime(64 * 1024 + 1)).execute({})
    assert "eeee" not in str(caught.value)


def test_runtime_path_check_applies_to_relative_paths_with_separators(tmp_path):
    validate_runtime_path(["bare-name-found-on-path-later"])
    validate_runtime_path([sys.executable])
    for missing in ("./definitely-missing-runtime", str(tmp_path / "missing"), "sub/dir/missing"):
        with pytest.raises(FileNotFoundError):
            validate_runtime_path([missing])


# ------------------------------------------------------------------- cli


def test_mcp_launcher_requires_a_project():
    with pytest.raises(SystemExit) as caught:
        parser().parse_args([])
    assert caught.value.code == 2
