# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""The four protocol modules match the reviewed, frozen hash list."""

import hashlib
import json
from pathlib import Path


def test_frozen_protocol_copy_hashes():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "docs/CL1_SOURCE_PARITY.json").read_text())
    assert len(manifest["files"]) == 4
    for row in manifest["files"]:
        path = root / row["path"]
        assert path.resolve().is_relative_to(root / "src/memstrata_client")
        text = path.read_text(encoding="utf-8")
        assert hashlib.sha256(text.encode()).hexdigest() == row["sha256"]
