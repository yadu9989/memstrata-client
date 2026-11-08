# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""Producer SDK for the mnemo/v0 ingest contract (stdlib only)."""

from memstrata_client._version import __version__
from memstrata_client.mnemo.envelope import (
    MAX_ITEMS_PER_ENVELOPE,
    MAX_TEXT,
    SCHEMA_V0,
    MnemoTransportError,
    MnemoValidationError,
    build_envelope,
    canonical_json,
    envelope_id,
    post_envelope,
)
from memstrata_client.mnemo.producer import IngestError, MemStrataProducer

__all__ = [
    "IngestError",
    "MAX_ITEMS_PER_ENVELOPE",
    "MAX_TEXT",
    "MemStrataProducer",
    "MnemoTransportError",
    "MnemoValidationError",
    "SCHEMA_V0",
    "__version__",
    "build_envelope",
    "canonical_json",
    "envelope_id",
    "post_envelope",
]
