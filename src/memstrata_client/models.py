"""Immutable public request and response values."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from memstrata_client.errors import ProtocolError

ALLOWED_ROLES = frozenset({"system", "user", "assistant", "tool"})
MAX_MESSAGES = 512
MAX_MESSAGE_CHARS = 1_000_000
MAX_TOTAL_MESSAGE_CHARS = 4_000_000
MAX_OPTIONS = 64


def _exact_keys(value: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ProtocolError(f"{label} has unknown fields: {sorted(unknown)}")


def _required_text(value: Any, label: str, *, maximum: int = MAX_MESSAGE_CHARS) -> str:
    if not isinstance(value, str) or not value:
        raise ProtocolError(f"{label} must be a non-empty string")
    if len(value) > maximum:
        raise ProtocolError(f"{label} exceeds {maximum} characters")
    return value


def _optional_text(value: Any, label: str, *, maximum: int = 4096) -> str | None:
    if value is None:
        return None
    return _required_text(value, label, maximum=maximum)


def _string_list(value: Any, label: str, *, maximum: int = 512) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ProtocolError(f"{label} must be a list with at most {maximum} entries")
    result: list[str] = []
    for index, item in enumerate(value):
        result.append(_required_text(item, f"{label}[{index}]", maximum=4096))
    if len(set(result)) != len(result):
        raise ProtocolError(f"{label} contains duplicate identifiers")
    return tuple(result)


@dataclass(frozen=True)
class Message:
    role: str
    content: str
    name: str | None = None

    @classmethod
    def from_value(cls, value: Message | Mapping[str, Any]) -> Message:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise ProtocolError("message must be a Message or mapping")
        _exact_keys(value, {"role", "content", "name"}, "message")
        role = value.get("role")
        if role not in ALLOWED_ROLES:
            raise ProtocolError(f"message.role must be one of {sorted(ALLOWED_ROLES)}")
        return cls(
            role=role,
            content=_required_text(value.get("content"), "message.content"),
            name=_optional_text(value.get("name"), "message.name", maximum=128),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name is not None:
            result["name"] = self.name
        return result


def normalize_messages(values: Sequence[Message | Mapping[str, Any]]) -> tuple[Message, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ProtocolError("messages must be a sequence")
    if not values or len(values) > MAX_MESSAGES:
        raise ProtocolError(f"messages must contain 1..{MAX_MESSAGES} entries")
    messages = tuple(Message.from_value(item) for item in values)
    if sum(len(item.content) for item in messages) > MAX_TOTAL_MESSAGE_CHARS:
        raise ProtocolError(f"total message content exceeds {MAX_TOTAL_MESSAGE_CHARS} characters")
    return messages


def normalize_options(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping) or len(value) > MAX_OPTIONS:
        raise ProtocolError(f"options must be a mapping with at most {MAX_OPTIONS} keys")
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key or len(key) > 128:
            raise ProtocolError("option keys must be non-empty strings <= 128 characters")
        if item is not None and not isinstance(item, (str, int, float, bool)):
            raise ProtocolError(f"option {key!r} must be a JSON scalar")
        normalized[key] = item
    return MappingProxyType(normalized)


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    kind: str
    content: str
    source: str | None = None


@dataclass(frozen=True)
class Claim:
    claim_id: str
    text: str
    status: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class MemoryItem:
    memory_id: str
    text: str
    kind: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class Assurance:
    source_truth: str
    runtime_integrity: str
    license_mode: str


@dataclass(frozen=True)
class ProcessResult:
    memory: tuple[MemoryItem, ...]
    claims: tuple[Claim, ...]
    evidence: tuple[Evidence, ...]
    assurance: Assurance
    request_id: str
    runtime_version: str
    engine: str
    raw: Mapping[str, Any] = field(repr=False)
