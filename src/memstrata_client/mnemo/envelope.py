# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""Zero-dependency mnemo/v0 envelope builder and local-HTTP client.

This module is intentionally small enough to vendor. It implements the client side
of the mnemo/v0 ingest contract: the server remains the authority that validates
and commits an envelope.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA_V0 = "mnemo/v0"
MAX_ITEMS_PER_ENVELOPE = 256
MAX_TEXT = 32_768

_KINDS = frozenset(("episode", "candidate", "assertion", "file_event"))
_ENVELOPE_FIELDS = frozenset(
    ("schema", "project_id", "producer", "sent_at", "idempotency_key", "items")
)
_ITEM_FIELDS = frozenset(
    (
        "kind",
        "text",
        "role",
        "ts",
        "type",
        "importance",
        "valid_from",
        "world",
        "unverified",
        "is_revert",
        "subject",
        "relation",
        "object",
        "path",
        "change_type",
        "git_sha",
        "symbols_mutated",
        "scope_precise",
    )
)
_ITEM_DEFAULTS: dict[str, Any] = {
    "type": "mutable_fact",
    "importance": 5,
    "valid_from": "",
    "world": "main",
    "unverified": False,
    "is_revert": False,
    "change_type": "modified",
    "symbols_mutated": [],
    "scope_precise": False,
}

# Defense in depth, not a claim that regular expressions can identify every
# secret. The client has no credential fields and never reads environment vars.
# ASCII word boundaries, so a key next to non-ASCII letters is still redacted and
# the Python and JavaScript clients agree.
_SECRET_PATTERNS = (
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b", re.ASCII),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,255}\b", re.ASCII),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,255}\b", re.ASCII),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b", re.ASCII),
)

# Text specification shared with js/mnemo.js (see test_vectors/sanitize_v1.json):
# 1. reject unpaired surrogates; 2. remove C0 controls except tab, LF and CR, DEL and
# the C1 controls; 3. CRLF and CR become LF; 4. redact credential-shaped values;
# 5. NFC; 6. trim the explicit set below. Controls go first and NFC last, so the
# function is idempotent.
_CONTROLS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_SURROGATES = re.compile("[\ud800-\udfff]")
_TRIM = (
    "\t\n \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009"
    "\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Never follow a redirect: a producer talks to exactly the URL it was given."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


def _open_request(request: urllib.request.Request, *, timeout: float):
    # Configure TLS only for HTTPS requests. Local HTTP must not load the host
    # certificate store, and neither transport uses environment proxies or redirects.
    if request.type == "http":
        opener = urllib.request.OpenerDirector()
        for handler in (
            urllib.request.HTTPHandler(),
            urllib.request.HTTPDefaultErrorHandler(),
            _NoRedirect(),
            urllib.request.HTTPErrorProcessor(),
        ):
            opener.add_handler(handler)
    else:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    return opener.open(request, timeout=timeout)


_MAX_RESPONSE_BYTES = 8 * 1024 * 1024


def _checked_base_url(base_url: str) -> str:
    """Validate a plain http(s) URL and rebuild it from its parsed parts."""
    if (
        not isinstance(base_url, str)
        or any(ord(char) <= 32 or ord(char) == 127 for char in base_url)
        or "?" in base_url
        or "#" in base_url
        or "\\" in base_url
    ):
        raise MnemoValidationError("base_url must be a plain http(s) URL without credentials")
    try:
        parts = urllib.parse.urlsplit(base_url)
        parts.port  # noqa: B018 -- raises ValueError for a malformed port
    except ValueError as exc:
        raise MnemoValidationError("base_url must be a plain http(s) URL") from exc
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username
        or parts.password
    ):
        raise MnemoValidationError("base_url must be a plain http(s) URL without credentials")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def _read_json_object(response) -> dict:
    """Read a bounded response body and return it as a JSON object."""
    data = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(data) > _MAX_RESPONSE_BYTES:
        raise MnemoTransportError("ingest response exceeds the bounded envelope")
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise MnemoTransportError("ingest response is not valid JSON") from exc
    if not isinstance(value, dict):
        raise MnemoTransportError("ingest response is not a JSON object")
    return value


class MnemoValidationError(ValueError):
    """The producer supplied data that is outside the mnemo/v0 contract."""


class MnemoTransportError(RuntimeError):
    """The local daemon did not return a committed receipt for an envelope."""

    def __init__(self, message: str, response: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.response = dict(response or {})


def sanitize_text(value: str, *, field: str = "text") -> str:
    """Normalize a string before it enters a content-addressed envelope.

    Controls are removed, line endings become LF, common credential-shaped values are
    redacted, and the result is NFC-normalized and trimmed (see the specification above
    the secret patterns). The function is idempotent. NFC results depend on the Unicode
    version of the runtime: newly encoded characters can compose differently on an older
    or newer interpreter, so envelope IDs for such text can differ between runtimes.
    Callers still must use a data allowlist: this is a guardrail, not a secret scanner.
    """
    if not isinstance(value, str):
        raise MnemoValidationError(f"{field} must be a string")
    if _SURROGATES.search(value):
        raise MnemoValidationError(f"{field} must not contain unpaired surrogates")
    cleaned = _CONTROLS.sub("", value).replace("\r\n", "\n").replace("\r", "\n")
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub("[REDACTED]", cleaned)
    return unicodedata.normalize("NFC", cleaned).strip(_TRIM)


def _require_text(value: Any, field: str) -> str:
    result = sanitize_text(value, field=field)
    if not result:
        raise MnemoValidationError(f"{field} must be non-empty")
    return result


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    result = sanitize_text(value, field=field)
    return result or None


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MnemoValidationError(f"{field} must be an object")
    return value


def _forbid_unknown(value: Mapping[str, Any], allowed: frozenset[str], field: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise MnemoValidationError(f"{field} has unknown field(s): {', '.join(unknown)}")


def build_item(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Build one strict, fully-defaulted mnemo/v0 item."""
    raw = _require_mapping(raw, "item")
    _forbid_unknown(raw, _ITEM_FIELDS, "item")
    kind = raw.get("kind")
    if kind not in _KINDS:
        raise MnemoValidationError("item.kind must be episode, candidate, assertion, or file_event")

    item: dict[str, Any] = {"kind": kind, **_ITEM_DEFAULTS, "symbols_mutated": []}
    for field in (
        "text",
        "role",
        "ts",
        "type",
        "valid_from",
        "world",
        "subject",
        "relation",
        "object",
        "path",
        "change_type",
        "git_sha",
    ):
        if field in raw:
            value = _optional_text(raw[field], field)
            if value is not None:
                item[field] = value

    if "importance" in raw:
        importance = raw["importance"]
        if (
            isinstance(importance, bool)
            or not isinstance(importance, int)
            or not 1 <= importance <= 10
        ):
            raise MnemoValidationError("item.importance must be an integer from 1 through 10")
        item["importance"] = importance
    for field in ("unverified", "is_revert", "scope_precise"):
        if field in raw:
            if not isinstance(raw[field], bool):
                raise MnemoValidationError(f"item.{field} must be a boolean")
            item[field] = raw[field]
    if "symbols_mutated" in raw:
        symbols = raw["symbols_mutated"]
        if isinstance(symbols, (str, bytes)) or not isinstance(symbols, Sequence):
            raise MnemoValidationError("item.symbols_mutated must be an array of strings")
        item["symbols_mutated"] = [_require_text(symbol, "symbols_mutated[]") for symbol in symbols]

    if item.get("text") is not None and len(item["text"]) > MAX_TEXT:
        raise MnemoValidationError(f"item.text must be at most {MAX_TEXT} characters")
    if kind in ("episode", "candidate") and not item.get("text"):
        raise MnemoValidationError(f"{kind} item requires non-empty text")
    if kind == "assertion":
        for field in ("subject", "relation", "object"):
            if not item.get(field):
                raise MnemoValidationError(f"assertion item requires non-empty {field}")
    if kind == "file_event" and not item.get("path"):
        raise MnemoValidationError("file_event item requires non-empty path")
    return item


def build_envelope(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Sanitize and validate an envelope into its canonical wire shape."""
    raw = _require_mapping(raw, "envelope")
    _forbid_unknown(raw, _ENVELOPE_FIELDS, "envelope")
    schema = raw.get("schema", SCHEMA_V0)
    if schema != SCHEMA_V0:
        raise MnemoValidationError(f"envelope.schema must be {SCHEMA_V0!r}")
    project_id = _require_text(raw.get("project_id"), "project_id")
    producer = _require_text(raw.get("producer", "unknown"), "producer")
    items = raw.get("items")
    if isinstance(items, (str, bytes)) or not isinstance(items, Sequence):
        raise MnemoValidationError("envelope.items must be an array")
    if not 1 <= len(items) <= MAX_ITEMS_PER_ENVELOPE:
        raise MnemoValidationError(f"envelope.items must contain 1..{MAX_ITEMS_PER_ENVELOPE} items")
    envelope: dict[str, Any] = {
        "schema": SCHEMA_V0,
        "project_id": project_id,
        "producer": producer,
        "items": [build_item(_require_mapping(item, "item")) for item in items],
    }
    for field in ("sent_at", "idempotency_key"):
        if field in raw:
            value = _optional_text(raw[field], field)
            if value is not None:
                envelope[field] = value
    return envelope


def episode(text: str, *, role: str | None = None, ts: str | None = None) -> dict[str, Any]:
    return build_item({"kind": "episode", "text": text, "role": role, "ts": ts})


def candidate(text: str, **fields: Any) -> dict[str, Any]:
    return build_item({"kind": "candidate", "text": text, **fields})


def assertion(subject: str, relation: str, object: str, **fields: Any) -> dict[str, Any]:
    return build_item(
        {"kind": "assertion", "subject": subject, "relation": relation, "object": object, **fields}
    )


def state_assertion(
    entity: str,
    aspect: str,
    value: str,
    *,
    valid_from: str = "",
    observed_at: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Format one external state transition as a bitemporal assertion.

    ``valid_from`` is the source's real-world valid time. ``observed_at`` maps
    to the production ``ts`` field; server receipt time remains transaction
    time and is deliberately not producer-controlled.
    """
    return assertion(entity, aspect, value, valid_from=valid_from, ts=observed_at, **fields)


def envelope(
    project_id: str,
    items: Sequence[Mapping[str, Any]],
    *,
    producer: str = "unknown",
    sent_at: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    return build_envelope(
        {
            "schema": SCHEMA_V0,
            "project_id": project_id,
            "producer": producer,
            "sent_at": sent_at,
            "idempotency_key": idempotency_key,
            "items": list(items),
        }
    )


def canonical_json(raw: Mapping[str, Any]) -> str:
    """Exact mnemo/v0 content-addressed representation."""
    return json.dumps(
        build_envelope(raw), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def envelope_id(raw: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(raw).encode("utf-8")).hexdigest()


def post_envelope(
    base_url: str, raw: Mapping[str, Any], *, timeout: float = 30.0
) -> dict[str, Any]:
    """POST one envelope to a local MemStrata daemon and verify its receipt ID.

    The ``timeout`` applies to each socket operation, not to the whole call. On a refusal,
    ``MnemoTransportError.response`` holds the server's body, which can echo submitted
    content: do not log it blindly.
    """
    payload = build_envelope(raw)
    body = canonical_json(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{_checked_base_url(base_url)}/ingest/v0",
        data=body,
        method="POST",
        headers={"content-type": "application/json"},
    )
    try:
        with _open_request(request, timeout=timeout) as response:
            result = _read_json_object(response)
    except urllib.error.HTTPError as exc:
        try:
            detail = _read_json_object(exc)
        except MnemoTransportError:
            detail = {}
        raise MnemoTransportError(f"ingest HTTP {exc.code}", detail) from exc
    except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
        raise MnemoTransportError(f"ingest transport failed: {exc}") from exc
    if result.get("status") != "committed":
        raise MnemoTransportError("ingest did not commit the envelope", result)
    ack = result.get("ack")
    if not isinstance(ack, dict) or ack.get("envelope_id") != envelope_id(payload):
        raise MnemoTransportError(
            "ingest receipt envelope_id does not match local canonical payload", result
        )
    return result


__all__ = [
    "MAX_ITEMS_PER_ENVELOPE",
    "MAX_TEXT",
    "SCHEMA_V0",
    "MnemoTransportError",
    "MnemoValidationError",
    "assertion",
    "build_envelope",
    "build_item",
    "candidate",
    "canonical_json",
    "envelope",
    "envelope_id",
    "episode",
    "post_envelope",
    "sanitize_text",
    "state_assertion",
]
