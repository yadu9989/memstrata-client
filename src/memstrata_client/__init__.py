# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""Public MemStrata runtime client.

This package contains protocol, validation, and transport code only. It does
not contain a memory engine or licensing enforcement.
"""

from memstrata_client._version import __version__
from memstrata_client.client import MemStrata
from memstrata_client.errors import (
    ConfigurationError,
    ProtocolError,
    RuntimeFailure,
    RuntimeTimeout,
)
from memstrata_client.local import MemStrataClient
from memstrata_client.models import (
    Assurance,
    Claim,
    Evidence,
    MemoryItem,
    Message,
    ProcessResult,
)

__all__ = [
    "Assurance",
    "Claim",
    "ConfigurationError",
    "Evidence",
    "MemoryItem",
    "MemStrata",
    "MemStrataClient",
    "Message",
    "ProcessResult",
    "ProtocolError",
    "RuntimeFailure",
    "RuntimeTimeout",
    "__version__",
]
