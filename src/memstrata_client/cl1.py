# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""Scoped CL1 context and source client for a provisioned application.

The context path never invokes the built-in answer reader. Write methods need
a separate write-capable grant. Tenant and principal come from that grant,
never from a question or caller-supplied request body.
"""

from __future__ import annotations

import hashlib
import json
import re
import ssl

from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote, urlsplit

import httpx

Profile = Literal["standard_7k", "standard_8k", "deep_24k"]
_PROFILE_CEILINGS = {"standard_7k": 7000, "standard_8k": 8192, "deep_24k": 24000}


def _transport_options(base_url: str) -> dict[str, Any]:
    if base_url.startswith("http://"):
        # Only literal loopback HTTP is admitted. An empty TLS trust context
        # avoids eagerly loading OS certificates on this plaintext-only path.
        return {"verify": ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)}
    return {}


_EXPIRED_MESSAGE = "This connection expired. Open Connections and choose Renew."


def _authorization_expired(response: httpx.Response, detail: Any) -> bool:
    return response.status_code == 403 and (
        detail == "CL1 credential expired"
        or response.headers.get("X-MemStrata-Error-Code") == "authorization_expired"
    )


class CL1Error(RuntimeError):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        *,
        code: str | None = None,
        detail: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.detail = detail


_MAX_CONTEXT_BYTES = 8 * 1024 * 1024
_MAX_SOURCE_BYTES = 32 * 1024 * 1024
_TOO_LARGE = "The CL1 response exceeds the bounded envelope"


def _bounded_request(client, method, url, *, maximum, **kwargs) -> httpx.Response:
    """Send one request and read at most ``maximum`` response bytes (no redirects)."""
    with client.stream(method, url, follow_redirects=False, **kwargs) as response:
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > maximum:
            raise CL1Error(_TOO_LARGE)
        parts, total = [], 0
        for part in response.iter_bytes(65536):
            total += len(part)
            if total > maximum:
                raise CL1Error(_TOO_LARGE)
            parts.append(part)
        return httpx.Response(response.status_code, content=b"".join(parts))


async def _abounded_request(client, method, url, *, maximum, **kwargs) -> httpx.Response:
    async with client.stream(method, url, follow_redirects=False, **kwargs) as response:
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > maximum:
            raise CL1Error(_TOO_LARGE)
        parts, total = [], 0
        async for part in response.aiter_bytes(65536):
            total += len(part)
            if total > maximum:
                raise CL1Error(_TOO_LARGE)
            parts.append(part)
        return httpx.Response(response.status_code, content=b"".join(parts))


@dataclass(frozen=True)
class CL1Document:
    quote: str
    source_id: str
    revision: int
    session_index: int
    turn_index: int
    date: str
    role: str
    speaker: str
    start_byte: int
    end_byte: int
    packet_start_byte: int
    packet_end_byte: int
    source_sha256: str


@dataclass(frozen=True)
class CL1Context:
    assembled_context: str
    documents: tuple[CL1Document, ...]
    requested_profile: str
    effective_profile: str
    evidence_token_count: int
    evidence_token_ceiling: int
    tokenizer_id: str
    source_bindings: tuple[dict[str, Any], ...]
    baseline_policy_id: str
    retrieval_policy_version: str
    source_scope: str = "selected"
    library_sources_searchable: int | None = None
    candidate_source_count: int | None = None


def _parse(
    payload: Any,
    *,
    expected_project: str,
    expected_source_ids: tuple[str, ...],
    expected_profile: Profile,
    expected_source_scope: str = "selected",
) -> CL1Context:
    if (
        not isinstance(payload, dict)
        or payload.get("contract") != "memstrata/cl1-context/v1"
        or payload.get("status") != "ready"
        or payload.get("fallback_used") is not False
        or payload.get("source_validation_passed") is not True
        or payload.get("completion_status") != "complete"
        or payload.get("project_id") != expected_project
    ):
        raise CL1Error("The server did not return a complete CL1 context")
    if not isinstance(payload.get("assembled_context"), str) or not isinstance(
        payload.get("documents"), list
    ):
        raise CL1Error("The CL1 context response is incomplete")
    actual, ceiling = payload.get("evidence_token_count"), payload.get("evidence_token_ceiling")
    if (
        type(actual) is not int
        or type(ceiling) is not int
        or actual < 0
        or ceiling not in set(_PROFILE_CEILINGS.values())
        or actual > ceiling
    ):
        raise CL1Error("The CL1 evidence receipt violates its profile ceiling")
    effective = payload.get("effective_profile")
    if (
        effective not in _PROFILE_CEILINGS
        or payload.get("requested_profile") != expected_profile
        or effective != expected_profile
        or ceiling != _PROFILE_CEILINGS[effective]
        or payload.get("answer_correctness") != "NOT_MEASURED"
        or not isinstance(payload.get("tokenizer_id"), str)
        or not payload["tokenizer_id"]
    ):
        raise CL1Error("The CL1 evidence receipt has inconsistent profile metadata")
    try:
        documents = tuple(
            CL1Document(**{key: item[key] for key in CL1Document.__dataclass_fields__})
            for item in payload["documents"]
        )
        if any(
            type(item.session_index) is not int
            or item.session_index < 0
            or type(item.turn_index) is not int
            or item.turn_index < 0
            for item in documents
        ):
            raise CL1Error("A CL1 document has invalid session or turn locators")
        bindings = tuple(dict(item) for item in payload["source_bindings"])
        if not bindings or any(
            not isinstance(item.get("source_id"), str)
            or not item["source_id"]
            or type(item.get("revision")) is not int
            or item["revision"] < 1
            or not isinstance(item.get("source_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", item["source_sha256"])
            for item in bindings
        ):
            raise CL1Error("The CL1 source bindings are incomplete")
        scope = payload.get("source_scope", "selected")
        if scope != expected_source_scope:
            raise CL1Error("The CL1 source scope differs from the request")
        if scope == "selected" and tuple(item["source_id"] for item in bindings) != expected_source_ids:
            raise CL1Error("The CL1 source selection differs from the request")
        if scope == "all_ready":
            searchable = payload.get("library_sources_searchable")
            candidates = payload.get("candidate_source_count")
            if (type(searchable) is not int or type(candidates) is not int
                    or not 1 <= len(bindings) <= candidates <= searchable
                    or len({item["source_id"] for item in bindings}) != len(bindings)):
                raise CL1Error("The CL1 library source receipt is inconsistent")
        bound = {(item["source_id"], item["revision"], item["source_sha256"]) for item in bindings}
        if len(bound) != len(bindings) or any(
            (item.source_id, item.revision, item.source_sha256) not in bound for item in documents
        ):
            raise CL1Error("A CL1 document is outside the selected source revisions")
        if any(
            not isinstance(item.quote, str)
            or not item.quote
            or type(item.start_byte) is not int
            or type(item.end_byte) is not int
            or not 0 <= item.start_byte < item.end_byte
            or type(item.packet_start_byte) is not int
            or type(item.packet_end_byte) is not int
            or not 0 <= item.packet_start_byte < item.packet_end_byte
            for item in documents
        ):
            raise CL1Error("A CL1 document has invalid evidence offsets")
        return CL1Context(
            assembled_context=payload["assembled_context"],
            documents=documents,
            requested_profile=str(payload["requested_profile"]),
            effective_profile=str(payload["effective_profile"]),
            evidence_token_count=actual,
            evidence_token_ceiling=ceiling,
            tokenizer_id=str(payload["tokenizer_id"]),
            source_bindings=bindings,
            baseline_policy_id=str(payload["baseline_policy_id"]),
            retrieval_policy_version=str(payload["retrieval_policy_version"]),
            source_scope=scope,
            library_sources_searchable=payload.get("library_sources_searchable"),
            candidate_source_count=payload.get("candidate_source_count"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise CL1Error("The CL1 context response has missing source metadata") from exc


class CL1Client:
    def __init__(
        self,
        base_url: str,
        *,
        project_id: str,
        token: str,
        source_ids: list[str] | None = None,
        source_scope: Literal["selected", "all_ready"] = "selected",
        profile: Profile = "standard_8k",
        timeout: float = 120.0,
        client: httpx.Client | None = None,
        async_client: httpx.AsyncClient | None = None,
    ):
        url = urlsplit(base_url)
        if (
            url.scheme not in {"http", "https"}
            or not url.hostname
            or url.username
            or url.password
            or "?" in base_url
            or "#" in base_url
        ):
            raise ValueError("A plain HTTP(S) CL1 server URL is required")
        if url.scheme == "http" and url.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Remote CL1 credentials require HTTPS")
        if not isinstance(project_id, str) or not project_id.strip():
            raise ValueError("A project is required")
        if not isinstance(token, str) or not token.startswith("cl1_") or len(token) > 128:
            raise ValueError("A scoped CL1 token is required")
        selected = [] if source_ids is None else source_ids
        if (
            not isinstance(selected, list)
            or len(selected) > 128
            or any(not isinstance(item, str) or not item for item in selected)
            or len(set(selected)) != len(selected)
        ):
            raise ValueError("Explicit distinct source IDs are required")
        if profile not in _PROFILE_CEILINGS:
            raise ValueError("Unknown CL1 profile")
        if source_scope not in {"selected", "all_ready"} or (source_scope == "all_ready" and selected):
            raise ValueError("Choose explicit source IDs or all_ready, not both")
        self.base_url = base_url.rstrip("/")
        self.project_id = project_id
        self._token = token
        self.source_ids = tuple(selected)
        self.source_scope = source_scope
        self.profile = profile
        self.timeout = timeout
        self._client = client
        self._async_client = async_client

    def __repr__(self) -> str:
        return (
            f"CL1Client(project_id={self.project_id!r}, profile={self.profile!r}, token=<redacted>)"
        )

    def with_sources(self, source_ids: list[str]) -> CL1Client:
        """Bind an explicit selection after scoped source discovery."""
        if not source_ids:
            raise ValueError("Select at least one CL1 source")
        return CL1Client(
            self.base_url,
            project_id=self.project_id,
            token=self._token,
            source_ids=source_ids,
            profile=self.profile,
            timeout=self.timeout,
            client=self._client,
            async_client=self._async_client,
        )

    def _request(self, question: str, date: str | None, profile: Profile | None) -> dict[str, Any]:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("A nonblank question is required")
        if self.source_scope == "selected" and not self.source_ids:
            raise ValueError("Select explicit CL1 source IDs before retrieval")
        selected = self.profile if profile is None else profile
        if selected not in _PROFILE_CEILINGS:
            raise ValueError("Unknown CL1 profile")
        body = {
            "project_id": self.project_id,
            "source_ids": list(self.source_ids),
            "question": question,
            "date": date,
            "profile": selected,
        }
        if self.source_scope == "all_ready":
            body.pop("source_ids")
            body["source_scope"] = "all_ready"
        return body

    def _headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer " + self._token}

    @staticmethod
    def _result(
        response: httpx.Response,
        *,
        project_id: str,
        source_ids: tuple[str, ...],
        profile: Profile,
        source_scope: str = "selected",
    ) -> CL1Context:
        if response.status_code != 200:
            try:
                error = response.json()
                detail = error.get("detail") if isinstance(error, dict) else None
            except (ValueError, TypeError, RecursionError):
                detail = None
            if _authorization_expired(response, detail):
                raise CL1Error(_EXPIRED_MESSAGE, 403, code="authorization_expired")
            if isinstance(detail, dict) and detail.get("code") in {
                "baseline_over_profile_ceiling",
                "reader_context_too_small",
            }:
                code = str(detail["code"])
                message = (
                    "CL1 evidence exceeds the selected profile"
                    if code == "baseline_over_profile_ceiling"
                    else "The selected reader cannot hold the requested CL1 context"
                )
                raise CL1Error(
                    message,
                    response.status_code,
                    code=code,
                    detail=detail,
                )
            raise CL1Error(
                "CL1 retrieval failed; inspect the server's scoped error receipt",
                response.status_code,
            )
        try:
            return _parse(
                response.json(),
                expected_project=project_id,
                expected_source_ids=source_ids,
                expected_profile=profile,
                expected_source_scope=source_scope,
            )
        except (ValueError, TypeError, RecursionError) as exc:
            raise CL1Error("The server returned invalid CL1 JSON") from exc

    def context(
        self, question: str, *, date: str | None = None, profile: Profile | None = None
    ) -> CL1Context:
        body = self._request(question, date, profile)
        try:
            if self._client is not None:
                response = _bounded_request(
                    self._client, "POST", self.base_url + "/context/cl1/v1",
                    maximum=_MAX_CONTEXT_BYTES, json=body, headers=self._headers(),
                )
            else:
                with httpx.Client(timeout=self.timeout, trust_env=False, **_transport_options(self.base_url)) as client:
                    response = _bounded_request(
                        client, "POST", self.base_url + "/context/cl1/v1",
                        maximum=_MAX_CONTEXT_BYTES, json=body, headers=self._headers(),
                    )
        except httpx.HTTPError as exc:
            raise CL1Error("CL1 retrieval service is unavailable") from exc
        return self._result(
            response,
            project_id=self.project_id,
            source_ids=self.source_ids,
            profile=body["profile"],
            source_scope=self.source_scope,
        )

    async def acontext(
        self, question: str, *, date: str | None = None, profile: Profile | None = None
    ) -> CL1Context:
        body = self._request(question, date, profile)
        try:
            if self._async_client is not None:
                response = await _abounded_request(
                    self._async_client, "POST", self.base_url + "/context/cl1/v1",
                    maximum=_MAX_CONTEXT_BYTES, json=body, headers=self._headers(),
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout, trust_env=False, **_transport_options(self.base_url)) as client:
                    response = await _abounded_request(
                        client, "POST", self.base_url + "/context/cl1/v1",
                        maximum=_MAX_CONTEXT_BYTES, json=body, headers=self._headers(),
                    )
        except httpx.HTTPError as exc:
            raise CL1Error("CL1 retrieval service is unavailable") from exc
        return self._result(
            response,
            project_id=self.project_id,
            source_ids=self.source_ids,
            profile=body["profile"],
            source_scope=self.source_scope,
        )

    @staticmethod
    def _source_path(source_id: str) -> str:
        if (
            not isinstance(source_id, str)
            or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", source_id)
            or source_id in {".", ".."}
        ):
            raise ValueError("A stable CL1 source ID is required")
        return "/sources/cl1/v1/" + quote(source_id, safe="")

    @staticmethod
    def _listed(payload: dict[str, Any], *, expected_project: str) -> dict[str, Any]:
        if (
            payload.get("contract") != "memstrata/cl1-source-list/v1"
            or payload.get("project_id") != expected_project
            or "next_cursor" not in payload
            or not isinstance(payload.get("sources"), list)
            or len(payload["sources"]) > 100
            or any(
                not isinstance(row, dict)
                or not isinstance(row.get("source_id"), str)
                or not row["source_id"]
                or len(row["source_id"]) > 256
                or type(row.get("revision")) is not int
                or row["revision"] < 1
                or not isinstance(row.get("source_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", row["source_sha256"])
                for row in payload["sources"]
            )
            or (
                payload.get("next_cursor") is not None
                and (
                    not isinstance(payload["next_cursor"], str) or len(payload["next_cursor"]) > 256
                )
            )
        ):
            raise CL1Error("The scoped CL1 source list is invalid")
        ids = [row["source_id"] for row in payload["sources"]]
        if ids != sorted(set(ids)) or (payload["next_cursor"] is not None and not ids):
            raise CL1Error("The scoped CL1 source list is not ordered")
        return payload

    def list_sources(self, *, cursor: str = "", limit: int = 100) -> dict[str, Any]:
        return self._listed(
            self._source_call(
                "GET",
                "/sources/cl1/v1",
                params={"project_id": self.project_id, "cursor": cursor, "limit": limit},
            ),
            expected_project=self.project_id,
        )

    async def alist_sources(self, *, cursor: str = "", limit: int = 100) -> dict[str, Any]:
        return self._listed(
            await self._asource_call(
                "GET",
                "/sources/cl1/v1",
                params={"project_id": self.project_id, "cursor": cursor, "limit": limit},
            ),
            expected_project=self.project_id,
        )

    @staticmethod
    def _source_response(response: httpx.Response, *, expected_status: int = 200) -> dict[str, Any]:
        if response.status_code != expected_status:
            if response.status_code == 403:
                try:
                    payload = response.json()
                except ValueError:
                    payload = None
                detail = payload.get("detail") if isinstance(payload, dict) else None
                if _authorization_expired(response, detail):
                    raise CL1Error(_EXPIRED_MESSAGE, 403, code="authorization_expired")
            raise CL1Error("Scoped CL1 source operation failed", response.status_code)
        try:
            payload = response.json()
        except (ValueError, TypeError, RecursionError) as exc:
            raise CL1Error("The server returned invalid CL1 source JSON") from exc
        if not isinstance(payload, dict):
            raise CL1Error("The CL1 source response is invalid")
        return payload

    def _source_call(
        self,
        method: str,
        path: str,
        *,
        body: dict | None = None,
        params: dict | None = None,
        expected_status: int = 200,
    ) -> dict[str, Any]:
        try:
            if self._client is not None:
                response = _bounded_request(
                    self._client, method, self.base_url + path, maximum=_MAX_SOURCE_BYTES,
                    json=body, params=params, headers=self._headers(),
                )
            else:
                with httpx.Client(timeout=self.timeout, trust_env=False, **_transport_options(self.base_url)) as client:
                    response = _bounded_request(
                        client, method, self.base_url + path, maximum=_MAX_SOURCE_BYTES,
                        json=body, params=params, headers=self._headers(),
                    )
        except httpx.HTTPError as exc:
            raise CL1Error("CL1 source service is unavailable") from exc
        return self._source_response(response, expected_status=expected_status)

    async def _asource_call(
        self,
        method: str,
        path: str,
        *,
        body: dict | None = None,
        params: dict | None = None,
        expected_status: int = 200,
    ) -> dict[str, Any]:
        try:
            if self._async_client is not None:
                response = await _abounded_request(
                    self._async_client, method, self.base_url + path, maximum=_MAX_SOURCE_BYTES,
                    json=body, params=params, headers=self._headers(),
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout, trust_env=False, **_transport_options(self.base_url)) as client:
                    response = await _abounded_request(
                        client, method, self.base_url + path, maximum=_MAX_SOURCE_BYTES,
                        json=body, params=params, headers=self._headers(),
                    )
        except httpx.HTTPError as exc:
            raise CL1Error("CL1 source service is unavailable") from exc
        return self._source_response(response, expected_status=expected_status)

    def ingest_document(
        self, source_id: str, filename: str, text: str, *, expected_revision: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._source_path(source_id)
        return self._source_call(
            "POST",
            "/sources/cl1/v1",
            body={
                "project_id": self.project_id,
                "source_id": source_id,
                "kind": "document",
                "filename": filename,
                "text": text,
                "expected_revision": expected_revision,
                **({"metadata": self._document_metadata(metadata)} if metadata is not None else {}),
            },
        )

    async def aingest_document(
        self, source_id: str, filename: str, text: str, *, expected_revision: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._source_path(source_id)
        return await self._asource_call(
            "POST",
            "/sources/cl1/v1",
            body={
                "project_id": self.project_id,
                "source_id": source_id,
                "kind": "document",
                "filename": filename,
                "text": text,
                "expected_revision": expected_revision,
                **({"metadata": self._document_metadata(metadata)} if metadata is not None else {}),
            },
        )

    @staticmethod
    def _document_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(metadata, dict):
            raise ValueError("Source metadata must be a JSON object")
        try:
            raw = json.dumps(metadata, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, UnicodeError) as exc:
            raise ValueError("Finite UTF-8 JSON metadata required") from exc
        if len(raw) > 65536:
            raise ValueError("Source metadata exceeds 64 KiB")
        return metadata

    def ingest_conversations(
        self,
        source_id: str,
        conversations: list[dict[str, Any]],
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        self._source_path(source_id)
        return self._source_call(
            "POST",
            "/sources/cl1/v1",
            body={
                "project_id": self.project_id,
                "source_id": source_id,
                "kind": "conversation",
                "conversations": conversations,
                "expected_revision": expected_revision,
            },
        )

    async def aingest_conversations(
        self,
        source_id: str,
        conversations: list[dict[str, Any]],
        *,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        self._source_path(source_id)
        return await self._asource_call(
            "POST",
            "/sources/cl1/v1",
            body={
                "project_id": self.project_id,
                "source_id": source_id,
                "kind": "conversation",
                "conversations": conversations,
                "expected_revision": expected_revision,
            },
        )

    def remove_source(self, source_id: str, *, expected_revision: int) -> dict[str, Any]:
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("Exact positive source revision required for removal")
        return self._source_call(
            "DELETE",
            self._source_path(source_id),
            body={"project_id": self.project_id, "expected_revision": expected_revision},
        )

    async def aremove_source(self, source_id: str, *, expected_revision: int) -> dict[str, Any]:
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("Exact positive source revision required for removal")
        return await self._asource_call(
            "DELETE",
            self._source_path(source_id),
            body={"project_id": self.project_id, "expected_revision": expected_revision},
        )

    def fetch_source(self, source_id: str, *, revision: int | None = None) -> dict[str, Any]:
        """Fetch and verify a currently authorized source; never a historical snapshot."""
        path = self._source_path(source_id)
        if source_id in {".", ".."}:
            raise ValueError("A stable CL1 source ID is required")
        if revision is not None:
            self._revision(revision, allow_create=False)
        params: dict[str, Any] = {"project_id": self.project_id}
        if revision is not None:
            params["revision"] = revision
        payload = self._source_call("GET", path, params=params)
        if (
            payload.get("contract") != "memstrata/cl1-source/v1"
            or payload.get("project_id") != self.project_id
            or payload.get("source_id") != source_id
            or type(payload.get("revision")) is not int
            or payload["revision"] < 1
            or (revision is not None and payload["revision"] != revision)
            or payload.get("offset_basis") != "turn_utf8"
            or payload.get("canonicalization") != "cl1-normalized-sessions/v1"
            or not isinstance(payload.get("sessions"), list)
            or not isinstance(payload.get("metadata"), dict)
        ):
            raise CL1Error("The fetched CL1 source binding is invalid")
        try:
            canonical = json.dumps(
                {"sessions": payload["sessions"]}, ensure_ascii=False,
                sort_keys=True, separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeError) as exc:
            raise CL1Error("The fetched CL1 source snapshot is invalid") from exc
        if hashlib.sha256(canonical).hexdigest() != payload.get("source_sha256"):
            raise CL1Error("The fetched CL1 source hash does not match its canonical snapshot")
        return payload

    async def afetch_source(self, source_id: str, *, revision: int | None = None) -> dict[str, Any]:
        """Fetch and verify a currently authorized source; never a historical snapshot."""
        path = self._source_path(source_id)
        if source_id in {".", ".."}:
            raise ValueError("A stable CL1 source ID is required")
        if revision is not None:
            self._revision(revision, allow_create=False)
        params: dict[str, Any] = {"project_id": self.project_id}
        if revision is not None:
            params["revision"] = revision
        payload = await self._asource_call("GET", path, params=params)
        if (
            payload.get("contract") != "memstrata/cl1-source/v1"
            or payload.get("project_id") != self.project_id
            or payload.get("source_id") != source_id
            or type(payload.get("revision")) is not int
            or payload["revision"] < 1
            or (revision is not None and payload["revision"] != revision)
            or payload.get("offset_basis") != "turn_utf8"
            or payload.get("canonicalization") != "cl1-normalized-sessions/v1"
            or not isinstance(payload.get("sessions"), list)
            or not isinstance(payload.get("metadata"), dict)
        ):
            raise CL1Error("The fetched CL1 source binding is invalid")
        try:
            canonical = json.dumps(
                {"sessions": payload["sessions"]}, ensure_ascii=False,
                sort_keys=True, separators=(",", ":"), allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError, UnicodeError) as exc:
            raise CL1Error("The fetched CL1 source snapshot is invalid") from exc
        if hashlib.sha256(canonical).hexdigest() != payload.get("source_sha256"):
            raise CL1Error("The fetched CL1 source hash does not match its canonical snapshot")
        return payload

    def source_status(self, source_id: str) -> dict[str, Any]:
        return self._source_call(
            "GET", self._source_path(source_id) + "/status", params={"project_id": self.project_id}
        )

    async def asource_status(self, source_id: str) -> dict[str, Any]:
        return await self._asource_call(
            "GET", self._source_path(source_id) + "/status", params={"project_id": self.project_id}
        )

    def backfill_source(self, source_id: str, *, batch_size: int = 32) -> dict[str, Any]:
        return self._source_call(
            "POST",
            self._source_path(source_id) + "/backfill",
            body={"project_id": self.project_id, "batch_size": batch_size},
        )

    async def abackfill_source(self, source_id: str, *, batch_size: int = 32) -> dict[str, Any]:
        return await self._asource_call(
            "POST",
            self._source_path(source_id) + "/backfill",
            body={"project_id": self.project_id, "batch_size": batch_size},
        )

    @staticmethod
    def _revision(expected_revision: int | None, *, allow_create: bool = True) -> None:
        if (expected_revision is None and not allow_create) or (
            expected_revision is not None
            and (
                type(expected_revision) is not int or expected_revision < (0 if allow_create else 1)
            )
        ):
            raise ValueError("A nonnegative exact source revision is required")
