# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""Opt-in LangChain retriever over the scoped CL1 evidence API.

Each returned Document is one verified selected source span. This does not
replace the existing Memory.search or claim a fabricated similarity score.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

try:
    from langchain_core.callbacks import (
        AsyncCallbackManagerForRetrieverRun,
        CallbackManagerForRetrieverRun,
    )
    from langchain_core.documents import Document
    from langchain_core.retrievers import BaseRetriever
    from langchain_core.vectorstores import VectorStore
    from pydantic import ConfigDict, Field
except ImportError as exc:
    raise ImportError(
        "CL1 LangChain support is optional. Install with "
        '`pip install "memstrata-client[langchain]"`.'
    ) from exc

from memstrata_client.cl1 import CL1Client, CL1Context, CL1Error


class CL1Retriever(BaseRetriever):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    client: CL1Client = Field(exclude=True, repr=False)

    @staticmethod
    def _documents(result: CL1Context) -> list[Document]:
        return [
            Document(
                id=(
                    f"{item.source_id}@{item.revision}:s{item.session_index}:"
                    f"t{item.turn_index}:{item.start_byte}-{item.end_byte}"
                ),
                page_content=item.quote,
                metadata={
                    "source_id": item.source_id,
                    "source_revision": item.revision,
                    "session_index": item.session_index,
                    "turn_index": item.turn_index,
                    "source_sha256": item.source_sha256,
                    "date": item.date,
                    "role": item.role,
                    "speaker": item.speaker,
                    "start_byte": item.start_byte,
                    "end_byte": item.end_byte,
                    "packet_start_byte": item.packet_start_byte,
                    "packet_end_byte": item.packet_end_byte,
                    "evidence_profile": result.effective_profile,
                    "evidence_tokens": result.evidence_token_count,
                    "baseline_policy_id": result.baseline_policy_id,
                    "retrieval_policy_version": result.retrieval_policy_version,
                    "answer_correctness": "NOT_MEASURED",
                },
            )
            for item in result.documents
        ]

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        del run_manager
        return self._documents(self.client.context(query))

    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: AsyncCallbackManagerForRetrieverRun,
    ) -> list[Document]:
        del run_manager
        return self._documents(await self.client.acontext(query))


def create_cl1_retriever(client: CL1Client, **kwargs: Any) -> CL1Retriever:
    return CL1Retriever(client=client, **kwargs)


class CL1BatchError(CL1Error):
    """A nontransactional lifecycle batch stopped; prior receipts stay explicit."""

    def __init__(
        self, operation: str, completed: list[dict[str, Any]], failed_id: str, cause: Exception
    ):
        super().__init__(
            f"CL1 {operation} batch stopped at source {failed_id!r}",
            getattr(cause, "status_code", None),
            code=getattr(cause, "code", None),
            detail=getattr(cause, "detail", None),
        )
        self.completed = completed
        self.failed_id = failed_id


class CL1DocumentStore(VectorStore):
    """Pinned text lifecycle subset with CAS writes and CL1-ordered evidence.

    This does not store arbitrary embeddings or return vector similarity scores.
    Writes are committed source writes; indexing/search readiness is separate.
    """

    def __init__(self, client: CL1Client):
        self.client = client
        self.write_receipts: list[dict[str, Any]] = []

    @staticmethod
    def _ids(ids: list[str] | None, count: int | None = None) -> list[str]:
        if ids is None or not isinstance(ids, list) or (count is not None and len(ids) != count):
            raise ValueError("Explicit stable document IDs are required")
        for source_id in ids:
            CL1Client._source_path(source_id)
            if source_id in {".", ".."}:
                raise ValueError("A stable document ID is required")
        if len(set(ids)) != len(ids):
            raise ValueError("Document IDs must be distinct in a lifecycle batch")
        return ids

    @staticmethod
    def _options(kwargs: dict[str, Any], allowed: set[str]) -> None:
        unknown = set(kwargs) - allowed
        if unknown:
            raise NotImplementedError(f"Unsupported CL1 lifecycle options: {sorted(unknown)}")

    def _prepared(self, documents: list[Document], kwargs: dict[str, Any]):
        self._options(kwargs, {"ids", "expected_revisions"})
        ids = self._ids(kwargs.get("ids", [doc.id for doc in documents]), len(documents))
        revisions = kwargs.get("expected_revisions", {})
        if not isinstance(revisions, dict) or set(revisions) - set(ids):
            raise ValueError("Expected revisions must name only documents in this batch")
        for revision in revisions.values():
            if revision is None:
                raise ValueError("Expected revisions must be explicit integers")
            CL1Client._revision(revision)
        revisions = dict(revisions)
        prepared = []
        for source_id, doc in zip(ids, documents, strict=True):
            if not isinstance(doc.page_content, str) or not doc.page_content.strip():
                raise ValueError("Nonblank document text is required")
            if "\f" in doc.page_content:
                raise NotImplementedError(
                    "The CL1 text lifecycle subset excludes form-feed page splitting"
                )
            if "_cl1" in doc.metadata:
                provenance = doc.metadata["_cl1"]
                if (
                    not isinstance(provenance, dict)
                    or provenance.get("document_kind") != "full_source_document"
                    or type(provenance.get("source_revision")) is not int
                    or provenance["source_revision"] < 1
                    or not isinstance(provenance.get("source_sha256"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", provenance["source_sha256"])
                    or doc.id != source_id
                ):
                    raise ValueError(
                        "Only full-source documents can carry _cl1 provenance into an update"
                    )
                revisions.setdefault(source_id, provenance["source_revision"])
                doc = Document(
                    id=doc.id,
                    page_content=doc.page_content,
                    metadata={key: value for key, value in doc.metadata.items() if key != "_cl1"},
                )
            # Validate every item before the first write.
            CL1Client._document_metadata(doc.metadata)
            prepared.append(doc)
        return ids, revisions, prepared

    def _current_revision(self, source_id: str) -> int:
        try:
            revision = self.client.source_status(source_id)["revision"]
            CL1Client._revision(revision, allow_create=False)
            return revision
        except CL1Error as exc:
            if exc.status_code == 404:
                return 0
            raise

    async def _acurrent_revision(self, source_id: str) -> int:
        try:
            revision = (await self.client.asource_status(source_id))["revision"]
            CL1Client._revision(revision, allow_create=False)
            return revision
        except CL1Error as exc:
            if exc.status_code == 404:
                return 0
            raise

    def add_documents(self, documents: list[Document], **kwargs: Any) -> list[str]:
        ids, revisions, documents = self._prepared(documents, kwargs)
        self.write_receipts = []
        for source_id, doc in zip(ids, documents, strict=True):
            try:
                revision = (
                    revisions[source_id]
                    if source_id in revisions
                    else self._current_revision(source_id)
                )
                receipt = self.client.ingest_document(
                    source_id,
                    source_id + ".txt",
                    doc.page_content,
                    expected_revision=revision,
                    metadata=doc.metadata,
                )
                self.write_receipts.append({"source_id": source_id, **receipt})
            except (CL1Error, ValueError) as exc:
                raise CL1BatchError("write", self.write_receipts.copy(), source_id, exc) from exc
        return ids

    async def aadd_documents(self, documents: list[Document], **kwargs: Any) -> list[str]:
        ids, revisions, documents = self._prepared(documents, kwargs)
        self.write_receipts = []
        for source_id, doc in zip(ids, documents, strict=True):
            try:
                revision = (
                    revisions[source_id]
                    if source_id in revisions
                    else await self._acurrent_revision(source_id)
                )
                receipt = await self.client.aingest_document(
                    source_id,
                    source_id + ".txt",
                    doc.page_content,
                    expected_revision=revision,
                    metadata=doc.metadata,
                )
                self.write_receipts.append({"source_id": source_id, **receipt})
            except (CL1Error, ValueError) as exc:
                raise CL1BatchError("write", self.write_receipts.copy(), source_id, exc) from exc
        return ids

    def add_texts(self, texts: Iterable[str], metadatas=None, *, ids=None, **kwargs):
        texts = list(texts)
        metadatas = [{} for _ in texts] if metadatas is None else list(metadatas)
        if len(texts) != len(metadatas):
            raise ValueError("Metadata must have one object per text")
        return self.add_documents(
            [
                Document(page_content=text, metadata=meta)
                for text, meta in zip(texts, metadatas, strict=True)
            ],
            ids=ids,
            **kwargs,
        )

    async def aadd_texts(self, texts: Iterable[str], metadatas=None, *, ids=None, **kwargs):
        texts = list(texts)
        metadatas = [{} for _ in texts] if metadatas is None else list(metadatas)
        if len(texts) != len(metadatas):
            raise ValueError("Metadata must have one object per text")
        return await self.aadd_documents(
            [
                Document(page_content=text, metadata=meta)
                for text, meta in zip(texts, metadatas, strict=True)
            ],
            ids=ids,
            **kwargs,
        )

    @staticmethod
    def _snapshot_document(snapshot: dict[str, Any]) -> Document:
        sessions = snapshot["sessions"]
        if (
            len(sessions) != 1
            or len(sessions[0]["turns"]) != 1
            or sessions[0]["turns"][0]["role"] != "source"
        ):
            raise NotImplementedError(
                "Full-document reads support only the single-turn text lifecycle subset"
            )
        return Document(
            id=snapshot["source_id"],
            page_content=sessions[0]["turns"][0]["text"],
            metadata={
                **snapshot["metadata"],
                "_cl1": {
                    "document_kind": "full_source_document",
                    "source_revision": snapshot["revision"],
                    "source_sha256": snapshot["source_sha256"],
                    "canonicalization": snapshot["canonicalization"],
                    "offset_basis": snapshot["offset_basis"],
                    "source_provenance": snapshot.get("source_provenance"),
                    "imported_lineage": snapshot.get("imported_lineage"),
                },
            },
        )

    def get_by_ids(self, ids: list[str]) -> list[Document]:
        documents = []
        for source_id in self._ids(ids):
            try:
                documents.append(self._snapshot_document(self.client.fetch_source(source_id)))
            except CL1Error as exc:
                if exc.status_code != 404:
                    raise
        return documents

    async def aget_by_ids(self, ids: list[str]) -> list[Document]:
        documents = []
        for source_id in self._ids(ids):
            try:
                documents.append(
                    self._snapshot_document(await self.client.afetch_source(source_id))
                )
            except CL1Error as exc:
                if exc.status_code != 404:
                    raise
        return documents

    def _search_client(self, kwargs: dict[str, Any]) -> CL1Client:
        self._options(kwargs, {"filter", "date", "profile"})
        filters = kwargs.get("filter")
        if filters is None:
            return self.client
        if not isinstance(filters, dict) or set(filters) != {"source_id"}:
            raise NotImplementedError(
                "CL1 supports only source_id equality or source_id $in filters"
            )
        value = filters["source_id"]
        ids = (
            [value]
            if isinstance(value, str)
            else value.get("$in")
            if isinstance(value, dict) and set(value) == {"$in"}
            else None
        )
        ids = self._ids(ids)
        if not ids or len(ids) > 128:
            raise ValueError("A source filter must select 1 through 128 distinct IDs")
        if self.client.source_ids and not set(ids) <= set(self.client.source_ids):
            raise ValueError("A source filter cannot widen the bound client selection")
        return self.client.with_sources(ids)

    @staticmethod
    def _k(k: int) -> None:
        if type(k) is not int or k < 1:
            raise ValueError("k must be a positive integer")

    def _search_documents(self, context: CL1Context, k: int) -> list[Document]:
        docs = CL1Retriever._documents(context)[:k]
        revisions = {binding["source_id"]: binding["revision"] for binding in context.source_bindings}
        snapshots = {
            source_id: self.client.fetch_source(source_id, revision=revisions[source_id])
            for source_id in dict.fromkeys(doc.metadata["source_id"] for doc in docs)
        }
        for doc in docs:
            provenance = doc.metadata
            doc.id = provenance["source_id"]
            doc.metadata = {**snapshots[doc.id]["metadata"], "_cl1": provenance}
        return docs

    def similarity_search(self, query: str, k: int = 4, **kwargs: Any) -> list[Document]:
        self._k(k)
        client = self._search_client(kwargs)
        return self._search_documents(
            client.context(query, date=kwargs.get("date"), profile=kwargs.get("profile")), k
        )

    async def asimilarity_search(self, query: str, k: int = 4, **kwargs: Any) -> list[Document]:
        self._k(k)
        client = self._search_client(kwargs)
        context = await client.acontext(
            query, date=kwargs.get("date"), profile=kwargs.get("profile")
        )
        docs = CL1Retriever._documents(context)[:k]
        revisions = {binding["source_id"]: binding["revision"] for binding in context.source_bindings}
        snapshots = {}
        for source_id in dict.fromkeys(doc.metadata["source_id"] for doc in docs):
            snapshots[source_id] = await self.client.afetch_source(source_id, revision=revisions[source_id])
        for doc in docs:
            provenance = doc.metadata
            doc.id = provenance["source_id"]
            doc.metadata = {**snapshots[doc.id]["metadata"], "_cl1": provenance}
        return docs

    def similarity_search_with_score(self, *args, **kwargs):
        raise NotImplementedError(
            "CL1 evidence ordering has no vector-distance or similarity-score meaning"
        )

    async def asimilarity_search_with_score(self, *args, **kwargs):
        raise NotImplementedError(
            "CL1 evidence ordering has no vector-distance or similarity-score meaning"
        )

    def similarity_search_with_relevance_scores(self, *args, **kwargs):
        raise NotImplementedError("CL1 does not fabricate normalized relevance scores")

    async def asimilarity_search_with_relevance_scores(self, *args, **kwargs):
        raise NotImplementedError("CL1 does not fabricate normalized relevance scores")

    def max_marginal_relevance_search(self, *args, **kwargs):
        raise NotImplementedError("CL1 does not implement LangChain MMR semantics")

    async def amax_marginal_relevance_search(self, *args, **kwargs):
        raise NotImplementedError("CL1 does not implement LangChain MMR semantics")

    @classmethod
    def from_texts(
        cls, texts, embedding=None, metadatas=None, *, client: CL1Client, ids=None, **kwargs
    ):
        if embedding is not None:
            raise NotImplementedError("The CL1 adapter does not accept arbitrary embeddings")
        store = cls(client)
        store.add_texts(texts, metadatas, ids=ids, **kwargs)
        return store

    @classmethod
    async def afrom_texts(
        cls, texts, embedding=None, metadatas=None, *, client: CL1Client, ids=None, **kwargs
    ):
        if embedding is not None:
            raise NotImplementedError("The CL1 adapter does not accept arbitrary embeddings")
        store = cls(client)
        await store.aadd_texts(texts, metadatas, ids=ids, **kwargs)
        return store
