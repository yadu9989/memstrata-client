from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def run_cli(
    arguments: list[str],
    config_path: Path,
    *,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["MEMSTRATA_CLIENT_CONFIG"] = str(config_path)
    return subprocess.run(
        [sys.executable, "-m", "memstrata_client.cli", *arguments],
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
        env=environment,
    )


def test_cli_mock_quickstart_is_json_serializable(tmp_path: Path) -> None:
    config_path = tmp_path / "client.json"

    initialized = run_cli(["init", "--mock"], config_path)
    assert initialized.returncode == 0, initialized.stderr
    initialized_value = json.loads(initialized.stdout)
    assert initialized_value["status"] == "initialized"
    assert initialized_value["runtime"]["license"]["status"] == "mock"

    doctor = run_cli(["doctor"], config_path)
    assert doctor.returncode == 0, doctor.stderr
    assert json.loads(doctor.stdout)["license"]["status"] == "mock"

    processed = run_cli(
        ["process"],
        config_path,
        input_text=json.dumps(
            [{"role": "user", "content": "Published package smoke test."}]
        ),
    )
    assert processed.returncode == 0, processed.stderr
    result = json.loads(processed.stdout)["result"]
    assert result["assurance"]["source_truth"] == "NOT_ASSERTED"
    assert len(result["memory"]) == 1
    assert len(result["evidence"]) == 1
