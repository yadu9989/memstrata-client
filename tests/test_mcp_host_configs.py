# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""The documented host snippets must stay valid against the real launcher."""

import json
import re
from pathlib import Path

from memstrata_client.mcp_cli import parser

DOC = Path(__file__).resolve().parents[1] / "docs" / "MCP_HOSTS.md"


def _entries():
    blocks = re.findall(r"```json\n(.*?)\n```", DOC.read_text(encoding="utf-8"), re.S)
    assert blocks, "docs/MCP_HOSTS.md has no JSON blocks"
    for block in blocks:
        config = json.loads(block)
        servers = config.get("servers") or config.get("mcpServers")
        assert servers, "block has neither servers nor mcpServers"
        yield from servers.items()


def test_every_documented_entry_parses_with_the_real_cli_and_holds_no_key():
    seen = 0
    for _name, entry in _entries():
        seen += 1
        args = entry["args"]
        assert entry["command"] == "uvx" and "memstrata-mcp" in args
        launcher = args[args.index("memstrata-mcp") + 1 :]
        parsed = parser().parse_args(launcher)
        assert parsed.project and parsed.key_ref.startswith("keychain:")
        flat = json.dumps(entry)
        assert "cl1_" not in flat and "Bearer" not in flat
    assert seen >= 2


def test_documented_package_version_is_the_current_one():
    from memstrata_client import __version__

    assert f"memstrata-client[mcp,keyring]=={__version__}" in DOC.read_text(encoding="utf-8")
