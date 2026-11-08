# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""Read-only stdio entry point; credentials are references or environment only."""

from __future__ import annotations

import argparse
import sys

from memstrata_client.cl1 import CL1Client
from memstrata_client.cl1_credentials import app_key


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # Argparse's default error may echo an accidentally pasted credential.
        self.exit(
            2,
            "Invalid MCP arguments. Use --help; app-key values belong only "
            "in the environment or OS vault.\n",
        )


def parser() -> argparse.ArgumentParser:
    result = _Parser(description=__doc__)
    result.add_argument("--url", default="http://127.0.0.1:9101")
    result.add_argument("--project", required=True)
    scope = result.add_mutually_exclusive_group()
    scope.add_argument("--all-sources", action="store_true")
    scope.add_argument("--source-id", action="append", default=[])
    result.add_argument("--profile", choices=("standard_8k", "deep_24k"), default="standard_8k")
    result.add_argument("--key-ref", help="OS-vault reference keychain:<name>; never a key value")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    # Fail before reading a credential if the optional server is unavailable.
    try:
        import mcp.server.fastmcp  # noqa: F401
    except ImportError:
        print('Install "memstrata-client[mcp]" to run the MCP server.', file=sys.stderr)
        return 2
    from memstrata_client.mcp import create_server

    try:
        client = CL1Client(
            args.url,
            project_id=args.project,
            token=app_key(args.key_ref),
            source_ids=args.source_id,
            source_scope="selected" if args.source_id else "all_ready",
            profile=args.profile,
        )
    except ValueError:
        print(
            "Invalid CL1 connection or unavailable app-key reference. "
            "No fallback or retry was made.",
            file=sys.stderr,
        )
        return 2
    # Keep protocol stdout free of diagnostics and credential values.
    create_server(client).run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
