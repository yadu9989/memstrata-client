# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""Current AG2 function-tool adapter; separate from Microsoft's AutoGen API."""

from __future__ import annotations

from memstrata_client.cl1 import CL1Client
from memstrata_client.tool_schema import create_async_context_function


def create_function_tool(client: CL1Client):
    from ag2 import tool

    return tool(create_async_context_function(client))
