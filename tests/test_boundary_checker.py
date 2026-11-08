# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Called It Inc.
"""The boundary checker tolerates developer folders and still catches real violations."""

from tools import check_public_boundary as boundary


def _tree(root, names):
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n", encoding="utf-8")


def test_common_developer_folders_do_not_fail_the_check(tmp_path, monkeypatch):
    monkeypatch.setattr(boundary, "ROOT", tmp_path)
    _tree(
        tmp_path,
        [
            "README.md",
            "src/pkg/mod.py",
            "venv/lib/x.py",
            ".idea/w.xml",
            ".mypy_cache/c.json",
            ".tox/t.py",
        ],
    )
    (tmp_path / ".DS_Store").write_bytes(b"\0")
    assert boundary.scan() == []


def test_real_violations_are_still_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(boundary, "ROOT", tmp_path)
    _tree(tmp_path, ["src/pkg/mod.py", "secret_engine/core.py", "src/pkg/lib.so"])
    (tmp_path / "src/pkg/bad.py").write_text("import harness.cli\n", encoding="utf-8")
    failures = " ".join(boundary.scan())
    assert "non-allowlisted top-level path: secret_engine" in failures
    assert "forbidden artifact type" in failures and "proprietary import 'harness.cli'" in failures
