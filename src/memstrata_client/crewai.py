# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""Read-only CrewAI tool; credentials never appear in serializable fields."""

from __future__ import annotations

import json

from crewai.tools import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

from memstrata_client.cl1 import CL1Client
from memstrata_client.tool_schema import DESCRIPTION, context_result


class ContextInput(BaseModel):
    question: str = Field(description="Question to retrieve authorized evidence for")


class CL1ContextTool(BaseTool):
    name: str = "cl1_get_context"
    description: str = DESCRIPTION
    args_schema: type[BaseModel] = ContextInput
    _client: CL1Client = PrivateAttr()

    def __init__(self, client: CL1Client, **kwargs):
        super().__init__(**kwargs)
        self._client = client

    def _run(self, question: str) -> str:
        return json.dumps(context_result(self._client.context(question)), ensure_ascii=False)

    async def _arun(self, question: str) -> str:
        return json.dumps(context_result(await self._client.acontext(question)), ensure_ascii=False)
