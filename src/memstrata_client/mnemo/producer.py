# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""MemStrata producer SDK: mnemo/v0 over HTTP, standard library only.

Buffer write intents, commit them as content-addressed envelopes to a MemStrata app
running on your computer, and keep the receipts. This module imports
``memstrata_mnemo.envelope`` (also standard-library only); vendor both files together.

What you can rely on
  * Every intent is validated and sanitized when you add it (the same rules as
    ``envelope.build_item``), so what is stored is what was checked here: trimmed text,
    removed control characters and redacted credential-shaped values. Redaction is a
    guardrail, not a secret scanner.
  * ``flush()`` freezes each envelope the first time it is built. After a failure, the
    next ``flush()`` re-sends the same bytes, which the server treats as a replay of
    that envelope, never a second application. New intents added in between go into new
    envelopes after the unsent ones.
  * The server's receipt carries the envelope ID; ``flush()`` fails loudly if it differs
    from the locally computed one.
  * One producer is safe to use from several threads: adding is locked and flushes are
    serialized. Items added while a flush is running go into the next flush.

What you must still do
  * The server commits an envelope even when some of its items fail. Read
    ``ack["items"]`` for per-item results (for example ``novel``, ``contradict``,
    ``duplicate``, ``stored`` or an error) and do not assume that a committed envelope
    means every item was applied. A replayed envelope returns the stored results.
  * ``verify_chain()`` reports what the server says about its own acknowledgement chain.
    It does not prove, from the client side, that nothing was removed from the end of
    the chain: keep each receipt's ``ack_hash`` and compare it with ``head`` and
    ``count``.

Minimal use::

    from memstrata_client.mnemo.producer import MemStrataProducer
    p = MemStrataProducer(project_id="my-repo", producer="mytool/1.0")
    p.assert_value("server port", "is", "9090")
    p.episode("deploy log: rolled restart complete", role="tool")
    acks = p.flush()
    assert p.verify_chain()["ok"]
"""

from __future__ import annotations

import http.client
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from memstrata_client.mnemo.envelope import (
    MAX_ITEMS_PER_ENVELOPE,
    SCHEMA_V0,
    MnemoTransportError,
    _checked_base_url,
    _open_request,
    _read_json_object,
    _require_text,
    build_envelope,
    build_item,
    canonical_json,
    envelope_id,
)

DEFAULT_BASE_URL = "http://127.0.0.1:9101"
_RETRIABLE_STATUS = frozenset({408, 429})


class IngestError(RuntimeError):
    """The daemon did not commit an envelope (feature off, rejected, unreachable, bad reply).

    ``response`` is the server's parsed body when there was one (it can echo submitted
    content: do not log it blindly). ``committed`` lists the receipts of envelopes that
    were committed earlier in the same ``flush()`` before this failure.
    """

    def __init__(
        self,
        message: str,
        response: dict | None = None,
        committed: list[dict] | None = None,
    ) -> None:
        super().__init__(message)
        self.response = response or {}
        self.committed = committed or []


class _HTTPStatus(Exception):
    """An HTTP error status with the server's parsed body (internal)."""

    def __init__(self, code: int, body: dict) -> None:
        super().__init__(f"HTTP {code}")
        self.code = code
        self.body = body


class MemStrataProducer:
    """Buffers write intents and commits them as mnemo/v0 envelopes.

    ``transport`` is injectable for tests and embedding: a callable
    ``(method, path, payload_or_None) -> dict``. The default speaks HTTP to ``base_url``
    (http or https only, no environment proxies, no redirects). ``timeout`` applies to
    each socket operation, not to the whole call.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        project_id: str = "default",
        *,
        producer: str = "memstrata-sdk-python/0.1",
        batch_size: int = MAX_ITEMS_PER_ENVELOPE,
        timeout: float = 30.0,
        retries: int = 2,
        transport: Callable[[str, str, dict | None], dict] | None = None,
    ) -> None:
        if not (1 <= batch_size <= MAX_ITEMS_PER_ENVELOPE):
            raise ValueError(f"batch_size must be 1..{MAX_ITEMS_PER_ENVELOPE}")
        if retries < 0:
            raise ValueError("retries must not be negative")
        self.base_url = _checked_base_url(base_url)
        self.project_id = _require_text(project_id, "project_id")
        self.producer = _require_text(producer, "producer")
        self.batch_size = batch_size
        self.timeout = timeout
        self.retries = retries
        self._transport = transport or self._http
        self._lock = threading.RLock()  # guards the buffers
        self._flush_lock = threading.Lock()  # serializes flushes
        self._items: list[dict] = []  # validated intents not yet in an envelope
        self._queued: list[tuple[dict, str]] = []  # frozen (payload, envelope_id), oldest first
        self._keys_used: set[str] = set()

    # -- buffering the four intent kinds ------------------------------------

    def _add(self, kind: str, **fields: Any) -> None:
        # Validated and sanitized now, so a bad intent fails at the call site.
        item = build_item({"kind": kind, **{k: v for k, v in fields.items() if v is not None}})
        with self._lock:
            self._items.append(item)

    def episode(self, text: str, *, role: str = "user", ts: str | None = None) -> None:
        """Raw turn or history text: append-only, no gating."""
        self._add("episode", text=text, role=role, ts=ts)

    def candidate(
        self,
        text: str,
        *,
        type: str | None = None,
        importance: int | None = None,
        valid_from: str | None = None,
        world: str | None = None,
        role: str | None = None,
        ts: str | None = None,
    ) -> None:
        """Free text for the engine to gate (dedupe, merge, supersede, write)."""
        self._add(
            "candidate",
            text=text,
            type=type,
            importance=importance,
            valid_from=valid_from,
            world=world,
            role=role,
            ts=ts,
        )

    def assert_value(
        self,
        subject: str,
        relation: str,
        object: str,
        *,
        text: str | None = None,
        importance: int | None = None,
        valid_from: str | None = None,
        world: str | None = None,
        unverified: bool | None = None,
        is_revert: bool | None = None,
        ts: str | None = None,
    ) -> None:
        """A pre-extracted (subject, relation, object) value for the server's
        deterministic supersession path."""
        self._add(
            "assertion",
            subject=subject,
            relation=relation,
            object=object,
            text=text,
            importance=importance,
            valid_from=valid_from,
            world=world,
            unverified=unverified,
            is_revert=is_revert,
            ts=ts,
        )

    def file_event(
        self,
        path: str,
        *,
        change_type: str | None = None,
        git_sha: str | None = None,
        symbols_mutated: list[str] | None = None,
        scope_precise: bool | None = None,
        ts: str | None = None,
    ) -> None:
        """An out-of-band source change."""
        self._add(
            "file_event",
            path=path,
            change_type=change_type,
            git_sha=git_sha,
            symbols_mutated=symbols_mutated,
            scope_precise=scope_precise,
            ts=ts,
        )

    # -- committing ---------------------------------------------------------

    def pending(self) -> int:
        """Intents not yet committed: buffered ones plus those in unsent envelopes."""
        with self._lock:
            return len(self._items) + sum(len(payload["items"]) for payload, _ in self._queued)

    def flush(self, *, idempotency_key: str | None = None) -> list[dict]:
        """Commit everything pending; returns one receipt per envelope committed.

        Unsent envelopes from an earlier failed flush go first, byte-identical. Raises
        ``IngestError`` if an envelope is not committed; the unsent envelopes stay queued
        for the next call and ``error.committed`` holds the receipts already obtained.

        ``idempotency_key`` is attached to the first envelope built by this call. Keys are
        fixed when an envelope is built: passing the key again to retry is harmless, but a
        key that this producer has already used cannot be attached to new data.
        """
        key = _require_text(idempotency_key, "idempotency_key") if idempotency_key else None
        with self._flush_lock:
            with self._lock:
                if self._items:
                    if key is not None and key in self._keys_used:
                        raise ValueError(
                            "idempotency_key was already used by this producer; use a new key "
                            "for new data"
                        )
                    items, self._items = self._items, []
                    for start in range(0, len(items), self.batch_size):
                        payload: dict[str, Any] = {
                            "schema": SCHEMA_V0,
                            "project_id": self.project_id,
                            "producer": self.producer,
                            "items": items[start : start + self.batch_size],
                        }
                        if key is not None and start == 0:
                            payload["idempotency_key"] = key
                        built = build_envelope(payload)
                        self._queued.append((built, envelope_id(built)))
                    if key is not None:
                        self._keys_used.add(key)
                queue = list(self._queued)
            acks: list[dict] = []
            for built, local_id in queue:
                try:
                    response = self._post_with_retry("/ingest/v0", built)
                    if response.get("status") != "committed":
                        raise IngestError(
                            f"ingest not committed: {response.get('status')} "
                            f"({response.get('reason', 'no reason')})",
                            response,
                        )
                    ack = response.get("ack")
                    if not isinstance(ack, dict) or ack.get("envelope_id") != local_id:
                        # Canonicalization drift between this client and the server
                        # contract: fail loudly, receipts depend on it.
                        raise IngestError(
                            f"envelope id mismatch: local {local_id[:12]} != "
                            f"server {str((ack or {}).get('envelope_id'))[:12]}",
                            response,
                        )
                except IngestError as exc:
                    exc.committed = list(acks)
                    raise
                with self._lock:
                    self._queued.pop(0)
                acks.append(ack)
            return acks

    # -- audit reads --------------------------------------------------------

    def verify_chain(self, project_id: str | None = None) -> dict:
        """The server's report on its acknowledgement chain: ``{'ok', 'count', 'head', ...}``.

        This is the server vouching for itself over HTTP; see the module docstring for what
        it does not prove.
        """
        pid = urllib.parse.quote(project_id or self.project_id, safe="")
        response = self._read("GET", f"/ingest/v0/chain?project_id={pid}")
        chain = response.get("chain")
        if response.get("status") != "ok" or not isinstance(chain, dict):
            raise IngestError(f"chain verify failed: {response.get('reason')}", response)
        return chain

    def get_ack(self, envelope_id_hex: str) -> dict | None:
        """Replay a stored receipt; ``None`` only when the server says it is not found."""
        if not isinstance(envelope_id_hex, str) or not re.fullmatch(
            r"[0-9a-f]{64}", envelope_id_hex
        ):
            raise ValueError("envelope_id_hex must be 64 lowercase hex characters")
        response = self._read("GET", f"/ingest/v0/envelope/{envelope_id_hex}")
        status = response.get("status")
        if status == "not_found":
            return None
        ack = response.get("ack")
        if status != "committed" or not isinstance(ack, dict):
            raise IngestError(f"receipt lookup failed: {response.get('reason', status)}", response)
        return ack

    # -- transport ----------------------------------------------------------

    def _read(self, method: str, path: str) -> dict:
        """One audit read: no retries, and every failure is an ``IngestError``."""
        try:
            return self._transport(method, path, None)
        except _HTTPStatus as exc:
            raise IngestError(f"ingest read failed: HTTP {exc.code}", exc.body) from exc
        except OSError as exc:
            raise IngestError(f"daemon unreachable: {exc}") from exc

    def _post_with_retry(self, path: str, payload: dict) -> dict:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                return self._transport("POST", path, payload)
            except _HTTPStatus as exc:
                if exc.code < 500 and exc.code not in _RETRIABLE_STATUS:
                    raise IngestError(
                        f"ingest rejected the envelope: HTTP {exc.code}", exc.body
                    ) from exc
                last = exc
            except OSError as exc:  # URLError, timeouts and connection errors
                last = exc
            if attempt < self.retries:
                time.sleep(min(2.0, 0.25 * (2**attempt)))
        raise IngestError(f"daemon unreachable after {self.retries + 1} attempts: {last}")

    def _http(self, method: str, path: str, payload: dict | None) -> dict:
        data = canonical_json(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"content-type": "application/json"} if data else {},
        )
        try:
            with _open_request(request, timeout=self.timeout) as response:
                return _read_producer_json(response)
        except urllib.error.HTTPError as exc:
            try:
                body = _read_json_object(exc)
            except MnemoTransportError:
                body = {}
            raise _HTTPStatus(exc.code, body) from exc
        except http.client.HTTPException as exc:
            raise urllib.error.URLError(str(exc)) from exc


def _read_producer_json(response) -> dict:
    try:
        return _read_json_object(response)
    except MnemoTransportError as exc:
        raise IngestError(str(exc)) from exc


__all__ = ["DEFAULT_BASE_URL", "IngestError", "MemStrataProducer"]
