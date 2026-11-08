# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""Default loopback client for a desktop-provisioned scoped app credential."""

from __future__ import annotations

import httpx

from memstrata_client.cl1 import CL1Client, _transport_options
from memstrata_client.cl1_credentials import app_key
from memstrata_client.errors import ConfigurationError

DEFAULT_URL = "http://127.0.0.1:9101"
DEFAULT_PROJECT = "personal"
DEFAULT_KEY_REF = "keychain:default-local-sdk"


class MemStrataClient(CL1Client):
    """Use the default local service and a previously enrolled SDK app grant."""

    def __init__(self) -> None:
        try:
            with httpx.Client(
                timeout=3.0, trust_env=False, **_transport_options(DEFAULT_URL)
            ) as client:
                response = client.get(f"{DEFAULT_URL}/health")
                response.raise_for_status()
                health = response.json()
        except (httpx.HTTPError, ValueError):
            raise ConfigurationError(
                "Start MemStrata Conversational with memstrata-conversational assistant."
            ) from None
        if (not isinstance(health, dict) or health.get("status") != "alive"
                or not isinstance(health.get("product_version"), str)):
            raise ConfigurationError("The default port does not identify a MemStrata runtime.")
        try:
            token = app_key(DEFAULT_KEY_REF)
        except ValueError:
            raise ConfigurationError(
                "The default scoped SDK grant is missing from the OS vault."
            ) from None
        super().__init__(DEFAULT_URL, project_id=DEFAULT_PROJECT, token=token,
                         source_scope="all_ready")
