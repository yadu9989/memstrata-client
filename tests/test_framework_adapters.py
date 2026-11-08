# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""Real framework interfaces with synthetic CL1 transport; never model agents."""

import asyncio
import json
from typing import TypedDict

import pytest

from tests.cl1_fixture import TEXT, mock_client


def test_langgraph_real_graph_node_and_toolnode():
    pytest.importorskip("langgraph")
    from langchain_core.messages import AIMessage, ToolMessage
    from langgraph.graph import END, START, MessagesState, StateGraph
    from langgraph.prebuilt import ToolNode

    from memstrata_client.langgraph import create_context_node, create_retriever_tool

    calls = []
    client, sync, asynchronous = mock_client(calls)

    class State(TypedDict):
        question: str
        memstrata_context: dict

    async def run():
        try:
            builder = StateGraph(State)
            builder.add_node("retrieve", create_context_node(client))
            builder.add_edge(START, "retrieve")
            builder.add_edge("retrieve", END)
            result = await builder.compile().ainvoke({"question": "When?"})
            assert result["memstrata_context"]["assembled_context"] == TEXT
            tool = create_retriever_tool(client)
            tools_graph = StateGraph(MessagesState)
            tools_graph.add_node("tools", ToolNode([tool]))
            tools_graph.add_edge(START, "tools")
            tools_graph.add_edge("tools", END)
            value = await tools_graph.compile().ainvoke(
                {
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "cl1_get_context",
                                    "args": {"question": "When?"},
                                    "id": "synthetic-call",
                                    "type": "tool_call",
                                }
                            ],
                        )
                    ]
                }
            )
            replies = [
                message
                for message in value["messages"]
                if isinstance(message, ToolMessage) and message.tool_call_id == "synthetic-call"
            ]
            assert len(replies) == 1
            content = json.loads(replies[0].content)
            assert content[0]["metadata"]["session_index"] == 2
            assert content[0]["page_content"] == TEXT
        finally:
            sync.close()
            await asynchronous.aclose()

    asyncio.run(run())
    assert len(calls) == 2


def test_crewai_real_basetool_sync_async_and_no_serialized_secret():
    pytest.importorskip("crewai")
    from crewai.tools import BaseTool

    from memstrata_client.crewai import CL1ContextTool

    calls = []
    client, sync, asynchronous = mock_client(calls)

    async def run():
        try:
            tool = CL1ContextTool(client)
            assert isinstance(tool, BaseTool)
            assert "cl1_synthetic" not in tool.model_dump_json()
            assert json.loads(tool.run(question="When?"))["assembled_context"] == TEXT
            assert json.loads(await tool.arun(question="When?"))["documents"][0]["turn_index"] == 3
        finally:
            sync.close()
            await asynchronous.aclose()

    asyncio.run(run())
    assert len(calls) == 2


def test_autogen_real_memory_context_function_tool_and_readonly_refusals():
    pytest.importorskip("autogen_core")
    from autogen_core import CancellationToken
    from autogen_core.memory import Memory, MemoryContent
    from autogen_core.model_context import UnboundedChatCompletionContext
    from autogen_core.models import UserMessage

    from memstrata_client.autogen import CL1Memory, create_function_tool

    calls = []
    client, sync, asynchronous = mock_client(calls)

    async def run():
        try:
            memory = CL1Memory(client)
            assert isinstance(memory, Memory)
            assert (await memory.query("When?")).results[0].content["assembled_context"] == TEXT
            context = UnboundedChatCompletionContext()
            await context.add_message(UserMessage(content="When?", source="user"))
            result = await memory.update_context(context)
            assert result.memories.results
            assert "Untrusted source evidence" in (await context.get_messages())[-1].content
            tool = create_function_tool(client)
            assert (await tool.run_json({"question": "When?"}, CancellationToken()))["documents"][
                0
            ]["source_id"] == "note"
            before = len(calls)
            cancelled = CancellationToken()
            cancelled.cancel()
            with pytest.raises(asyncio.CancelledError):
                await memory.query("When?", cancelled)
            with pytest.raises(NotImplementedError):
                await memory.add(MemoryContent(content="new", mime_type="text/plain"))
            with pytest.raises(NotImplementedError):
                await memory.clear()
            with pytest.raises(ValueError):
                memory._to_config()
            await memory.close()
            with pytest.raises(RuntimeError):
                await memory.query("When?")
            assert len(calls) == before
        finally:
            sync.close()
            await asynchronous.aclose()

    asyncio.run(run())
    assert len(calls) == 3


def test_ag2_real_function_tool_schema_and_event_dispatch():
    pytest.importorskip("ag2")
    from ag2.context import ConversationContext
    from ag2.events import ToolCallEvent, ToolResultEvent
    from ag2.tools.types import FunctionTool

    from memstrata_client.ag2 import create_function_tool

    calls = []
    client, sync, asynchronous = mock_client(calls)

    async def run():
        try:
            tool = create_function_tool(client)
            assert isinstance(tool, FunctionTool)
            assert tool.schema.function.name == "cl1_get_context"
            assert set(tool.schema.function.parameters["properties"]) == {"question"}
            context = ConversationContext(stream=None)
            result = await tool(
                ToolCallEvent(name="cl1_get_context", arguments='{"question":"When?"}'), context
            )
            assert isinstance(result, ToolResultEvent)
        finally:
            sync.close()
            await asynchronous.aclose()

    asyncio.run(run())
    assert len(calls) == 1


def test_llamaindex_real_retriever_preserves_locators_and_no_invented_score():
    pytest.importorskip("llama_index.core")
    from llama_index.core.callbacks import CallbackManager
    from llama_index.core.retrievers import BaseRetriever

    from memstrata_client.llamaindex import CL1Retriever

    calls = []
    client, sync, asynchronous = mock_client(calls)

    async def run():
        try:
            retriever = CL1Retriever(client, callback_manager=CallbackManager([]))
            assert isinstance(retriever, BaseRetriever)
            for rows in (retriever.retrieve("When?"), await retriever.aretrieve("When?")):
                assert rows[0].score is None and rows[0].node.text == TEXT
                assert rows[0].node.metadata["session_index"] == 2
                assert rows[0].node.node_id == "note@1:s2:t3:0-22"
        finally:
            sync.close()
            await asynchronous.aclose()

    asyncio.run(run())
    assert len(calls) == 2
