"""High-level public client."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from memstrata_client._version import __version__
from memstrata_client.config import ClientConfig, load_config
from memstrata_client.models import (
    Message,
    ProcessResult,
    normalize_messages,
    normalize_options,
)
from memstrata_client.transport import SubprocessTransport
from memstrata_client.validation import (
    PROTOCOL,
    parse_activation_response,
    parse_process_response,
    parse_status_response,
)


class MemStrata:
    """Client for a separately installed MemStrata runtime."""

    def __init__(
        self,
        runtime_command: Sequence[str] | None = None,
        *,
        timeout: float | None = None,
        config: ClientConfig | None = None,
    ) -> None:
        selected = config or (load_config() if runtime_command is None else None)
        command = tuple(runtime_command or (selected.runtime_command if selected else ()))
        selected_timeout = timeout if timeout is not None else (
            selected.timeout_seconds if selected else 60.0
        )
        self._transport = SubprocessTransport(command, timeout=selected_timeout)

    def process(
        self,
        messages: Sequence[Message | Mapping[str, Any]],
        *,
        options: Mapping[str, Any] | None = None,
    ) -> ProcessResult:
        normalized_messages = normalize_messages(messages)
        normalized_options = normalize_options(options)
        request_id = str(uuid.uuid4())
        request = {
            "protocol": PROTOCOL,
            "request_id": request_id,
            "operation": "process",
            "messages": [item.to_dict() for item in normalized_messages],
            "options": dict(normalized_options),
            "client": {"name": "memstrata-client", "version": __version__},
        }
        response = self._transport.execute(request)
        return parse_process_response(response, request_id)

    def status(self) -> Mapping[str, Any]:
        request_id = str(uuid.uuid4())
        response = self._transport.execute(
            {
                "protocol": PROTOCOL,
                "request_id": request_id,
                "operation": "status",
                "client": {"name": "memstrata-client", "version": __version__},
            }
        )
        return parse_status_response(response, request_id)

    def activate(self, license_document: Mapping[str, Any]) -> Mapping[str, Any]:
        request_id = str(uuid.uuid4())
        response = self._transport.execute(
            {
                "protocol": PROTOCOL,
                "request_id": request_id,
                "operation": "activate",
                "license": dict(license_document),
                "client": {"name": "memstrata-client", "version": __version__},
            }
        )
        return parse_activation_response(response, request_id)
