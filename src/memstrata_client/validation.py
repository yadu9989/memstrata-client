"""Fail-closed validation for memstrata.runtime/v1."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from memstrata_client.errors import ProtocolError, RuntimeFailure
from memstrata_client.models import Assurance, Claim, Evidence, MemoryItem, ProcessResult

PROTOCOL = "memstrata.runtime/v1"
MAX_ITEMS_PER_SECTION = 10_000
MAX_TEXT_CHARS = 1_000_000


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError(f"{label} must be an object")
    return value


def _keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str] = frozenset(),
    label: str,
) -> None:
    missing = required - set(value)
    unknown = set(value) - required - optional
    if missing:
        raise ProtocolError(f"{label} is missing fields: {sorted(missing)}")
    if unknown:
        raise ProtocolError(f"{label} has unknown fields: {sorted(unknown)}")


def _text(value: Any, label: str, *, maximum: int = MAX_TEXT_CHARS) -> str:
    if not isinstance(value, str) or not value:
        raise ProtocolError(f"{label} must be a non-empty string")
    if len(value) > maximum:
        raise ProtocolError(f"{label} exceeds {maximum} characters")
    return value


def _objects(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) > MAX_ITEMS_PER_SECTION:
        raise ProtocolError(
            f"{label} must be a list with at most {MAX_ITEMS_PER_SECTION} entries"
        )
    return [_mapping(item, f"{label}[{index}]") for index, item in enumerate(value)]


def _ids(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > MAX_ITEMS_PER_SECTION:
        raise ProtocolError(f"{label} must be an identifier list")
    result = tuple(_text(item, f"{label}[]", maximum=256) for item in value)
    if len(result) != len(set(result)):
        raise ProtocolError(f"{label} contains duplicates")
    return result


def _control_root(
    payload: Any,
    expected_request_id: str,
    *,
    success_field: str,
    extra_optional: set[str] = frozenset(),
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    root = _mapping(payload, "response")
    _keys(
        root,
        required={"protocol", "request_id", "status", "runtime"},
        optional={success_field, "error"} | extra_optional,
        label="response",
    )
    if root["protocol"] != PROTOCOL:
        raise ProtocolError(f"unsupported response protocol: {root['protocol']!r}")
    if root["request_id"] != expected_request_id:
        raise ProtocolError("response request_id does not match the request")
    runtime = _mapping(root["runtime"], "response.runtime")
    _keys(runtime, required={"version", "engine"}, label="response.runtime")
    _text(runtime["version"], "runtime.version", maximum=128)
    _text(runtime["engine"], "runtime.engine", maximum=128)
    if root["status"] == "error":
        if success_field in root:
            raise ProtocolError(f"error response must not contain {success_field}")
        error = _mapping(root.get("error"), "response.error")
        _keys(error, required={"code", "message"}, label="response.error")
        code = _text(error["code"], "error.code", maximum=128)
        message = _text(error["message"], "error.message", maximum=2048)
        raise RuntimeFailure(f"runtime rejected request ({code}): {message}")
    if root["status"] != "ok":
        raise ProtocolError(f"unknown response status: {root['status']!r}")
    if "error" in root:
        raise ProtocolError("success response must not contain error")
    value = _mapping(root.get(success_field), f"response.{success_field}")
    return root, value


def parse_status_response(payload: Any, expected_request_id: str) -> Mapping[str, Any]:
    root, license_value = _control_root(
        payload,
        expected_request_id,
        success_field="license",
        extra_optional={"device"},
    )
    device = _mapping(root.get("device"), "response.device")
    _keys(device, required={"device_id"}, label="response.device")
    _text(device["device_id"], "device.device_id", maximum=256)
    status = license_value.get("status")
    if status == "active":
        _keys(
            license_value,
            required={"status", "plan", "mode", "expires_at", "serial"},
            label="response.license",
        )
        _text(license_value["plan"], "license.plan", maximum=128)
        _text(license_value["mode"], "license.mode", maximum=128)
        if not isinstance(license_value["expires_at"], int) or isinstance(
            license_value["expires_at"], bool
        ):
            raise ProtocolError("license.expires_at must be an integer")
        if not isinstance(license_value["serial"], int) or isinstance(
            license_value["serial"], bool
        ):
            raise ProtocolError("license.serial must be an integer")
    elif status == "inactive":
        _keys(
            license_value,
            required={"status", "reason"},
            label="response.license",
        )
        _text(license_value["reason"], "license.reason", maximum=128)
    elif status == "mock":
        _keys(
            license_value,
            required={"status", "mode"},
            label="response.license",
        )
        if license_value["mode"] != "test":
            raise ProtocolError("mock status must report mode=test")
    else:
        raise ProtocolError(f"unknown license status: {status!r}")
    return MappingProxyType(root)


def parse_activation_response(payload: Any, expected_request_id: str) -> Mapping[str, Any]:
    root, activation = _control_root(
        payload,
        expected_request_id,
        success_field="activation",
    )
    status = activation.get("status")
    if status == "active":
        _keys(
            activation,
            required={"status", "plan", "mode", "expires_at"},
            label="response.activation",
        )
        _text(activation["plan"], "activation.plan", maximum=128)
        _text(activation["mode"], "activation.mode", maximum=128)
        if not isinstance(activation["expires_at"], int) or isinstance(
            activation["expires_at"], bool
        ):
            raise ProtocolError("activation.expires_at must be an integer")
    elif status == "mock":
        _keys(
            activation,
            required={"status", "mode"},
            label="response.activation",
        )
        if activation["mode"] != "test":
            raise ProtocolError("mock activation must report mode=test")
    else:
        raise ProtocolError(f"unknown activation status: {status!r}")
    return MappingProxyType(root)


def parse_process_response(payload: Any, expected_request_id: str) -> ProcessResult:
    root = _mapping(payload, "response")
    _keys(
        root,
        required={"protocol", "request_id", "status", "runtime"},
        optional={"result", "error"},
        label="response",
    )
    if root["protocol"] != PROTOCOL:
        raise ProtocolError(f"unsupported response protocol: {root['protocol']!r}")
    if root["request_id"] != expected_request_id:
        raise ProtocolError("response request_id does not match the request")

    status = root["status"]
    if status not in {"ok", "error"}:
        raise ProtocolError(f"unknown response status: {status!r}")

    runtime = _mapping(root["runtime"], "response.runtime")
    _keys(runtime, required={"version", "engine"}, label="response.runtime")
    runtime_version = _text(runtime["version"], "runtime.version", maximum=128)
    engine = _text(runtime["engine"], "runtime.engine", maximum=128)

    if status == "error":
        if "result" in root:
            raise ProtocolError("error response must not contain result")
        error = _mapping(root.get("error"), "response.error")
        _keys(error, required={"code", "message"}, label="response.error")
        code = _text(error["code"], "error.code", maximum=128)
        message = _text(error["message"], "error.message", maximum=2048)
        raise RuntimeFailure(f"runtime rejected request ({code}): {message}")

    if "error" in root:
        raise ProtocolError("success response must not contain error")
    result = _mapping(root.get("result"), "response.result")
    _keys(
        result,
        required={"memory", "claims", "evidence", "assurance"},
        label="response.result",
    )

    evidence: list[Evidence] = []
    evidence_ids: set[str] = set()
    for index, item in enumerate(_objects(result["evidence"], "result.evidence")):
        _keys(
            item,
            required={"evidence_id", "kind", "content"},
            optional={"source"},
            label=f"evidence[{index}]",
        )
        evidence_id = _text(item["evidence_id"], "evidence_id", maximum=256)
        if evidence_id in evidence_ids:
            raise ProtocolError(f"duplicate evidence_id: {evidence_id}")
        evidence_ids.add(evidence_id)
        source = item.get("source")
        if source is not None:
            source = _text(source, "evidence.source", maximum=4096)
        evidence.append(
            Evidence(
                evidence_id=evidence_id,
                kind=_text(item["kind"], "evidence.kind", maximum=128),
                content=_text(item["content"], "evidence.content"),
                source=source,
            )
        )

    claims: list[Claim] = []
    claim_ids: set[str] = set()
    for index, item in enumerate(_objects(result["claims"], "result.claims")):
        _keys(
            item,
            required={"claim_id", "text", "status", "evidence_ids"},
            label=f"claim[{index}]",
        )
        claim_id = _text(item["claim_id"], "claim.claim_id", maximum=256)
        if claim_id in claim_ids:
            raise ProtocolError(f"duplicate claim_id: {claim_id}")
        claim_ids.add(claim_id)
        refs = _ids(item["evidence_ids"], "claim.evidence_ids")
        missing = set(refs) - evidence_ids
        if missing:
            raise ProtocolError(f"claim {claim_id} references unknown evidence: {sorted(missing)}")
        claims.append(
            Claim(
                claim_id=claim_id,
                text=_text(item["text"], "claim.text"),
                status=_text(item["status"], "claim.status", maximum=128),
                evidence_ids=refs,
            )
        )

    memory: list[MemoryItem] = []
    memory_ids: set[str] = set()
    for index, item in enumerate(_objects(result["memory"], "result.memory")):
        _keys(
            item,
            required={"memory_id", "text", "kind", "evidence_ids"},
            label=f"memory[{index}]",
        )
        memory_id = _text(item["memory_id"], "memory.memory_id", maximum=256)
        if memory_id in memory_ids:
            raise ProtocolError(f"duplicate memory_id: {memory_id}")
        memory_ids.add(memory_id)
        refs = _ids(item["evidence_ids"], "memory.evidence_ids")
        missing = set(refs) - evidence_ids
        if missing:
            raise ProtocolError(
                f"memory item {memory_id} references unknown evidence: {sorted(missing)}"
            )
        memory.append(
            MemoryItem(
                memory_id=memory_id,
                text=_text(item["text"], "memory.text"),
                kind=_text(item["kind"], "memory.kind", maximum=128),
                evidence_ids=refs,
            )
        )

    assurance_value = _mapping(result["assurance"], "result.assurance")
    _keys(
        assurance_value,
        required={"source_truth", "runtime_integrity", "license_mode"},
        label="result.assurance",
    )
    assurance = Assurance(
        source_truth=_text(
            assurance_value["source_truth"], "assurance.source_truth", maximum=128
        ),
        runtime_integrity=_text(
            assurance_value["runtime_integrity"], "assurance.runtime_integrity", maximum=128
        ),
        license_mode=_text(
            assurance_value["license_mode"], "assurance.license_mode", maximum=128
        ),
    )
    if assurance.source_truth != "NOT_ASSERTED":
        raise ProtocolError("runtime must report source_truth=NOT_ASSERTED")

    return ProcessResult(
        memory=tuple(memory),
        claims=tuple(claims),
        evidence=tuple(evidence),
        assurance=assurance,
        request_id=expected_request_id,
        runtime_version=runtime_version,
        engine=engine,
        raw=MappingProxyType(root),
    )
