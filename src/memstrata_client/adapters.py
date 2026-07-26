"""Dependency-free normalization helpers for common agent message shapes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from memstrata_client.errors import ProtocolError
from memstrata_client.models import Message


def from_role_content(messages: Sequence[Mapping[str, Any]]) -> list[Message]:
    """Normalize OpenAI-compatible, AutoGen, and CrewAI role/content mappings."""
    return [Message.from_value(message) for message in messages]


def from_langchain(messages: Sequence[Any]) -> list[Message]:
    """Normalize LangChain-like objects without importing LangChain."""
    role_map = {"human": "user", "ai": "assistant", "system": "system", "tool": "tool"}
    result: list[Message] = []
    for index, item in enumerate(messages):
        role = getattr(item, "type", None)
        content = getattr(item, "content", None)
        if role not in role_map or not isinstance(content, str):
            raise ProtocolError(f"unsupported LangChain-like message at index {index}")
        name = getattr(item, "name", None)
        result.append(Message(role=role_map[role], content=content, name=name))
    return result
