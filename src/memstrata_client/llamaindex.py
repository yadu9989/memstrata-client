# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""LlamaIndex retriever preserving source locators, without invented scores."""

from __future__ import annotations

from dataclasses import asdict

from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore, TextNode

from memstrata_client.cl1 import CL1Client


class CL1Retriever(BaseRetriever):
    def __init__(self, client: CL1Client, **kwargs):
        super().__init__(**kwargs)
        self._client = client

    @staticmethod
    def _nodes(context):
        return [
            NodeWithScore(
                node=TextNode(
                    text=document.quote,
                    id_=f"{document.source_id}@{document.revision}:s{document.session_index}:t{document.turn_index}:{document.start_byte}-{document.end_byte}",
                    metadata={
                        **{key: value for key, value in asdict(document).items() if key != "quote"},
                        "evidence_profile": context.effective_profile,
                        "answer_correctness": "NOT_MEASURED",
                    },
                ),
                score=None,
            )
            for document in context.documents
        ]

    def _retrieve(self, query_bundle):
        return self._nodes(self._client.context(query_bundle.query_str))

    async def _aretrieve(self, query_bundle):
        return self._nodes(await self._client.acontext(query_bundle.query_str))
