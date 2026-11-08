# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""Audit the open-client wheel inventory, metadata and RECORD; never publish."""

from __future__ import annotations

import argparse
import base64
import configparser
import csv
import hashlib
import io
import json
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile

from packaging.requirements import Requirement


def audit(path: Path):
    with ZipFile(path) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)), "Duplicate wheel member"
        assert archive.testzip() is None, "CRC failure"
        for name in names:
            assert name.startswith(("memstrata_client/", "memstrata_client-0.2.0.dist-info/"))
            assert ".." not in name.split("/") and "\\" not in name
            assert not name.endswith((".dll", ".so", ".exe", ".bin", ".pkl", ".pem"))
        dist = "memstrata_client-0.2.0.dist-info/"
        metadata = BytesParser().parsebytes(archive.read(dist + "METADATA"))
        assert metadata["Name"] == "memstrata-client" and metadata["Version"] == "0.2.0"
        requirements = [Requirement(item) for item in metadata.get_all("Requires-Dist", [])]
        base = [str(item) for item in requirements if item.marker is None]
        assert len(base) == 2 and {Requirement(item).name for item in base} == {"httpx", "keyring"}
        assert "memstrata_client/mnemo/envelope.py" in names
        assert "memstrata_client/mnemo/producer.py" in names
        entries = configparser.ConfigParser()
        entries.read_string(archive.read(dist + "entry_points.txt").decode())
        assert entries["console_scripts"]["memstrata-mcp"] == "memstrata_client.mcp_cli:main"
        records = list(csv.reader(io.StringIO(archive.read(dist + "RECORD").decode())))
        assert {row[0] for row in records} == set(names)
        for name, digest, size in records:
            if name == dist + "RECORD":
                assert not digest and not size
                continue
            raw = archive.read(name)
            expected = "sha256=" + base64.urlsafe_b64encode(
                hashlib.sha256(raw).digest()
            ).decode().rstrip("=")
            assert digest == expected and int(size) == len(raw), name
    return {
        "status": "PASS",
        "wheel": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "files": names,
        "base_requirements": base,
        "requires_dist": metadata.get_all("Requires-Dist"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    print(json.dumps(audit(parser.parse_args().wheel), sort_keys=True))


if __name__ == "__main__":
    main()
