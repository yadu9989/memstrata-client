# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
from tools.check_public_boundary import scan


def test_public_boundary() -> None:
    assert scan() == []
