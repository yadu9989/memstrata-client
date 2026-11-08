# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""Explicit LangGraph helpers; never an implicit persistent BaseStore."""

from __future__ import annotations

from collections.abc import Mapping

from memstrata_client.cl1 import CL1Client
from memstrata_client.tool_schema import DESCRIPTION, context_result


def create_retriever_tool(client: CL1Client):
    from langchain_core.tools import StructuredTool

    from memstrata_client.langchain import CL1Retriever

    retriever = CL1Retriever(client=client)

    def retrieve(question: str) -> list[dict]:
        return [document.model_dump() for document in retriever.invoke(question)]

    async def aretrieve(question: str) -> list[dict]:
        return [document.model_dump() for document in await retriever.ainvoke(question)]

    return StructuredTool.from_function(
        retrieve, coroutine=aretrieve, name="cl1_get_context", description=DESCRIPTION
    )


def create_context_node(
    client: CL1Client, *, question_key="question", output_key="memstrata_context"
):
    if not question_key or not output_key or question_key == output_key:
        raise ValueError("Distinct explicit input and output state keys are required")

    async def retrieve(state: Mapping) -> dict:
        if not isinstance(state, Mapping) or not isinstance(state.get(question_key), str):
            raise ValueError("An explicit text question is required")
        return {output_key: context_result(await client.acontext(state[question_key]))}

    return retrieve
