# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""Packaging must follow the package version; a stale copy has to fail validation."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _validate(tree: Path):
    return subprocess.run(
        [sys.executable, str(tree / "packaging" / "validate.py")],
        cwd=tree,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _copy(tmp_path: Path) -> Path:
    tree = tmp_path / "tree"
    shutil.copytree(ROOT / "packaging", tree / "packaging")
    (tree / "src" / "memstrata_client").mkdir(parents=True)
    shutil.copy(
        ROOT / "src" / "memstrata_client" / "_version.py", tree / "src" / "memstrata_client"
    )
    return tree


def test_unmodified_copy_validates(tmp_path):
    assert _validate(_copy(tmp_path)).returncode == 0


def test_stale_product_json_version_fails(tmp_path):
    tree = _copy(tmp_path)
    path = tree / "packaging" / "product.json"
    path.write_text(
        path.read_text(encoding="utf-8").replace('"version": "0.2.0"', '"version": "0.1.0"'),
        encoding="utf-8",
    )
    result = _validate(tree)
    assert result.returncode == 1 and "product.json version" in result.stderr


def test_stale_script_defaults_fail(tmp_path):
    for rel, old, new, message in [
        ("macos/build-pkg.sh", 'version="0.2.0"', 'version="0.1.0"', "build-pkg.sh"),
        ("windows/build-msix.ps1", '"0.2.0.0"', '"0.1.0.0"', "build-msix.ps1"),
        ("linux/snap/snapcraft.yaml", "version: '0.2.0'", "version: '0.1.0'", "snapcraft.yaml"),
    ]:
        tree = _copy(tmp_path / rel.replace("/", "_"))
        path = tree / "packaging" / rel
        text = path.read_text(encoding="utf-8")
        assert old in text, rel
        path.write_text(text.replace(old, new), encoding="utf-8")
        result = _validate(tree)
        assert result.returncode == 1 and message in result.stderr, (rel, result.stderr)
