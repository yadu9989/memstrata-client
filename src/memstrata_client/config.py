"""Non-secret local client configuration."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from memstrata_client.errors import ConfigurationError
from memstrata_client.transport import validate_runtime_path

CONFIG_SCHEMA = "memstrata.client-config/v1"


def default_config_path() -> Path:
    override = os.environ.get("MEMSTRATA_CLIENT_CONFIG")
    if override:
        return Path(override).expanduser()
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "MemStrata" / "client.json"
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "memstrata" / "client.json"


@dataclass(frozen=True)
class ClientConfig:
    runtime_command: tuple[str, ...]
    timeout_seconds: float = 60.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": CONFIG_SCHEMA,
            "runtime_command": list(self.runtime_command),
            "timeout_seconds": self.timeout_seconds,
        }


def save_config(config: ClientConfig, path: Path | None = None) -> Path:
    validate_runtime_path(config.runtime_command)
    target = path or default_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    data = json.dumps(config.to_dict(), indent=2, sort_keys=True) + "\n"
    temporary.write_text(data, encoding="utf-8")
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    temporary.replace(target)
    return target


def load_config(path: Path | None = None) -> ClientConfig:
    target = path or default_config_path()
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigurationError(
            f"client is not initialized; run memstrata-client init ({target})"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"unable to read client config {target}: {exc}") from exc
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "runtime_command",
        "timeout_seconds",
    }:
        raise ConfigurationError("client config has an unsupported shape")
    if value["schema"] != CONFIG_SCHEMA:
        raise ConfigurationError(f"unsupported client config schema: {value['schema']!r}")
    command = value["runtime_command"]
    if not isinstance(command, list) or not command or not all(
        isinstance(part, str) and part for part in command
    ):
        raise ConfigurationError("runtime_command must be a non-empty string list")
    timeout = value["timeout_seconds"]
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0:
        raise ConfigurationError("timeout_seconds must be positive")
    validate_runtime_path(command)
    return ClientConfig(tuple(command), float(timeout))
