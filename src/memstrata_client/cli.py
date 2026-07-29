"""Command-line interface for the public client."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from memstrata_client.client import MemStrata
from memstrata_client.config import ClientConfig, save_config
from memstrata_client.errors import MemStrataError


def _runtime_command(args: argparse.Namespace) -> tuple[str, ...]:
    if args.mock:
        return (sys.executable, "-m", "memstrata_client.mock_runtime")
    return (str(Path(args.runtime).expanduser().resolve()),)


def _cmd_init(args: argparse.Namespace) -> int:
    command = _runtime_command(args)
    path = save_config(ClientConfig(command, args.timeout))
    client = MemStrata(command, timeout=args.timeout)
    activation = None
    if args.license_file:
        document = json.loads(Path(args.license_file).read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError("license document must be a JSON object")
        activation = dict(client.activate(document))
    status = dict(client.status())
    print(
        json.dumps(
            {
                "status": "initialized",
                "config": str(path),
                "activation": activation,
                "runtime": status,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _cmd_doctor(_args: argparse.Namespace) -> int:
    print(json.dumps(dict(MemStrata().status()), indent=2, sort_keys=True))
    return 0


def _cmd_process(args: argparse.Namespace) -> int:
    raw = Path(args.input).read_text(encoding="utf-8") if args.input else sys.stdin.read()
    value = json.loads(raw)
    messages = value.get("messages") if isinstance(value, dict) else value
    options = value.get("options") if isinstance(value, dict) else None
    result = MemStrata(timeout=args.timeout).process(messages, options=options)
    print(json.dumps(dict(result.raw), indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="memstrata-client")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="configure a separately installed runtime")
    runtime = init.add_mutually_exclusive_group(required=True)
    runtime.add_argument("--runtime", help="absolute path to the commercial runtime")
    runtime.add_argument("--mock", action="store_true", help="use the synthetic test runtime")
    init.add_argument("--license-file", help="signed license JSON; never a private key")
    init.add_argument("--timeout", type=float, default=60.0)
    init.set_defaults(handler=_cmd_init)

    doctor = sub.add_parser("doctor", help="query runtime and entitlement status")
    doctor.set_defaults(handler=_cmd_doctor)

    process = sub.add_parser("process", help="process JSON messages from stdin or a file")
    process.add_argument("--input")
    process.add_argument("--timeout", type=float)
    process.set_defaults(handler=_cmd_process)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return int(args.handler(args))
    except (MemStrataError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
