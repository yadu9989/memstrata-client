# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""Read an explicit OS-vault reference or environment app key; never persist it."""
from __future__ import annotations

import os
import re

SERVICE = "MemStrata CL1 app keys"
OS_BACKENDS = frozenset({"keyring.backends.Windows", "keyring.backends.macOS",
                         "keyring.backends.SecretService", "keyring.backends.kwallet"})


def _os_keyring():
    try:
        import keyring
        backend = keyring.get_keyring()
        if type(backend).__module__ not in OS_BACKENDS:
            raise ValueError("OS vault required")
        return backend
    except Exception:
        raise ValueError("OS keychain unavailable; install keyring support and configure the OS vault") from None


def app_key(key_ref: str | None = None) -> str:
    """An explicit reference never falls back to an unrelated environment key."""
    if key_ref is None:
        value = os.environ.get("MEMSTRATA_CL1_TOKEN", "")
    else:
        if not isinstance(key_ref, str) or not re.fullmatch(r"keychain:[A-Za-z0-9._-]{1,80}", key_ref):
            raise ValueError("Use --key-ref keychain:<name> with a simple nonsecret name")
        backend = _os_keyring()
        try:
            value = backend.get_password(SERVICE, key_ref.partition(":")[2])
        except Exception:
            raise ValueError("The referenced CL1 key is unavailable; no fallback was attempted") from None
    if (not isinstance(value, str) or not value.startswith("cl1_") or not 4 < len(value) <= 128
            or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError("Set MEMSTRATA_CL1_TOKEN or choose an available --key-ref for an owner-created CL1 app key")
    return value
