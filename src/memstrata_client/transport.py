"""Bounded JSON-lines subprocess transport."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from memstrata_client.errors import ProtocolError, RuntimeFailure, RuntimeTimeout

MAX_REQUEST_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_STDERR_BYTES = 64 * 1024
SAFE_ENV_NAMES = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "TMP",
    "TEMP",
    "LANG",
    "LC_ALL",
)


class SubprocessTransport:
    """Execute one request against a runtime without exposing a local port."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        timeout: float = 60.0,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("runtime command must contain non-empty strings")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be positive")
        self.command = tuple(command)
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes

    def execute(self, request: Mapping[str, Any]) -> Any:
        encoded = json.dumps(
            request,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8") + b"\n"
        if len(encoded) > MAX_REQUEST_BYTES:
            raise ProtocolError(f"request exceeds {MAX_REQUEST_BYTES} bytes")

        safe_env = {name: value for name in SAFE_ENV_NAMES if (value := os.environ.get(name))}
        safe_env["PYTHONIOENCODING"] = "utf-8"

        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            try:
                process = subprocess.Popen(
                    self.command,
                    stdin=subprocess.PIPE,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    env=safe_env,
                    close_fds=os.name != "nt",
                )
            except OSError as exc:
                raise RuntimeFailure(f"unable to start runtime: {exc}") from exc

            try:
                assert process.stdin is not None
                process.stdin.write(encoded)
                process.stdin.close()
                process.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                process.wait()
                raise RuntimeTimeout(f"runtime exceeded {self.timeout:.3f}s deadline") from exc
            except BrokenPipeError:
                process.wait()

            stdout_size = stdout_file.tell()
            stderr_size = stderr_file.tell()
            if stdout_size > self.max_response_bytes:
                raise ProtocolError(
                    f"runtime response exceeds {self.max_response_bytes} bytes"
                )
            if stderr_size > DEFAULT_MAX_STDERR_BYTES:
                raise RuntimeFailure("runtime diagnostics exceeded the safe byte ceiling")
            if process.returncode != 0:
                raise RuntimeFailure(
                    f"runtime exited with code {process.returncode}; "
                    f"{stderr_size} diagnostic bytes suppressed"
                )

            stdout_file.seek(0)
            raw = stdout_file.read()
            if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
                raise ProtocolError(
                    "runtime must emit exactly one newline-terminated JSON response"
                )
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ProtocolError("runtime response is not UTF-8") from exc
            try:
                return json.loads(text)
            except json.JSONDecodeError as exc:
                raise ProtocolError("runtime response is not valid JSON") from exc


def validate_runtime_path(command: Sequence[str]) -> None:
    """Reject an obviously missing local executable before saving config."""
    if not command:
        raise ValueError("empty runtime command")
    executable = command[0]
    if os.path.isabs(executable) or any(separator in executable for separator in ("/", "\\")):
        path = Path(executable).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"runtime executable not found: {path}")
